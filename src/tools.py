"""
tools.py — Agent Tool Implementations
---------------------------------------
These are the functions the AI Agent calls during its reasoning loop.

INTERVIEW TALKING POINT:
  Tool/Function Calling lets the LLM decide WHEN to call a function
  and WHAT arguments to pass. The LLM outputs a structured request
  saying which tool to call — our Python code executes it and feeds
  the result back. The LLM never runs code directly — it only instructs.

  ReAct pattern (Reason + Act):
    Agent reads log → calls parse_log
    → sees failures → calls search_kb
    → gets KB matches → calls classify_severity
    → produces final structured diagnosis
"""

import re
import os
from dataclasses import dataclass
from typing import List, Optional, Dict
from knowledge_base import search_knowledge_base, KBEntry


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ParsedFailure:
    line_number: int
    error_type: str
    message: str
    context: str
    test_id: str = ""


# ── Tool: read_log_file ───────────────────────────────────────────────────────

def read_log_file(file_path: str) -> str:
    """
    Read a .log, .txt, or .phd file from disk.
    Supports any plain-text log format.
    """
    resolved = os.path.abspath(file_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"File not found: {resolved}")

    ext = os.path.splitext(resolved)[1].lower()
    supported = {".log", ".txt", ".phd", ""}
    if ext not in supported:
        raise ValueError(f"Unsupported file type '{ext}'. Use .log, .txt, or .phd")

    with open(resolved, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ── Tool: parse_log ───────────────────────────────────────────────────────────

# Patterns that indicate a failure line
FAILURE_PATTERNS = re.compile(
    r"\bFAIL\b|\bERROR\b|Exception|FATAL|OutOfMemoryError|"
    r"WSVR0605W|CWWKE0701E|SRVE0777E|heapdump|NullPointer|"
    r"BUILD FAILURE|Tests run.*Failures|LEAK SUSPECT",
    re.IGNORECASE
)

def parse_log(log_text: str) -> List[ParsedFailure]:
    """
    Extract all failure/error lines from raw log text with context.

    Works with:
      - WAS SystemOut.log format
      - Jenkins BVT/regression log format
      - Java heap dump / javacore format
      - Generic log formats
    """
    lines = log_text.splitlines()
    failures: List[ParsedFailure] = []
    seen: set[str] = set()  # deduplicate identical messages

    for i, line in enumerate(lines):
        if not FAILURE_PATTERNS.search(line):
            continue

        # Grab up to 5 context lines after the failure
        context_lines = [
            l.strip() for l in lines[i + 1: i + 6]
            if l.strip() and not l.strip().startswith("#")
        ]

        # Extract test ID if present e.g. [AUTH-004] or WSVR0605W
        test_id = ""
        tid_match = re.search(r"\[([A-Z]+-\d+)\]|WSVR\d+\w|CWWKE\d+\w|SRVE\d+\w", line)
        if tid_match:
            test_id = tid_match.group(0).strip("[]")

        msg_key = line.strip()[:120]  # dedup key
        if msg_key in seen:
            continue
        seen.add(msg_key)

        failures.append(ParsedFailure(
            line_number=i + 1,
            error_type=_classify_error_type(line),
            message=line.strip(),
            context="\n".join(context_lines),
            test_id=test_id,
        ))

    return failures


def _classify_error_type(line: str) -> str:
    """Classify the type of error from a log line."""
    line_lower = line.lower()
    if "outofmemoryerror" in line_lower:
        return "OutOfMemoryError"
    if "nullpointerexception" in line_lower:
        return "NullPointerException"
    if "heapdump" in line_lower or "jvmdump" in line_lower:
        return "HeapDump Triggered"
    if "leak suspect" in line_lower:
        return "Memory Leak"
    if "wsvr0605w" in line_lower or "hung thread" in line_lower or "active for" in line_lower:
        return "Hung Thread"
    if "connectionpool" in line_lower or "no connections" in line_lower:
        return "Connection Pool Exhausted"
    if "gc overhead" in line_lower or "major gc" in line_lower:
        return "GC Overhead"
    if "blocked on" in line_lower or "blocked by" in line_lower:
        return "Thread Contention"
    if "404" in line:
        return "HTTP 404 Not Found"
    if "500" in line or "internal server error" in line_lower:
        return "HTTP 500 Internal Error"
    if "build failure" in line_lower:
        return "Build Failure"
    if "cwwke0701e" in line_lower:
        return "WAS Framework Error"
    return "Unknown Error"


# ── Tool: search_kb ───────────────────────────────────────────────────────────

def search_kb(error_text: str) -> List[KBEntry]:
    """Search the knowledge base for entries matching the error text."""
    return search_knowledge_base(error_text, top_k=3)


# ── Tool: classify_severity ───────────────────────────────────────────────────

def classify_severity(errors: List[str]) -> str:
    """
    Rule-based severity classification.
    Returns CRITICAL / HIGH / MEDIUM / LOW.
    """
    combined = " ".join(errors).lower()

    if any(kw in combined for kw in [
        "outofmemoryerror", "server crashed", "server down",
        "manual intervention", "automatic restart disabled",
        "heapdump", "leak suspect"
    ]):
        return "CRITICAL"

    if any(kw in combined for kw in [
        "hung thread", "connection pool", "no connections",
        "gc overhead", "blocked", "wsvr0605w"
    ]):
        return "HIGH"

    if any(kw in combined for kw in [
        "404", "warn", "timeout", "retry", "build failure"
    ]):
        return "MEDIUM"

    return "LOW"


# ── Tool: detect_log_type ─────────────────────────────────────────────────────

def detect_log_type(log_text: str) -> str:
    """
    Auto-detect what kind of log file this is.
    Returns: 'was_systemout' | 'javacore' | 'heapdump' | 'bvt' | 'generic'
    """
    sample = log_text[:2000].lower()
    if "jvmdump" in sample or "heapdump" in sample or "phd" in sample:
        if "0section" in sample or "3xmthreadinfo" in sample:
            return "javacore"
        return "heapdump"
    if "websphere application server" in sample or "systemout" in sample or "wsvr" in sample:
        return "was_systemout"
    if "gradle" in sample or "jenkins" in sample or "tests run" in sample or "bvt" in sample:
        return "bvt"
    return "generic"
