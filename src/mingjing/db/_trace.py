"""``TraceLlmSynthesisMixin`` — trace events, llm calls, and (append-only) syntheses.

All shared-connection access is serialized by the ONE canonical ``_WRITE_LOCK``
imported from :mod:`mingjing.db._base`.
"""

import json
import time
from typing import Any

from ._base import _WRITE_LOCK


class TraceLlmSynthesisMixin:
    """``trace_events`` / ``llm_calls`` / ``syntheses`` operations mixed into
    :class:`mingjing.db.Database`."""

    # ---- trace / llm (write helpers used by trace.py) ---------------------
    def insert_trace_event(self, row: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO trace_events (run_id, agent, node, event_type, payload_json,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["run_id"],
                    row.get("agent"),
                    row.get("node"),
                    row["event_type"],
                    row.get("payload_json", "{}"),
                    time.time(),
                ),
            )
            self._conn.commit()

    def trace_events_for_run(self, run_id: str, since: int = 0) -> list[dict[str, Any]]:
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM trace_events WHERE run_id = ? AND id > ? ORDER BY id ASC",
                (run_id, since),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def insert_llm_call(self, row: dict[str, Any]) -> None:
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO llm_calls (run_id, agent, model, prompt_json, output_text,"
                " prompt_tokens, completion_tokens, total_tokens, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["run_id"],
                    row.get("agent"),
                    row.get("model"),
                    row.get("prompt_json", "[]"),
                    row.get("output_text"),
                    row.get("prompt_tokens"),
                    row.get("completion_tokens"),
                    row.get("total_tokens"),
                    time.time(),
                ),
            )
            self._conn.commit()

    def llm_calls_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM llm_calls WHERE run_id = ? ORDER BY id ASC", (run_id,)
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ---- syntheses (append-only) ------------------------------------------
    def append_synthesis(self, run_id: str, payload: dict[str, Any]) -> None:
        """Insert one projected synthesis row (append-only, never UPDATEd).

        The ``referenced_claim_ids`` list is mirrored into its own column so the
        provenance set survives independently of the payload blob. Both are
        JSON-serialized; the single-writer ``_WRITE_LOCK`` is held for the write.

        Args:
            run_id: The run this synthesis belongs to.
            payload: The projected synthesis dict (already validated/projected by
                :func:`mingjing.synthesis.project_synthesis`). Its
                ``referenced_claim_ids`` key (if present) is copied into the
                dedicated column.
        """
        referenced = payload.get("referenced_claim_ids") or []
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO syntheses (run_id, payload_json, referenced_claim_ids_json,"
                " created_at) VALUES (?, ?, ?, ?)",
                (
                    run_id,
                    json.dumps(payload),
                    json.dumps(referenced),
                    time.time(),
                ),
            )
            self._conn.commit()

    def get_synthesis(self, run_id: str) -> dict[str, Any] | None:
        """Return the latest synthesis payload for a run, or ``None`` if absent.

        Selects the most recent row by ``created_at`` (then ``id`` as a stable
        tiebreaker). The stored ``payload_json`` is parsed and the
        ``referenced_claim_ids`` key is overlaid from its dedicated column so the
        provenance set is authoritative even if the payload blob omitted it.

        Args:
            run_id: The run identifier.

        Returns:
            The parsed payload dict (with ``referenced_claim_ids`` merged in), or
            ``None`` when the run has no synthesis row.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT payload_json, referenced_claim_ids_json FROM syntheses"
                " WHERE run_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        try:
            referenced = json.loads(row["referenced_claim_ids_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            referenced = []
        payload["referenced_claim_ids"] = referenced
        return payload
