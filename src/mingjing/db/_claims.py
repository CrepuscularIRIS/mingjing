"""``ClaimMixin`` — the append-only ``claims`` table read/write helpers.

Claims are never UPDATEd in place: a revision inserts a new row with an
incremented ``version`` (supersede-by-insert). All shared-connection access is
serialized by the ONE canonical ``_WRITE_LOCK`` imported from
:mod:`mingjing.db._base`.
"""

import json
import time
from typing import Any

from ._base import _WRITE_LOCK


class ClaimMixin:
    """Append-only ``claims`` operations mixed into :class:`mingjing.db.Database`."""

    def append_claim(self, claim: dict[str, Any]) -> None:
        """Insert a new claim row. Never UPDATE — revisions supersede by version."""
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO claims (id, run_id, competitor, schema_field, claim_type,"
                " statement, value_json, evidence_json, based_on_json, evidence_strength,"
                " status, version, produced_by, note, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim["id"],
                    claim["run_id"],
                    claim.get("competitor"),
                    claim["schema_field"],
                    claim["claim_type"],
                    claim["statement"],
                    claim.get("value_json", "{}"),
                    claim.get("evidence_json", "[]"),
                    claim.get("based_on_json", "[]"),
                    claim["evidence_strength"],
                    claim["status"],
                    int(claim.get("version", 1)),
                    claim.get("produced_by"),
                    claim.get("note"),
                    time.time(),
                ),
            )
            self._conn.commit()

    def append_superseding_claim(
        self, run_id: str, claim_id: str, updates: dict[str, Any]
    ) -> int:
        """Append a superseding claim version via an atomic read-modify-write.

        The ENTIRE read-modify-write runs inside a SINGLE ``_WRITE_LOCK`` window:
        the fresh latest row is read, the caller's ``updates`` DELTA is overlaid,
        ``version`` is set to ``latest.version + 1``, and the new row is INSERTed —
        all before the lock is released. Because the read-latest and the append
        share the one lock that serializes every claim write, two concurrent
        corrections see each other's committed content: the second correction
        builds on the first's edit (no lost update / stale-read clobber) and the
        versions are strictly monotonic (N+1 then N+2). Preserves the append-only
        invariant (always an INSERT, never an UPDATE).

        Args:
            run_id: The run the claim belongs to.
            claim_id: The logical claim identifier (shared across versions).
            updates: A partial DELTA of columns to overlay on the fresh latest row
                (e.g. ``status``, ``produced_by``, ``note``, ``statement``,
                ``value_json``). ``version`` and ``created_at`` are ignored —
                ``version`` is derived from the current max and ``created_at`` is
                set to now (NOT carried from the prior row). Unspecified columns
                are inherited verbatim from the fresh latest row.

        Returns:
            The version assigned to the inserted row.

        Raises:
            KeyError: When no prior version of the claim exists — nothing to
                supersede; the caller must verify the claim exists first.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM claims WHERE run_id = ? AND id = ?"
                " ORDER BY version DESC LIMIT 1",
                (run_id, claim_id),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(
                    f"no existing claim to supersede: run_id={run_id!r}"
                    f" id={claim_id!r}"
                )
            latest = dict(row)
            new_row = {**latest, **updates}
            new_version = int(latest["version"]) + 1
            self._conn.execute(
                "INSERT INTO claims (id, run_id, competitor, schema_field, claim_type,"
                " statement, value_json, evidence_json, based_on_json, evidence_strength,"
                " status, version, produced_by, note, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    run_id,
                    new_row.get("competitor"),
                    new_row["schema_field"],
                    new_row["claim_type"],
                    new_row["statement"],
                    new_row.get("value_json", "{}"),
                    new_row.get("evidence_json", "[]"),
                    new_row.get("based_on_json", "[]"),
                    new_row["evidence_strength"],
                    new_row["status"],
                    new_version,
                    new_row.get("produced_by"),
                    new_row.get("note"),
                    time.time(),
                ),
            )
            self._conn.commit()
        return new_version

    def claims_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM claims WHERE run_id = ? ORDER BY rowid_pk ASC", (run_id,)
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def latest_claims_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return only the highest-version row per claim id."""
        rows = self.claims_for_run(run_id)
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            cur = latest.get(r["id"])
            if cur is None or r["version"] > cur["version"]:
                latest[r["id"]] = r
        return list(latest.values())

    def claim_versions(self, run_id: str, claim_id: str) -> list[dict[str, Any]]:
        """Return all versions of a single claim, ordered oldest-first.

        Args:
            run_id: The run the claim belongs to.
            claim_id: The logical claim identifier (shared across versions).

        Returns:
            A list of claim row dicts ordered by version ASC (may be empty if
            no such claim exists in the given run).
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT * FROM claims WHERE run_id = ? AND id = ? ORDER BY version ASC",
                (run_id, claim_id),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def flagged_claim_ids_last_round(self, run_id: str) -> set[str]:
        """Return claim ids that the LAST QA round flagged (non-empty issues).

        QA appends one ``qc_reports`` row per claim per round; the row's
        ``issues_json`` is the list of issue codes for that claim in that round
        (``[]`` when clean). This returns the set of claim ids whose
        highest-round qc_report carries at least one issue — i.e. the claims the
        most recent QA pass still rejected. Returns an empty set when the run has
        no qc_reports. Used by the write node so a claim flagged in an EARLIER
        round but recovered by the final round is NOT wrongly excluded on the
        partial path.

        Equivalent to ``set(self.last_round_issues_for_run(run_id))`` — both share
        the same last-round scan; this returns just the ids.
        """
        return set(self.last_round_issues_for_run(run_id))

    def last_round_issues_for_run(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Return the LAST QA round's issue codes per claim id.

        Maps each ``claim_id`` whose highest-round qc_report carries at least one
        issue code to ``{"round": int, "issue_codes": [str, ...]}``. Claims clean
        in the final round (empty ``issues_json``) are omitted. Returns an empty
        dict when the run has no qc_reports. Used by the withheld-claims
        disclosure (Task 9) so a partial run can ENUMERATE what it withheld and
        why — never silent.
        """
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT claim_id, round, issues_json FROM qc_reports"
                " WHERE run_id = ? AND round = ("
                "   SELECT MAX(round) FROM qc_reports WHERE run_id = ?"
                " )",
                (run_id, run_id),
            )
            raw_rows = cur.fetchall()
        out: dict[str, dict[str, Any]] = {}
        for row in raw_rows:
            claim_id = row["claim_id"]
            if not claim_id:
                continue
            try:
                codes = json.loads(row["issues_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                codes = []
            if codes:
                out[claim_id] = {"round": row["round"], "issue_codes": list(codes)}
        return out
