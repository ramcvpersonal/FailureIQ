"""
cli.py — Command Line Interface
---------------------------------
Entry point for the AI Log Analyzer.

Usage:
  python cli.py --file logs/SystemOut.log
  python cli.py --file logs/heapdump.20240917.103000.AppServer01.0001.phd
  python cli.py --file logs/javacore.20240917.103000.AppServer01.0002.txt
  python cli.py --file logs/bvt-regression.log
  python cli.py --file logs/cx-regression.log
  python cli.py --file /path/to/any/log.txt
"""

import argparse
import json
import sys
import os
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from llm_client import LLMClient
from tools import read_log_file
from agent import run_agent
from schemas import DiagnosisReport

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="🧠 FailureIQ — diagnose BVT, WAS, heap dump logs using local LLMs"
    )
    parser.add_argument(
        "--file", "-f",
        required=False,
        help="Path to log file (.log, .txt, .phd). Defaults to logs/SystemOut.log"
    )
    parser.add_argument(
        "--output", "-o",
        required=False,
        help="Save JSON report to file (optional)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress streaming output, only show final summary"
    )
    args = parser.parse_args()

    # ── Print banner ──────────────────────────────────────────────────────────
    _print_banner()

    # ── Resolve log file ──────────────────────────────────────────────────────
    log_file = args.file or "logs/SystemOut.log"
    try:
        log_text = read_log_file(log_file)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]❌ {e}[/red]")
        sys.exit(1)

    console.print(
        f"[dim]📂 Loaded:[/dim] [bold]{os.path.basename(log_file)}[/bold] "
        f"[dim]({len(log_text):,} chars)[/dim]\n"
    )

    # ── Initialize LLM ────────────────────────────────────────────────────────
    try:
        llm = LLMClient.create()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    # ── Run Agent ─────────────────────────────────────────────────────────────
    start = time.time()
    report = run_agent(log_text, llm, verbose=not args.quiet)
    elapsed = time.time() - start

    # ── Print structured summary ──────────────────────────────────────────────
    _print_report(report)

    # ── Save JSON output ──────────────────────────────────────────────────────
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report.model_dump(), f, indent=2)
        console.print(f"\n[green]✅ Report saved to:[/green] {args.output}")

    console.print(
        f"\n[dim]✅ Analysis complete in {elapsed:.1f}s | "
        f"Provider: {llm.provider} | Model: {llm.model}[/dim]\n"
    )


# ── Display Helpers ───────────────────────────────────────────────────────────

def _print_banner():
    console.print(Panel.fit(
        "[bold cyan]🧠 FailureIQ[/bold cyan]\n"
        "[dim]AI Agent — diagnoses BVT, WAS, heap dump & customer case logs[/dim]\n"
        "[dim]Powered by IBM Granite / Llama via Ollama (free, local)[/dim]",
        border_style="cyan"
    ))
    console.print()


SEVERITY_STYLES = {
    "CRITICAL": ("red", "🔴"),
    "HIGH":     ("yellow", "🟠"),
    "MEDIUM":   ("blue", "🟡"),
    "LOW":      ("green", "🟢"),
}


def _print_report(report: DiagnosisReport):
    color, icon = SEVERITY_STYLES.get(report.severity, ("white", "⚪"))

    console.print(f"\n[bold cyan]📊 DIAGNOSIS REPORT[/bold cyan]")
    console.print("─" * 70)

    # Header
    console.print(f"\n  {icon} Severity  : [{color}][bold]{report.severity}[/bold][/{color}]")
    console.print(f"  📋 Log Type  : {report.log_type}")
    console.print(f"  💥 Failures  : {report.total_failures}")
    console.print(f"\n  📝 Summary   : [bold]{report.summary}[/bold]")

    # Root Causes table
    if report.root_causes:
        console.print(f"\n[bold yellow]🔍 Root Causes:[/bold yellow]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("#",              style="dim",    width=3)
        table.add_column("Error Type",     style="red",    width=25)
        table.add_column("Component",      style="cyan",   width=28)
        table.add_column("Confidence",     style="green",  width=12)

        for i, rc in enumerate(report.root_causes, 1):
            conf_pct = f"{rc.confidence * 100:.0f}%"
            table.add_row(str(i), rc.error_type, rc.affected_component, conf_pct)
        console.print(table)

        for i, rc in enumerate(report.root_causes, 1):
            console.print(f"  [bold]{i}. {rc.error_type}[/bold] — {rc.affected_component}")
            console.print(f"     [dim]Root Cause:[/dim] {rc.root_cause}")
            console.print(f"     [green]Fix:[/green] {rc.suggested_fix.splitlines()[0]}")
            if rc.code_fix:
                console.print(f"     [dim]Code:[/dim]\n{rc.code_fix}")
            console.print()

    # Immediate actions
    if report.immediate_actions:
        console.print("[bold red]⚡ Immediate Actions:[/bold red]")
        for action in report.immediate_actions:
            console.print(f"  • {action}")

    # Prevention
    if report.prevention_recommendations:
        console.print(f"\n[bold blue]🛡️  Prevention Recommendations:[/bold blue]")
        for rec in report.prevention_recommendations:
            console.print(f"  • {rec}")

    console.print("\n" + "─" * 70)


if __name__ == "__main__":
    main()
