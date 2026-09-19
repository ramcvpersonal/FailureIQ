# 🧠 FailureIQ

> AI Agent that reads BVT logs, WAS heap dumps, thread dumps, and customer cases —
> then diagnoses failures, finds root causes, and suggests exact fixes.
> Powered by **IBM Granite / Llama via Ollama** (free, runs locally — no API key needed).

---

## What it does

```
You drop a log file
        ↓
FailureIQ reads it (SystemOut.log / heapdump / javacore / BVT log)
        ↓
Agent extracts all failures (parse_log)
        ↓
Searches knowledge base for known fixes (RAG — search_kb)
        ↓
Classifies overall severity (CRITICAL / HIGH / MEDIUM / LOW)
        ↓
LLM streams diagnosis word-by-word (streaming)
        ↓
Returns structured report: root cause + fix + code snippet + prevention
```

---

## Project Structure

```
FailureIQ/
├── src/
│   ├── cli.py            ← Entry point — python cli.py --file <log>
│   ├── demo.py           ← Runs all sample logs automatically
│   ├── agent.py          ← ReAct agent loop (Reason → Act → Observe)
│   ├── llm_client.py     ← LLM abstraction (Ollama + OpenAI fallback)
│   ├── tools.py          ← Agent tools: parse_log, search_kb, classify_severity
│   ├── knowledge_base.py ← RAG knowledge base of known errors + fixes
│   └── schemas.py        ← Pydantic structured output schema
├── logs/
│   ├── SystemOut.log                               ← WAS application log
│   ├── heapdump.20240917.103000.AppServer01.0001.phd ← Heap dump
│   ├── javacore.20240917.103000.AppServer01.0002.txt ← Thread dump
│   ├── bvt-regression.log                          ← Real BVT regression log
│   ├── cx-regression.log                           ← Real CX regression log
│   ├── bvt-sample.log                              ← Sample BVT log
│   └── customer-case.log                           ← Sample P1 customer case
├── requirements.txt
└── .env.example
```

---

## Quick Start

### Option 1 — Free (Recommended): Ollama + IBM Granite

```bash
# 1. Install Ollama
brew install ollama

# 2. Start Ollama server
ollama serve

# 3. Pull IBM Granite (free, runs locally)
ollama pull granite3.1-dense

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Analyze a log
python src/cli.py --file logs/SystemOut.log
python src/cli.py --file logs/heapdump.20240917.103000.AppServer01.0001.phd
python src/cli.py --file logs/bvt-regression.log
```

### Option 2 — OpenAI (Paid fallback)

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
python src/cli.py --file logs/SystemOut.log
```

---

## Usage

```bash
# Analyze any log file
python src/cli.py --file logs/SystemOut.log
python src/cli.py --file logs/heapdump.20240917.103000.AppServer01.0001.phd
python src/cli.py --file logs/javacore.20240917.103000.AppServer01.0002.txt
python src/cli.py --file logs/bvt-regression.log
python src/cli.py --file /path/to/your/own/log.txt

# Save JSON report to file
python src/cli.py --file logs/SystemOut.log --output report.json

# Run full demo (all log types)
python src/demo.py
```

---

## Sample Output

```
╭─────────────────────────────────────────────────╮
│  🧠 FailureIQ                                   │
│  AI Agent — diagnoses BVT, WAS, heap dump logs  │
│  Powered by IBM Granite / Llama via Ollama       │
╰─────────────────────────────────────────────────╯

✅ Using Ollama (local) → model: granite3.1-dense
📂 Loaded: SystemOut.log (8,921 chars)

📂 Log type detected: was_systemout
🔎 Failures extracted: 12
📚 KB matches found: 4
🚨 Severity classified: CRITICAL

💡 Generating diagnosis (streaming)...

──────────────────────────────────────────────────────────────────────
{
  "summary": "Server crashed 3 times in 6 hours due to unbounded static
              cache in ReportCacheManager exhausting JVM heap",
  "severity": "CRITICAL",
  ...
}
──────────────────────────────────────────────────────────────────────

📊 DIAGNOSIS REPORT
──────────────────────────────────────────────────────────────────────

  🔴 Severity  : CRITICAL
  📋 Log Type  : was_systemout
  💥 Failures  : 12

  📝 Summary   : Server crashed 3 times in 6 hours due to unbounded
                 static ArrayList in ReportCacheManager exhausting heap

🔍 Root Causes:
  #   Error Type              Component                 Confidence
  1   OutOfMemoryError        ReportCacheManager        95%
  2   OutOfMemoryError        AuditLogger               91%
  3   OutOfMemoryError        SessionRegistry           88%

⚡ Immediate Actions:
  • Restart AppServer01 to restore service
  • Increase -Xmx to 4096m as temporary relief
  • Deploy hotfix for ReportCacheManager before next restart

🛡️  Prevention Recommendations:
  • Replace static ArrayList with Caffeine bounded cache (max=1000, TTL=1h)
  • Add heap alerting at 70% threshold
  • Code review policy: no static collections without eviction
  • Enable WAS PMI metrics to Grafana
```

---

## LLM Concepts Demonstrated

| Concept | Where |
|---|---|
| **Streaming** | `llm_client.py` — tokens appear word-by-word |
| **RAG** | `knowledge_base.py` — KB injected into LLM prompt |
| **Structured Output** | `schemas.py` — Pydantic validates LLM JSON response |
| **ReAct Agent Loop** | `agent.py` — Reason → Act → Observe pattern |
| **Provider Abstraction** | `llm_client.py` — Ollama or OpenAI, same interface |
| **Tool Calling** | `tools.py` — parse_log, search_kb, classify_severity |
| **Prompt Engineering** | `agent.py` — system prompt tuned for log analysis |

---

## Interview Talking Points

1. **"Why Ollama?"** — Free, local, no API key. IBM Granite runs on-device. Same OpenAI SDK works for both — just change the base URL.

2. **"What is RAG?"** — Instead of relying only on the LLM's training data, we inject our team's runbook (known errors + fixes) directly into the prompt. The LLM answers using both.

3. **"What is streaming?"** — Chunked HTTP transfer. The model sends tokens as it generates them. We print immediately — same as ChatGPT's typing effect. Critical for perceived performance.

4. **"What is the ReAct pattern?"** — Reason + Act. The agent reasons about the log, calls tools (parse, search, classify), observes results, then produces a final answer. Foundation of LangChain Agents and watsonx Orchestrate.

5. **"Why Pydantic?"** — LLMs can return malformed JSON. Pydantic validates the schema at runtime and gives you a typed Python object — safe to use in production pipelines.

---

## Supported Log Formats

| Format | Example |
|---|---|
| WAS SystemOut.log | `logs/SystemOut.log` |
| JVM Heap Dump (.phd) | `heapdump.20240917.103000.AppServer01.0001.phd` |
| Javacore / Thread Dump | `javacore.20240917.103000.AppServer01.0002.txt` |
| Jenkins BVT / Regression | `logs/bvt-regression.log` |
| Customer Support Case | `logs/customer-case.log` |
| Any plain text log | `*.log`, `*.txt` |
