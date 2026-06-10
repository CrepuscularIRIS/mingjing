"""``SourcesEvidenceMixin`` — sources, evidence chunks, qc reports, revision tasks.

All shared-connection access is serialized by the ONE canonical ``_WRITE_LOCK``
imported from :mod:`mingjing.db._base`.
"""

import time
from typing import Any

from ._base import _WRITE_LOCK


class SourcesEvidenceMixin:
    """``sources`` / ``evidence_chunks`` / ``qc_reports`` / ``revision_tasks``
    operations mixed into :class:`mingjing.db.Database`."""

    # ---- sources ----------------------------------------------------------
    def append_source(self, source: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO sources (id, run_id, url, title, source_type, source_mode,"
                " fetched_at, content_hash, raw_text, meta_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source["id"],
                    source["run_id"],
                    source.get("url"),
                    source.get("title"),
                    source.get("source_type"),
                    source.get("source_mode"),
                    source.get("fetched_at"),
                    source.get("content_hash"),
                    source.get("raw_text"),
                    source.get("meta_json", "{}"),
                    time.time(),
                ),
            )
            self._conn.commit()

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with _WRITE_LOCK:
            cur = self._conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
            row = cur.fetchone()
        return None if row is None else dict(row)

    def sources_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return all source rows for a run, ordered by creation time.

        Args:
            run_id: The run identifier.

        Returns:
            A list of source row dicts ordered by ``created_at ASC``.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM sources WHERE run_id = ? ORDER BY created_at ASC", (run_id,)
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ---- evidence chunks --------------------------------------------------
    def append_evidence_chunk(self, chunk: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO evidence_chunks (id, run_id, source_id, locator, text,"
                " content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk["id"],
                    chunk["run_id"],
                    chunk.get("source_id"),
                    chunk.get("locator"),
                    chunk["text"],
                    chunk.get("content_hash"),
                    time.time(),
                ),
            )
            self._conn.commit()

    # ---- qc reports -------------------------------------------------------
    def append_qc_report(self, report: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO qc_reports (id, run_id, claim_id, round, verdict,"
                " issues_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    report["id"],
                    report["run_id"],
                    report.get("claim_id"),
                    int(report.get("round", 0)),
                    report["verdict"],
                    report.get("issues_json", "[]"),
                    time.time(),
                ),
            )
            self._conn.commit()

    # ---- revision tasks ---------------------------------------------------
    def append_revision_task(self, task: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO revision_tasks (id, run_id, claim_id, assignee, issue_code,"
                " instruction, status, round, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task["id"],
                    task["run_id"],
                    task.get("claim_id"),
                    task["assignee"],
                    task.get("issue_code"),
                    task.get("instruction"),
                    task.get("status", "open"),
                    int(task.get("round", 0)),
                    time.time(),
                ),
            )
            self._conn.commit()
