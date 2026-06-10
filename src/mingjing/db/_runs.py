"""``RunMixin`` — the ``runs`` table read/write helpers.

All shared-connection access is serialized by the ONE canonical ``_WRITE_LOCK``
imported from :mod:`mingjing.db._base`, so every mixin references the same Lock.
"""

import json
import time
import uuid
from typing import Any

from ._base import _RUN_CHILD_TABLES, _WRITE_LOCK


class RunMixin:
    """``runs`` table operations mixed into :class:`mingjing.db.Database`."""

    def create_run(
        self,
        *,
        category: str,
        competitors: list[str],
        goal: str,
        domain: str | None = None,
        depth: str = "quick",
        market_scope: str | None = None,
        max_competitors: int | None = None,
        seed_competitors: list[str] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        seed_json = json.dumps(seed_competitors) if seed_competitors else None
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO runs"
                " (id, category, competitors_json, goal, status, created_at, domain, depth,"
                "  market_scope, max_competitors, seed_competitors_json)"
                " VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)",
                (
                    run_id, category, json.dumps(competitors), goal, time.time(),
                    domain, depth, market_scope, max_competitors, seed_json,
                ),
            )
            self._conn.commit()
        return run_id

    def update_run_competitors(self, run_id: str, competitors: list[str]) -> None:
        """Persist the competitor list for a run (used by Discovery Mode).

        The runner calls this after the bounded discovery pre-step populates an
        initially-empty competitor list, so the API's ``/runs`` views and report
        header reflect the discovered competitors. Like ``set_run_status`` this is
        a deliberate mutation of the runs row (claims remain append-only).
        """
        with _WRITE_LOCK:
            self._conn.execute(
                "UPDATE runs SET competitors_json = ? WHERE id = ?",
                (json.dumps(competitors), run_id),
            )
            self._conn.commit()

    def run_exists(self, run_id: str) -> bool:
        """Return True if a run with the given id exists in the runs table."""
        with _WRITE_LOCK:
            cur = self._conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,))
            row = cur.fetchone()
        return row is not None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return the run row with ``competitors`` decoded, or ``None`` if absent.

        Args:
            run_id: The run identifier.

        Returns:
            A dict with keys ``id, category, competitors (list), goal, status,
            created_at, domain, depth`` — the ``competitors_json`` column is
            decoded into the ``competitors`` list, ``domain`` is ``None`` when
            the run did not request a specific schema domain, and ``depth``
            defaults to ``"quick"`` for rows that pre-date the depth column.
            Returns ``None`` when no such run exists.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            row = cur.fetchone()
        if row is None:
            return None
        record = dict(row)
        try:
            competitors = json.loads(record.get("competitors_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            competitors = []
        try:
            seed_competitors = json.loads(record.get("seed_competitors_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            seed_competitors = []
        return {
            "id": record["id"],
            "category": record.get("category"),
            "competitors": competitors,
            "goal": record.get("goal"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "domain": record.get("domain"),
            "depth": record.get("depth", "quick"),
            "market_scope": record.get("market_scope"),
            "max_competitors": record.get("max_competitors"),
            "seed_competitors": seed_competitors,
        }

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent runs newest-first with a passed-claims count.

        Each returned dict carries ``run_id, category, competitors (decoded
        list), goal, status, created_at, passed_claims`` where
        ``passed_claims`` is the number of LATEST-version claims with
        ``status == "pass"`` for that run. The passed count is computed in a
        Python loop over :meth:`latest_claims_for_run` for each listed run (an
        N+1 read), which resolves the highest version per claim id so revisions
        (supersede-by-insert) are counted exactly once at their latest state.

        Args:
            limit: Maximum number of runs to return (newest-first).

        Returns:
            A list of run summary dicts, newest-first.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT id, category, competitors_json, goal, status, created_at, domain, depth"
                " FROM runs ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            )
            raw_rows = cur.fetchall()
        runs: list[dict[str, Any]] = []
        for row in raw_rows:
            record = dict(row)
            try:
                competitors = json.loads(record.get("competitors_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                competitors = []
            passed_claims = sum(
                1
                for claim in self.latest_claims_for_run(record["id"])
                if claim.get("status") == "pass"
            )
            runs.append(
                {
                    "run_id": record["id"],
                    "category": record.get("category"),
                    "competitors": competitors,
                    "goal": record.get("goal"),
                    "status": record.get("status"),
                    "created_at": record.get("created_at"),
                    "domain": record.get("domain"),
                    "depth": record.get("depth", "quick"),
                    "passed_claims": passed_claims,
                }
            )
        return runs

    def set_run_status(self, run_id: str, status: str) -> None:
        """Update a run's ``status`` column (the only mutable column on runs).

        Guarded by the single-writer ``_WRITE_LOCK`` like every other write.

        Args:
            run_id: The run identifier.
            status: The new status value (e.g. ``running``/``complete``/
                ``partial``/``error``).
        """
        with _WRITE_LOCK:
            self._conn.execute(
                "UPDATE runs SET status = ? WHERE id = ?", (status, run_id)
            )
            self._conn.commit()

    # Mirror of the module-level child-table tuple so existing call sites that
    # read ``self._RUN_CHILD_TABLES`` keep working (the attribute is preserved on
    # the assembled Database class).
    _RUN_CHILD_TABLES = _RUN_CHILD_TABLES

    def delete_run(self, run_id: str) -> None:
        """Delete a run and ALL of its child rows across every keyed table.

        Hard-deletes the ``runs`` row plus every row keyed by ``run_id`` in the
        child tables (claims, sources, evidence_chunks, qc_reports,
        revision_tasks, trace_events, llm_calls, syntheses). Unlike the
        append-only claim discipline, this is a deliberate destructive purge used
        for demo-DB hygiene (e.g. discarding rejected best-of-N attempts), not a
        runtime path. All deletes run under a single ``_WRITE_LOCK`` acquisition
        in one transaction so a run is never left half-deleted.

        Args:
            run_id: The run identifier to purge. A run_id with no rows is a no-op.
        """
        with _WRITE_LOCK:
            for table in self._RUN_CHILD_TABLES:
                self._conn.execute(
                    f"DELETE FROM {table} WHERE run_id = ?", (run_id,)
                )
            self._conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            self._conn.commit()

    def reap_stale_running(self, older_than_s: float) -> list[str]:
        """Mark orphaned ``running`` runs as ``error`` and return their ids.

        Server-side recovery for runs whose executing process died mid-loop and
        so are stuck at ``status='running'`` forever. Selects runs that are still
        ``running`` and were created more than ``older_than_s`` seconds ago, flips
        them to ``error`` in one transaction under the single-writer lock, and
        returns the affected run ids.

        This is NOT invoked destructively on import; call it from a startup hook
        or manually with a sane threshold (e.g. ``3600`` for 1h) — the frontend's
        client-side 1h stale label is the cosmetic counterpart to this recovery.

        Args:
            older_than_s: Age threshold in seconds; only runs older than this
                (by ``created_at``) are reaped.

        Returns:
            The list of run ids that were transitioned from ``running`` to
            ``error`` (empty when none qualified).
        """
        cutoff = time.time() - older_than_s
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT id FROM runs WHERE status = 'running' AND created_at < ?",
                (cutoff,),
            )
            stale_ids = [row["id"] for row in cur.fetchall()]
            if stale_ids:
                self._conn.executemany(
                    "UPDATE runs SET status = 'error' WHERE id = ?",
                    [(rid,) for rid in stale_ids],
                )
                self._conn.commit()
        return stale_ids
