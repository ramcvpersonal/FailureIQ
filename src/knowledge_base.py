"""
knowledge_base.py — RAG Knowledge Base
----------------------------------------
RAG = Retrieval-Augmented Generation

INTERVIEW TALKING POINT:
  Instead of relying solely on the LLM's training data, RAG injects
  your own domain knowledge at query time. The flow is:

  1. Store known errors + fixes as "documents" in this KB
  2. When a new log arrives, find the most relevant KB entries
  3. Inject those entries into the LLM prompt as extra context
  4. LLM answers using both its training + your specific knowledge

  In production: use vector embeddings + pgvector / Pinecone / Chroma.
  Here: keyword similarity — zero dependencies, works great for logs.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class KBEntry:
    id: str
    category: str
    error_patterns: List[str]   # keywords that trigger this entry
    title: str
    root_cause: str
    fix: str
    severity: str               # CRITICAL / HIGH / MEDIUM / LOW
    affected_component: str


# ── Knowledge Base ──────────────────────────────────────────────────────────
# Think of this as your team's runbook — known issues and their solutions.
# The LLM uses these as "ground truth" context when diagnosing logs.

KNOWLEDGE_BASE: List[KBEntry] = [

    KBEntry(
        id="KB-001",
        category="Memory Leak",
        error_patterns=["OutOfMemoryError", "Java heap space", "ReportCacheManager",
                        "static", "ArrayList", "unbounded", "248,921"],
        title="Unbounded static cache causing heap exhaustion",
        root_cause=(
            "A static ArrayList (ReportCacheManager.REPORT_CACHE) is used as an in-memory cache "
            "with no eviction, expiry, or size limit. Every scheduled report adds an entry but "
            "none are ever removed. After extended uptime the list grows until it exhausts heap."
        ),
        fix=(
            "1. Replace ArrayList with a bounded cache:\n"
            "   Cache<String, ReportEntry> cache = Caffeine.newBuilder()\n"
            "       .maximumSize(1000)\n"
            "       .expireAfterWrite(1, TimeUnit.HOURS)\n"
            "       .build();\n"
            "2. Or use LinkedHashMap with removeEldestEntry() override.\n"
            "3. Add heap usage alerting at 70% threshold.\n"
            "4. Immediate fix: restart server to clear heap."
        ),
        severity="CRITICAL",
        affected_component="ReportCacheManager / ReportService",
    ),

    KBEntry(
        id="KB-002",
        category="Memory Leak",
        error_patterns=["OutOfMemoryError", "AuditLogger", "StringBuilder",
                        "static", "auditBuffer", "never flushed", "never cleared"],
        title="Static StringBuilder accumulating audit log entries",
        root_cause=(
            "AuditLogger uses a static StringBuilder as a buffer that is appended on every "
            "HTTP request but never flushed, reset, or written to disk. Over time it grows "
            "unboundedly, consuming heap proportional to total request volume."
        ),
        fix=(
            "1. Flush and reset the buffer periodically or after each write:\n"
            "   auditBuffer.setLength(0);  // reset after flush\n"
            "2. Better: use a proper logging framework (Log4j2, SLF4J) instead of a static buffer.\n"
            "3. Or write directly to file/stream without buffering in memory.\n"
            "4. Immediate fix: restart server."
        ),
        severity="CRITICAL",
        affected_component="AuditLogger / RequestFilter",
    ),

    KBEntry(
        id="KB-003",
        category="Memory Leak",
        error_patterns=["OutOfMemoryError", "SessionRegistry", "ConcurrentHashMap",
                        "SESSION_MAP", "expired sessions", "never removed", "1,892,441"],
        title="Expired HTTP sessions never evicted from session registry",
        root_cause=(
            "SessionRegistry stores HttpSession objects in a static ConcurrentHashMap on every login. "
            "Sessions are never removed on logout or timeout. Over time the map accumulates millions "
            "of stale session objects that cannot be garbage collected due to the static reference."
        ),
        fix=(
            "1. Remove session on logout:\n"
            "   SessionRegistry.SESSION_MAP.remove(sessionId);\n"
            "2. Add a scheduled cleanup job:\n"
            "   @Scheduled(fixedRate = 300_000)  // every 5 minutes\n"
            "   public void evictExpiredSessions() {\n"
            "       SESSION_MAP.entrySet().removeIf(e -> e.getValue().isExpired());\n"
            "   }\n"
            "3. Consider delegating to WAS built-in session management instead of custom registry."
        ),
        severity="CRITICAL",
        affected_component="SessionRegistry / SessionFilter",
    ),

    KBEntry(
        id="KB-004",
        category="Thread Contention",
        error_patterns=["BLOCKED", "Blocked on", "Blocked by", "monitor", "WebContainer",
                        "WSVR0605W", "hung thread", "active for"],
        title="Thread contention on shared monitor lock",
        root_cause=(
            "Multiple WebContainer threads are blocked waiting to acquire the same object monitor. "
            "One thread holds the lock while performing a long-running or blocking operation "
            "(e.g. DB query, file I/O inside a synchronized method), starving all other threads."
        ),
        fix=(
            "1. Minimize synchronized block scope — only protect the critical section, not I/O.\n"
            "2. Replace synchronized with java.util.concurrent locks (ReentrantLock, ReadWriteLock).\n"
            "3. For caches, use ConcurrentHashMap.computeIfAbsent() which is lock-free.\n"
            "4. Profile with thread dump analysis to identify the root lock holder."
        ),
        severity="HIGH",
        affected_component="WebContainer Thread Pool",
    ),

    KBEntry(
        id="KB-005",
        category="Connection Pool",
        error_patterns=["ConnectionPool", "No connections available", "pool exhaustion",
                        "waited 30000ms", "DB connections", "47/50", "48/50", "50/50"],
        title="Database connection pool exhausted",
        root_cause=(
            "All database connections are in use and new requests are timing out waiting for one. "
            "This is typically caused by: connection leaks (connections not closed after use), "
            "slow queries holding connections too long, or pool size too small for the load."
        ),
        fix=(
            "1. Check for connection leaks — ensure all connections are closed in finally blocks.\n"
            "2. Increase pool size in WAS admin console: Resources → JDBC → Data Sources → Connection Pool.\n"
            "3. Add connection pool metrics monitoring.\n"
            "4. Optimize slow queries that hold connections for extended periods."
        ),
        severity="HIGH",
        affected_component="Database Connection Pool",
    ),

    KBEntry(
        id="KB-006",
        category="Build / Test",
        error_patterns=["404-Not Found", "v3/reporting", "register", "reset",
                        "Status Code-404", "rest call"],
        title="Reporting service endpoint returning 404",
        root_cause=(
            "The reporting service REST endpoint (v3/reporting/999/register or /reset) is returning "
            "404 Not Found. This usually means the service is not deployed, the route is incorrect, "
            "or the service pod/container is not running."
        ),
        fix=(
            "1. Verify the reporting service is deployed and running:\n"
            "   oc get pods -n <namespace> | grep reporting\n"
            "2. Check the service URL and port are correct in test configuration.\n"
            "3. Check service logs for startup errors.\n"
            "4. Verify the API version path is correct (v3 vs v2)."
        ),
        severity="HIGH",
        affected_component="Reporting Service / REST API",
    ),

    KBEntry(
        id="KB-007",
        category="Build / Test",
        error_patterns=["Cannot delete the project", "active jobs", "Stop all running jobs",
                        "projects_api_delete_project_active_job", "500"],
        title="Project deletion blocked by active jobs",
        root_cause=(
            "A test is attempting to delete a project that still has active/running jobs. "
            "The API correctly rejects this to prevent data loss. "
            "This is typically a test cleanup race condition."
        ),
        fix=(
            "1. Before deleting a project in tests, wait for all jobs to complete:\n"
            "   waitForJobsToComplete(projectId, timeout=300s);\n"
            "2. Or cancel active jobs before deletion:\n"
            "   cancelAllJobs(projectId);\n"
            "   deleteProject(projectId);\n"
            "3. Add retry logic with exponential backoff for cleanup steps."
        ),
        severity="MEDIUM",
        affected_component="Project API / Test Cleanup",
    ),

    KBEntry(
        id="KB-008",
        category="GC / Performance",
        error_patterns=["GC overhead", "major GC", "minor GC", "pause", "4200ms",
                        "GC frequency", "near zero reclaim"],
        title="GC thrashing — near-zero heap reclamation",
        root_cause=(
            "GC is running frequently but reclaiming almost no memory (near-zero reclaim). "
            "This means nearly all objects are strongly reachable and cannot be collected. "
            "This is a classic symptom of a memory leak via a GC root (static field)."
        ),
        fix=(
            "1. Take a heap dump and analyze with IBM Memory Analyzer Tool (MAT) or Eclipse MAT.\n"
            "2. Look for dominant object types that grow over time.\n"
            "3. Trace the retention path back to the GC root (usually a static field).\n"
            "4. Fix the leak source — add eviction, use WeakReference, or redesign the cache."
        ),
        severity="HIGH",
        affected_component="JVM Garbage Collector",
    ),
]


def search_knowledge_base(query: str, top_k: int = 3) -> List[KBEntry]:
    """
    Keyword-based similarity search over the knowledge base.

    INTERVIEW TALKING POINT:
      In production this would be vector similarity search:
        1. Embed the query text with text-embedding-3-small
        2. Compare cosine similarity against pre-embedded KB entries
        3. Return top-K closest entries
      Keyword matching is dependency-free and works well for structured logs.
    """
    query_lower = query.lower()

    scored = []
    for entry in KNOWLEDGE_BASE:
        score = sum(
            1 for kw in entry.error_patterns
            if kw.lower() in query_lower
        )
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
