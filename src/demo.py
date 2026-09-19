"""
demo.py — FailureIQ Full Demo
------------------------------
Runs all sample log files through the agent automatically.
Great for live interview demos.

Usage: python demo.py
"""

import os
import sys
import time
import json

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

sys.path.insert(0, os.path.dirname(__file__))

from llm_client import LLMClient
from tools import read_log_file
from agent import run_agent

console = Console()

DEMO_FILES = [
    {
        "file": "logs/SystemOut.log",
        "label": "WAS SystemOut Log",
        "desc": "WebSphere Application Server — 3 OOM crashes with heap leak analysis",
    },
    {
        "file": "logs/heapdump.20240917.103000.AppServer01.0001.phd",
        "label": "Heap Dump (.phd)",
        "desc": "JVM heap dump — static cache leak, 248,921 objects, GC root analysis",
    },
    {
        "file": "logs/javacore.20240917.103000.AppServer01.0002.txt",
        "label": "Javacore / Thread Dump",
        "desc": "Thread dump — blocked threads, lock contention, hung thread detection",
    },
    {
        "file": "logs/bvt-sample.log",
        "label": "BVT Regression Log",
        "desc": "Build Verification Test — 6 failures across Auth, DB, API, Payment modules",
    },
    {
        "file": "logs/customer-case.log",
        "label": "Customer Support Case (P1)",
        "desc": "Production outage — CORS failure + DB credential rotation after deployment",
    },
]


def main():
    console.print(Panel.fit(
        "[bold cyan]🧠 FailureIQ — Full Demo[/bold cyan]\n"
        "[dim]Running all log types through the AI diagnosis agent[/dim]\n"
        "[dim]Powered by IBM Granite / Llama via Ollama (free)[/dim]",
        border_style="cyan",
    ))

    # Init LLM once — reuse across all demos
    try:
        llm = LLMClient.create()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    results = []

    for i, demo in enumerate(DEMO_FILES, 1):
        if not os.path.exists(demo["file"]):
            console.print(f"[yellow]⚠️  Skipping {demo['file']} — file not found[/yellow]")
            continue

        console.print(Rule(f"[bold yellow]Demo {i}/{len(DEMO_FILES)}: {demo['label']}[/bold yellow]"))
        console.print(f"[dim]{demo['desc']}[/dim]\n")

        log_text = read_log_file(demo["file"])
        start = time.time()
        report = run_agent(log_text, llm, verbose=True)
        elapsed = time.time() - start

        results.append({
            "file": demo["file"],
            "label": demo["label"],
            "severity": report.severity,
            "total_failures": report.total_failures,
            "summary": report.summary,
            "elapsed_s": round(elapsed, 1),
        })

        if i < len(DEMO_FILES):
            console.print("\n[dim]Next demo in 2 seconds...[/dim]")
            time.sleep(2)

    # Final summary table
    console.print(Rule("[bold cyan]Demo Summary[/bold cyan]"))
    for r in results:
        sev_color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue", "LOW": "green"}.get(r["severity"], "white")
        console.print(
            f"  [{sev_color}]{r['severity']:8}[/{sev_color}]  "
            f"[bold]{r['label']:30}[/bold]  "
            f"{r['total_failures']:3} failures  "
            f"[dim]{r['elapsed_s']}s[/dim]"
        )

    console.print(f"\n[bold green]✅ FailureIQ demo complete![/bold green]\n")


if __name__ == "__main__":
    main()
