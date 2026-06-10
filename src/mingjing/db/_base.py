"""Base layer for the SQLite source-of-truth: lock, schema, and ``_BaseDatabase``.

Design discipline (per plan Task 3 / spec D1):
- WAL journal mode + ``busy_timeout=5000`` so readers (FastAPI polling) never
  block the single writer.
- A module-level ``threading.Lock`` serializes every shared-connection access
  (reads and writes) — single-connection discipline even though the connection
  is opened with ``check_same_thread=False``.
- Claims are append-only: a claim is never UPDATEd in place; a revision inserts a
  new row with an incremented ``version`` (supersede-by-insert).
- ``sources`` carries a ``source_mode`` column (LIVE | CACHED) for the provenance
  badge.

The ``Database`` class is assembled in :mod:`mingjing.db` by mixing
:class:`_BaseDatabase` with the per-table mixins. Every mixin module imports the
ONE canonical ``_WRITE_LOCK`` from this module, so all references share a single
Lock object (the single-writer discipline depends on this).
"""

import sqlite3
import threading

# Single global write lock — enforces the single-writer discipline across threads.
_WRITE_LOCK = threading.Lock()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    category TEXT,
    competitors_json TEXT NOT NULL,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    created_at REAL NOT NULL,
    domain TEXT,
    depth TEXT NOT NULL DEFAULT 'quick',
    market_scope TEXT,
    max_competitors INTEGER,
    seed_competitors_json TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    rowid_pk INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    competitor TEXT,
    schema_field TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    based_on_json TEXT NOT NULL DEFAULT '[]',
    evidence_strength TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    produced_by TEXT,
    note TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_chunks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT,
    locator TEXT,
    text TEXT NOT NULL,
    content_hash TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    source_type TEXT,
    source_mode TEXT,            -- LIVE | CACHED
    fetched_at REAL,
    content_hash TEXT,
    raw_text TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS qc_reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    claim_id TEXT,
    round INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL,
    issues_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS revision_tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    claim_id TEXT,
    assignee TEXT NOT NULL,
    issue_code TEXT,
    instruction TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    round INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent TEXT,
    node TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent TEXT,
    model TEXT,
    prompt_json TEXT NOT NULL DEFAULT '[]',
    output_text TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS syntheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    referenced_claim_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);

-- Indexes on the run_id column of every hot child table. The ``*_for_run``
-- read paths all filter by run_id; without these SQLite full-table-scans every
-- table on each FastAPI poll. ``IF NOT EXISTS`` keeps init_schema idempotent on
-- pre-existing DBs (additive, safe). Composite (run_id, id) indexes cover the
-- ORDER BY id queries (trace) and the per-claim-id grouping.
CREATE INDEX IF NOT EXISTS idx_claims_run_id ON claims (run_id);
CREATE INDEX IF NOT EXISTS idx_claims_run_id_id ON claims (run_id, id);
CREATE INDEX IF NOT EXISTS idx_sources_run_id ON sources (run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_chunks_run_id ON evidence_chunks (run_id);
CREATE INDEX IF NOT EXISTS idx_qc_reports_run_id ON qc_reports (run_id);
CREATE INDEX IF NOT EXISTS idx_revision_tasks_run_id ON revision_tasks (run_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_run_id_id ON trace_events (run_id, id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run_id ON llm_calls (run_id);
CREATE INDEX IF NOT EXISTS idx_syntheses_run_id ON syntheses (run_id);
"""


# Every table that carries a ``run_id`` (or, for runs, ``id``) keyed to a
# run. ``delete_run`` purges all of these so no orphaned child rows survive a
# run deletion. Kept here so a future table is a one-line addition.
_RUN_CHILD_TABLES = (
    "claims",
    "sources",
    "evidence_chunks",
    "qc_reports",
    "revision_tasks",
    "trace_events",
    "llm_calls",
    "syntheses",
)


class _BaseDatabase:
    """Thin wrapper around a single shared sqlite3 connection."""

    def __init__(self, path: str, *, read_only: bool = False) -> None:
        """Open the SQLite file at ``path``.

        Args:
            path: SQLite file path.
            read_only: Open in TRUE read-only mode (SQLite URI ``mode=ro`` plus
                ``PRAGMA query_only=ON``) — every write attempt fails at the
                engine level with ``sqlite3.OperationalError``, so an audit
                tool's "read-only" claim is enforced by SQLite itself, not by
                convention. Used by ``scripts/audit_verbatim.py``; the
                production runtime keeps the default read-write single-writer
                connection.
        """
        self._path = path
        self._read_only = read_only
        if read_only:
            # mode=ro also refuses to CREATE a missing file — an audit can
            # never conjure an empty database into existence.
            self._conn = sqlite3.connect(
                f"file:{path}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout=5000;")
            # Belt & braces on top of mode=ro (blocks writes even via any
            # path that might bypass the URI flag).
            self._conn.execute("PRAGMA query_only=ON;")
            return
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.commit()

    # ---- schema -----------------------------------------------------------
    def init_schema(self) -> None:
        with _WRITE_LOCK:
            self._conn.executescript(_SCHEMA)
            self._migrate_runs_domain()
            self._migrate_runs_depth()
            self._migrate_runs_discovery()
            self._migrate_claims_note()
            self._conn.commit()

    def _migrate_runs_domain(self) -> None:
        """Idempotently add the ``runs.domain`` column on a pre-existing DB.

        Caller MUST hold _WRITE_LOCK; this method accesses self._conn directly
        and must not re-acquire the (non-reentrant) lock.

        ``CREATE TABLE IF NOT EXISTS`` is a no-op on an already-existing table, so
        an older data DB created before the ``domain`` column would lack it and
        ``create_run`` would raise ``OperationalError``. SQLite has no
        ``ADD COLUMN IF NOT EXISTS``, so we check ``PRAGMA table_info`` and
        ``ALTER TABLE`` only when the column is absent (idempotent).
        """
        cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "domain" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN domain TEXT")

    def _migrate_runs_depth(self) -> None:
        """Idempotently add the ``runs.depth`` column on a pre-existing DB.

        Caller MUST hold _WRITE_LOCK; this method accesses self._conn directly
        and must not re-acquire the (non-reentrant) lock.

        Mirrors ``_migrate_runs_domain``: checks ``PRAGMA table_info`` and only
        runs the ``ALTER TABLE`` when the column is absent.  The default
        ``'quick'`` is applied by SQLite for all existing rows.
        """
        cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "depth" not in cols:
            self._conn.execute(
                "ALTER TABLE runs ADD COLUMN depth TEXT NOT NULL DEFAULT 'quick'"
            )

    def _migrate_claims_note(self) -> None:
        """Idempotently add the ``claims.note`` column on a pre-existing DB.

        Caller MUST hold _WRITE_LOCK. Mirrors ``_migrate_runs_domain``. The column
        is nullable: machine-produced claims leave it NULL; only a human
        correction (HITL) sets a reviewer rationale. Additive + advisory — it
        never enters scoring/QA/admission.
        """
        cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(claims)")}
        if "note" not in cols:
            self._conn.execute("ALTER TABLE claims ADD COLUMN note TEXT")

    def _migrate_runs_discovery(self) -> None:
        """Idempotently add the Discovery-Mode columns on a pre-existing DB.

        Caller MUST hold _WRITE_LOCK. Mirrors ``_migrate_runs_domain``: each
        column is added only when absent. These carry the Discovery-Mode inputs
        (``market_scope``, ``max_competitors``, ``seed_competitors_json``) so the
        runner can run the bounded discovery pre-step for runs created with an
        empty competitor list. All are nullable — Directed-Mode runs leave them
        unset and behave exactly as before.
        """
        cols = {row["name"] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "market_scope" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN market_scope TEXT")
        if "max_competitors" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN max_competitors INTEGER")
        if "seed_competitors_json" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN seed_competitors_json TEXT")

    def pragma(self, name: str) -> str:
        # PRAGMA names cannot be bound as ``?`` parameters in SQLite, so an
        # f-string is required here.  Callers must NEVER pass user-supplied input.
        with _WRITE_LOCK:
            cur = self._conn.execute(f"PRAGMA {name};")
            row = cur.fetchone()
        return "" if row is None else str(row[0])
