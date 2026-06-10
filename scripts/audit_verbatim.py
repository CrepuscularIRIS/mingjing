"""Read-only deterministic verbatim re-verification audit (task M7).

This is an AUDIT TOOL, not part of the product runtime: it opens
``data/mingjing.db`` read-only and, for every ADMITTED claim (latest version,
``status == "pass"``) of the audited runs, deterministically RE-CHECKS — using
the SAME helpers the production QA gate uses (:mod:`mingjing.qa.rules`) — that

1. each cited evidence ``snippet`` is a verbatim substring of its source's
   ``raw_text`` (whitespace-normalized; the production HALLUCINATED_SNIPPET口径);
2. each substantial string/numeric leaf under a **required** value sub-field is
   grounded in the concatenated cited-source text (the production
   VALUE_UNSUPPORTED口径).

A claim PASSES the verbatim re-check iff every cited snippet hits AND no required
sub-field leaf is unsupported. The audit also enumerates each run's WITHHELD
claims (final-round qc_reports with issues) and their issue codes, so abstention
is accounted for too.

Honest framing: this is a *deterministic re-verification* — it asserts nothing an
LLM said; it re-runs string-equality / numeric-equality checks that anyone can
reproduce. It never writes to the database and never weakens any gate.

Reproduce::

    uv run python scripts/audit_verbatim.py

Audit a different DB / run set::

    uv run python scripts/audit_verbatim.py --db data/mingjing.db \\
        --run 4fff4227cdce4661a654603566a0385e --run 3775d21a9b634b5a86854c613c3187c8
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from mingjing.claim_builder import claimset_parts
from mingjing.db import Database
from mingjing.qa import rules
from mingjing.schemas import active_field_schemas

logger = logging.getLogger(__name__)

# The two runs the M7 task audits by default (中文旗舰 + EN 史料).
DEFAULT_DB = "data/mingjing.db"
DEFAULT_RUNS = (
    "4fff4227cdce4661a654603566a0385e",
    "3775d21a9b634b5a86854c613c3187c8",
)


def _check_snippets(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-snippet verbatim verdict, identical口径 to ``_check_hallucinated_snippet``.

    A snippet ``hit`` iff its whitespace-normalized form is a substring of its
    source's whitespace-normalized ``raw_text`` (an empty snippet trivially hits,
    matching the production gate which only flags a non-empty miss).

    Args:
        claim: The reconstructed claim dict (from :func:`claimset_parts`).
        sources: The reconstructed sources map keyed by source id.

    Returns:
        One result dict per evidence item: ``{source_id, hit, snippet}``.
    """
    out: list[dict[str, Any]] = []
    for ev in claim.get("evidence", []):
        snippet = ev.get("snippet", "")
        sid = ev.get("source_id")
        raw = sources.get(sid, {}).get("raw_text", "")
        norm_snippet = rules._normalize_ws(snippet)
        hit = (not norm_snippet) or (norm_snippet in rules._normalize_ws(raw))
        out.append({"source_id": sid, "hit": hit, "snippet": snippet})
    return out


def audit_claim(db: Database, run_id: str, claim_id: str) -> dict[str, Any]:
    """Deterministically re-verify one admitted claim's snippets + value grounding.

    Reconstructs the single-claim claimset via :func:`claimset_parts` (the SAME
    code path that feeds the QA gate) and re-runs the production verbatim checks
    (:func:`mingjing.qa.rules._check_hallucinated_snippet` and
    :func:`mingjing.qa.rules._check_value_unsupported`) so the verdict cannot
    drift from the live gate semantics.

    Args:
        db: An initialized :class:`~mingjing.db.Database` (read-only use).
        run_id: The owning run id.
        claim_id: The logical claim id (latest version is resolved internally).

    Returns:
        A per-claim audit dict with field/tier/source-count, per-snippet hits,
        the value-grounding verdict, and an ``overall_pass`` boolean.

    Raises:
        KeyError: When the claim id has no latest-version row in the run.
    """
    latest = {c["id"]: c for c in db.latest_claims_for_run(run_id)}
    row = latest.get(claim_id)
    if row is None:
        raise KeyError(f"no latest claim {claim_id!r} in run {run_id!r}")

    claims, sources = claimset_parts(db, [row])
    claim = claims[0]

    snippets = _check_snippets(claim, sources)
    snippets_pass = all(s["hit"] for s in snippets)

    # Value grounding: reuse the production check verbatim. An empty issue list
    # means every required-sub-field leaf is grounded (or there is nothing to
    # ground). Surface the unsupported leaves when it fails (no cover-up).
    value_issues = rules._check_value_unsupported(claim, sources)
    value_supported = not value_issues
    unsupported_leaves: list[str] = []
    for issue in value_issues:
        unsupported_leaves.extend(issue.meta.get("unsupported", []))

    schema = active_field_schemas().get(claim.get("schema_field", ""), {})
    required_subfields = list(schema.get("required", []))

    source_ids = sorted({ev.get("source_id") for ev in claim.get("evidence", [])})
    overall_pass = snippets_pass and value_supported

    return {
        "claim_id": claim_id,
        "schema_field": claim.get("schema_field"),
        "competitor": claim.get("competitor"),
        "tier": row.get("evidence_strength"),
        "version": row.get("version"),
        "num_sources": len(source_ids),
        "source_ids": source_ids,
        "num_snippets": len(snippets),
        "snippets": snippets,
        "snippets_pass": snippets_pass,
        "required_subfields": required_subfields,
        "value_supported": value_supported,
        "unsupported_leaves": unsupported_leaves,
        "overall_pass": overall_pass,
    }


def _withheld_breakdown(db: Database, run_id: str) -> dict[str, Any]:
    """Final-round withheld-claim count + issue-code tally for a run.

    Reuses :meth:`Database.last_round_issues_for_run` — the SAME final-round scan
    the withheld-disclosure endpoint uses — so the audit's abstention accounting
    matches the product's own disclosure.
    """
    last_round = db.last_round_issues_for_run(run_id)
    code_tally: dict[str, int] = {}
    for entry in last_round.values():
        for code in entry.get("issue_codes", []):
            code_tally[code] = code_tally.get(code, 0) + 1
    return {
        "withheld_count": len(last_round),
        "withheld_codes": code_tally,
        "withheld_claim_ids": sorted(last_round.keys()),
    }


def audit_run(db: Database, run_id: str) -> dict[str, Any]:
    """Audit every admitted claim of a run + tally its withheld claims.

    Args:
        db: An initialized :class:`~mingjing.db.Database` (read-only use).
        run_id: The run id to audit.

    Returns:
        A run summary dict: admitted/checked/passed/failed counts, the per-claim
        audit records, the list of FAILED claim records (empty when all pass),
        and the withheld breakdown.
    """
    latest = db.latest_claims_for_run(run_id)
    admitted = [c for c in latest if c.get("status") == "pass"]

    claim_audits: list[dict[str, Any]] = []
    for c in admitted:
        claim_audits.append(audit_claim(db, run_id, c["id"]))

    passed = [a for a in claim_audits if a["overall_pass"]]
    failed = [a for a in claim_audits if not a["overall_pass"]]

    withheld = _withheld_breakdown(db, run_id)

    return {
        "run_id": run_id,
        "admitted_count": len(admitted),
        "checked": len(claim_audits),
        "passed": len(passed),
        "failed": len(failed),
        "pass_rate": (len(passed) / len(claim_audits)) if claim_audits else 0.0,
        "claims": claim_audits,
        "failed_claims": failed,
        "withheld_count": withheld["withheld_count"],
        "withheld_codes": withheld["withheld_codes"],
        "withheld_claim_ids": withheld["withheld_claim_ids"],
    }


def audit(db_path: str, run_ids: list[str]) -> dict[str, Any]:
    """Audit each run in ``run_ids`` against the DB at ``db_path``.

    Strictly read-only — ENFORCED BY THE ENGINE, not by convention: the DB is
    opened with ``read_only=True`` (SQLite URI ``mode=ro`` + ``query_only=ON``),
    so any write attempt raises ``sqlite3.OperationalError`` and a missing file
    is refused rather than created. No schema init is run.
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"DB not found: {db_path} — the audit is read-only and will not create a database"
        )
    db = Database(db_path, read_only=True)
    runs = [audit_run(db, rid) for rid in run_ids]
    total_checked = sum(r["checked"] for r in runs)
    total_passed = sum(r["passed"] for r in runs)
    return {
        "db_path": db_path,
        "runs": runs,
        "total_checked": total_checked,
        "total_passed": total_passed,
        "overall_pass_rate": (total_passed / total_checked) if total_checked else 0.0,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only verbatim claim audit (M7).")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path (read-only).")
    parser.add_argument(
        "--run",
        action="append",
        dest="runs",
        help="Run id to audit (repeatable). Defaults to the two M7 runs.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — print a human-readable audit, or ``--json`` for machine."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    run_ids = args.runs or list(DEFAULT_RUNS)
    report = audit(args.db, run_ids)

    if args.json:
        logger.info(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for run in report["runs"]:
        logger.info("=" * 72)
        logger.info("RUN %s", run["run_id"])
        logger.info(
            "  admitted=%d  re-checked=%d  PASS=%d  FAIL=%d  pass_rate=%.1f%%",
            run["admitted_count"],
            run["checked"],
            run["passed"],
            run["failed"],
            run["pass_rate"] * 100,
        )
        logger.info(
            "  withheld=%d  codes=%s",
            run["withheld_count"],
            run["withheld_codes"] or "{}",
        )
        for a in run["claims"]:
            mark = "PASS" if a["overall_pass"] else "FAIL"
            logger.info(
                "    [%s] %-16s tier=%-8s sources=%d snippets=%d(hit %d)"
                " value_supported=%s",
                mark,
                a["schema_field"],
                a["tier"],
                a["num_sources"],
                a["num_snippets"],
                sum(1 for s in a["snippets"] if s["hit"]),
                a["value_supported"],
            )
            if not a["overall_pass"]:
                misses = [s["snippet"] for s in a["snippets"] if not s["hit"]]
                logger.info("        claim_id=%s", a["claim_id"])
                if misses:
                    logger.info("        MISSED SNIPPETS: %s", misses)
                if a["unsupported_leaves"]:
                    logger.info("        UNSUPPORTED LEAVES: %s", a["unsupported_leaves"])
    logger.info("=" * 72)
    logger.info(
        "OVERALL: %d/%d snippets+value re-verified PASS = %.1f%%",
        report["total_passed"],
        report["total_checked"],
        report["overall_pass_rate"] * 100,
    )


if __name__ == "__main__":
    main()
