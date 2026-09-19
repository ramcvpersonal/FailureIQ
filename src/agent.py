"""
agent.py — FailureIQ Agent (ReAct Pattern)
--------------------------------------------------
ReAct = Reason + Act

INTERVIEW TALKING POINT:
  The ReAct pattern lets an LLM reason step-by-step and take actions
  (tool calls) based on observations. This is the foundation of agentic
  AI systems like LangChain Agents, AutoGPT, and watsonx Orchestrate.

  Each iteration:
    1. REASON  — LLM thinks about the current state
    2. ACT     — calls a tool (parse_log, search_kb, classify_severity)
    3. OBSERVE — we run the tool and return the result
    4. REPEAT  — until the LLM has enough context for a final answer

  This agent flow:
    Step 1: parse_log      → extract all failures from the log text
    Step 2: search_kb      → find KB matches for each failure
    Step 3: classify_severity → determine overall severity
    Step 4: stream diagnosis → LLM reasons over all context and streams output
    Step 5: parse JSON     → validate with Pydantic schema
"""

import json
import sys
import re
from typing import List, Dict
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from llm_client import LLMClient
from tools import parse_log, search_kb, classify_severity, detect_log_type, ParsedFailure
from knowledge_base import KBEntry
from schemas import DiagnosisReport, RootCause

console = Console()

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer and Log Analysis Agent.

You analyze application logs (WAS SystemOut, heap dumps, thread dumps, BVT logs, customer cases)
and produce a detailed diagnosis with root cause analysis and actionable fix recommendations.

You will be given:
- The raw log text
- Pre-extracted failure list
- Knowledge base matches for each failure
- Overall severity classification

Your job is to synthesize all this into a final diagnosis.

IMPORTANT: Your response MUST be a single valid JSON object matching this exact schema:
{
  "summary": "One-sentence summary of what happened",
  "severity": "CRITICAL | HIGH | MEDIUM | LOW",
  "log_type": "e.g. WAS SystemOut, BVT Regression, Javacore Thread Dump",
  "total_failures": <number>,
  "root_causes": [
    {
      "failure_id": "e.g. OOM-1",
      "error_type": "e.g. OutOfMemoryError",
      "affected_component": "e.g. ReportCacheManager",
      "root_cause": "Clear explanation of why this happened",
      "suggested_fix": "Specific numbered fix steps",
      "code_fix": "Optional code snippet showing the fix",
      "confidence": 0.0 to 1.0
    }
  ],
  "immediate_actions": ["Action to take right now", ...],
  "prevention_recommendations": ["Long-term improvement", ...]
}

Be specific, technical, and actionable. Do not be vague."""


def run_agent(log_text: str, llm: LLMClient, verbose: bool = True) -> DiagnosisReport:
    """
    Run the full ReAct agent loop on a log file.

    Steps:
      1. Detect log type
      2. Parse failures (deterministic — no LLM needed)
      3. Search KB for each failure (RAG)
      4. Classify severity
      5. Stream LLM diagnosis
      6. Parse + validate with Pydantic
    """

    # ── Step 1: Detect log type ─────────────────────────────────────────────
    log_type = detect_log_type(log_text)
    if verbose:
        console.print(f"\n[cyan]📂 Log type detected:[/cyan] [bold]{log_type}[/bold]")

    # ── Step 2: Parse failures ──────────────────────────────────────────────
    failures = parse_log(log_text)
    if verbose:
        console.print(f"[cyan]🔎 Failures extracted:[/cyan] [bold]{len(failures)}[/bold]")

    if not failures:
        console.print("[yellow]⚠️  No failures found in log. Log may be clean or format unrecognized.[/yellow]")

    # ── Step 3: Search KB for each failure (RAG) ────────────────────────────
    if verbose:
        console.print("[cyan]📚 Searching knowledge base...[/cyan]")

    kb_results: Dict[str, List[KBEntry]] = {}
    for failure in failures[:15]:  # cap at 15 to avoid context overflow
        search_text = f"{failure.error_type} {failure.message} {failure.context}"
        matches = search_kb(search_text)
        if matches:
            key = failure.test_id or failure.error_type
            kb_results[key] = matches

    if verbose:
        console.print(f"[cyan]📚 KB matches found:[/cyan] [bold]{len(kb_results)}[/bold]")

    # ── Step 4: Classify severity ────────────────────────────────────────────
    severity = classify_severity([f.message for f in failures])
    if verbose:
        color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue", "LOW": "green"}.get(severity, "white")
        console.print(f"[cyan]🚨 Severity classified:[/cyan] [{color}][bold]{severity}[/bold][/{color}]")

    # ── Step 5: Build context message for LLM ───────────────────────────────
    context_message = _build_context_message(log_text, failures, kb_results, severity, log_type)

    # ── Step 6: Stream LLM response ─────────────────────────────────────────
    if verbose:
        console.print("\n[green]💡 Generating diagnosis (streaming)...[/green]\n")
        console.print("─" * 70)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": context_message},
    ]

    full_response = ""
    for token in llm.stream(messages):
        if verbose:
            print(token, end="", flush=True)
        full_response += token

    if verbose:
        print()
        console.print("─" * 70)

    # ── Step 7: Parse and validate with Pydantic ────────────────────────────
    return _parse_diagnosis(full_response, len(failures), severity, log_type)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context_message(
    log_text: str,
    failures: List[ParsedFailure],
    kb_results: Dict[str, List[KBEntry]],
    severity: str,
    log_type: str,
) -> str:
    """Build the rich context message sent to the LLM."""

    # Truncate very large logs to avoid context window overflow
    # Keep first 3000 chars (header/env info) + last 5000 chars (where errors usually are)
    if len(log_text) > 8000:
        log_excerpt = log_text[:3000] + "\n\n[... middle truncated ...]\n\n" + log_text[-5000:]
    else:
        log_excerpt = log_text

    # Format failures
    failures_text = ""
    for i, f in enumerate(failures[:15], 1):
        failures_text += (
            f"\nFAILURE {i}"
            + (f" [{f.test_id}]" if f.test_id else "")
            + f"\n  Line     : {f.line_number}"
            f"\n  Type     : {f.error_type}"
            f"\n  Message  : {f.message[:200]}"
            f"\n  Context  : {f.context[:300] if f.context else 'none'}\n"
        )

    # Format KB matches
    kb_text = ""
    if kb_results:
        kb_text = "\n\nKNOWLEDGE BASE MATCHES (use these as ground truth for fixes):\n"
        for key, entries in kb_results.items():
            for entry in entries:
                kb_text += (
                    f"\n  [{entry.id}] {entry.title}"
                    f"\n  Category : {entry.category}"
                    f"\n  Root Cause: {entry.root_cause}"
                    f"\n  Fix      : {entry.fix}\n"
                )
    else:
        kb_text = "\n\nNo KB matches found — use your expert knowledge."

    return (
        f"LOG TYPE: {log_type}\n"
        f"SEVERITY: {severity}\n"
        f"TOTAL FAILURES: {len(failures)}\n\n"
        f"LOG EXCERPT:\n{log_excerpt}\n\n"
        f"EXTRACTED FAILURES ({len(failures)} total):{failures_text}"
        f"{kb_text}\n\n"
        f"Now produce the final diagnosis JSON as specified in your system instructions."
    )


def _parse_diagnosis(
    response: str,
    total_failures: int,
    severity: str,
    log_type: str,
) -> DiagnosisReport:
    """Extract and validate JSON from the LLM response using Pydantic."""
    # Try to extract JSON block from response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return DiagnosisReport(**data)
        except Exception:
            pass

    # Fallback if LLM didn't return clean JSON
    return DiagnosisReport(
        summary="Analysis complete — see streaming output above for full details.",
        severity=severity,
        log_type=log_type,
        total_failures=total_failures,
        root_causes=[],
        immediate_actions=["Review the streaming analysis output above"],
        prevention_recommendations=["Enable structured output mode for cleaner JSON"],
    )
