"""Pure projection / KPI helpers for the MingJing API (extracted from ``api.py``).

Everything here is module-level and free of FastAPI/app state. The functions take
their inputs explicitly (claims/sources/db), so they are unit-testable in
isolation and ``api.py`` simply re-exports them. Behavior is identical to the
prior in-``api.py`` definitions; this is a pure move.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from .contradiction import summarize_contradiction
from .db import Database
from .qa.groundedness import score_groundedness
from .schemas import FIELD_SCHEMAS

_log = logging.getLogger(__name__)


def _run_with_logging(executor: Callable[[str], None], rid: str) -> None:
    """Run ``executor(rid)`` and log any exception so failures are never silent."""
    try:
        executor(rid)
    except Exception:
        _log.exception("run_executor failed for run_id=%s", rid)


def _evidence_source_ids(raw: Any) -> list[str]:
    """Normalize a decoded ``evidence_json`` value to a list of id STRINGS.

    ``build_claim`` stores evidence as objects
    (``{"source_id","snippet","relevance"}``); older/synthetic rows may store
    plain id strings. The report/history API must always expose plain id strings
    so the frontend calls ``/sources/<id>`` rather than ``/sources/[object Object]``.
    """
    out: list[str] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict):
            sid = entry.get("source_id")
        else:
            sid = entry
        if sid:
            out.append(sid)
    return out


def _source_type_breakdown(
    evidence_source_ids: list[str], sources: dict[str, Any]
) -> dict[str, int]:
    """Return an ADVISORY per-source-type count for a claim's cited sources.

    A raw display tally of ``{source_type: count}`` over the claim's OWN
    ``evidence_source_ids`` (e.g. ``{"official": 2, "news": 1}``). Missing/unknown
    ids default to ``"web"`` (mirrors the collector default).

    NOTE: this is a RAW per-source count for human display. It is NOT the
    registrable-domain count that drives the 3-tier scorer (``scoring.strength``
    dedupes supporting sources by registrable domain before the >=2-domain gate),
    and it must never be wired into a verdict/tier — it is read-side enrichment only.
    """
    counts: dict[str, int] = {}
    for sid in evidence_source_ids:
        stype = ((sources.get(sid) or {}).get("source_type") or "web")
        counts[stype] = counts.get(stype, 0) + 1
    return counts


def _build_report_sections(
    claims: list[dict[str, Any]],
    sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group QA-passed claims by schema_field and compute a strength tally.

    Only claims with ``status`` equal to ``"pass"`` are included. Each section
    carries the list of claim dicts enriched with decoded ``value`` and
    ``evidence_source_ids``. When ``sources`` (a ``{source_id: {url, source_type}}``
    map) is provided, a claim whose evidence has a cross-domain supports/refutes
    split also carries a ``contradiction`` object (see
    :func:`mingjing.contradiction.summarize_contradiction`) so the report surfaces
    the conflict instead of hiding it.

    Args:
        claims: Latest-version claim rows from the database.
        sources: Optional source map for source-vs-source contradiction detection.

    Returns:
        A dict ``{"sections": [...], "strength_tally": {strong, moderate, weak}}``.
    """
    sources = sources or {}
    tally: dict[str, int] = {"strong": 0, "moderate": 0, "weak": 0}
    field_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for claim in claims:
        if claim.get("status") != "pass":
            continue
        strength = (claim.get("evidence_strength") or "").lower()
        if strength in tally:
            tally[strength] += 1

        # Decode JSON-encoded fields safely.
        try:
            value = json.loads(claim.get("value_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            value = {}
        try:
            evidence = json.loads(claim.get("evidence_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            evidence = []
        if not isinstance(evidence, list):
            evidence = []
        evidence_source_ids = _evidence_source_ids(evidence)
        try:
            based_on = json.loads(claim.get("based_on_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            based_on = []
        if not isinstance(based_on, list):
            based_on = []

        claim_dict: dict[str, Any] = {
            "id": claim.get("id"),
            "competitor": claim.get("competitor"),
            "statement": claim.get("statement", ""),
            "evidence_strength": claim.get("evidence_strength"),
            "value": value,
            "evidence_source_ids": evidence_source_ids,
            # Advisory per-source-type tally (display third axis). Read-side only:
            # never an input to scoring/QA — see _source_type_breakdown.
            "source_types": _source_type_breakdown(evidence_source_ids, sources),
            "based_on": based_on,
            "version": claim.get("version"),
        }
        # Surface a source-vs-source conflict (supports/refutes on distinct
        # domains) so the report never hides a disagreement. Omitted when clean.
        contradiction = summarize_contradiction(evidence, sources)
        if contradiction is not None:
            claim_dict["contradiction"] = contradiction
        field_groups[claim.get("schema_field", "unknown")].append(claim_dict)

    sections = [
        {"schema_field": field, "claims": field_claims}
        for field, field_claims in field_groups.items()
    ]
    return {"sections": sections, "strength_tally": tally}


def _claim_groundedness(
    claim: dict[str, Any], source_text_by_id: dict[str, str]
) -> float:
    """Compute the advisory blind-groundedness score for one claim row on read.

    Groundedness is NOT persisted per-claim (qc_reports has no such column), so
    it is recomputed here from the same raw materials the deterministic
    VALUE_UNSUPPORTED gate uses: the claim's decoded ``value`` leaves vs the
    concatenated raw text of its cited sources. The cited-source assembly mirrors
    ``rules._check_value_unsupported`` — evidence entries may be ``{"source_id"}``
    objects (``build_claim`` format) or plain id strings (synthetic rows).

    Args:
        claim: A claim row dict (with ``value_json`` and ``evidence_json``).
        source_text_by_id: Map of source id -> raw_text for the run.

    Returns:
        A 0..1 advisory groundedness score (see ``qa.groundedness``).
    """
    try:
        value = json.loads(claim.get("value_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        value = {}
    if not isinstance(value, dict):
        value = {}

    try:
        evidence = json.loads(claim.get("evidence_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        evidence = []
    source_ids = _evidence_source_ids(evidence)

    cited_text = " ".join(
        source_text_by_id.get(sid, "") for sid in source_ids
    )
    return score_groundedness(value=value, cited_source_text=cited_text)


def load_credibility_inputs(db: Database, run_id: str) -> dict[str, Any]:
    """Thin reader assembling the kwargs ``credibility_panel`` expects.

    Sourced entirely from existing ledger reads — no new DB queries beyond
    the ones the other endpoints already use:

    - ``passed_claims``: latest-version ``status=="pass"`` claims, each as
      ``{"id", "groundedness"}``. Groundedness is recomputed on read (it is
      not persisted) via :func:`_claim_groundedness`.
    - ``total_claims``: count of latest-version claims (any status).
    - ``required_fields`` / ``covered_fields``: reuse the SAME coverage
      definition as ``metrics.compute_metrics`` — required prefers the run's
      explicit ``intake["fields"]`` (schema-registry path) and falls back to
      the frozen ``FIELD_SCHEMAS`` keys; covered = distinct ``schema_field``
      among passed claims.
    - ``round_indices``: the sorted distinct version levels observed (version
      N == round N-1). Drives the ``rounds`` count only.
    - ``claim_version_groundedness``: per logical claim, its groundedness
      ordered oldest→newest by version (mirrors ``claim_version_strengths``).
      ``repair_delta`` is the PAIRED mean lift over claims that actually
      revised (>=2 versions): each such claim's last-version groundedness
      minus its first-version groundedness, averaged. Claims that never
      revised do not contribute (they were not repaired). When no claim
      revised, ``repair_delta`` is 0.0 — honest: nothing was repaired. This
      fixes the prior mean-of-means computation, which compared the "before"
      mean (every initial claim) against the "after" mean (only the subset
      that revised) — two non-comparable populations (RC1).

    Args:
        db: The :class:`~mingjing.db.Database` to read from.
        run_id: The run identifier.
    """
    active_db = db

    source_text_by_id = {
        s["id"]: (s.get("raw_text") or "")
        for s in active_db.sources_for_run(run_id)
    }

    latest = active_db.latest_claims_for_run(run_id)
    passed = [c for c in latest if c.get("status") == "pass"]
    passed_claims = [
        {
            "id": c.get("id"),
            "groundedness": _claim_groundedness(c, source_text_by_id),
        }
        for c in passed
    ]

    # Mirror metrics.compute_metrics: prefer the run's explicit field list,
    # fall back to the frozen FIELD_SCHEMAS keys — so the two coverage numbers
    # never disagree for a custom-field run.
    intake = active_db.get_run(run_id) or {}
    run_fields = intake.get("fields") if isinstance(intake, dict) else None
    required_fields = list(run_fields) if run_fields else list(FIELD_SCHEMAS.keys())
    covered_fields = sorted(
        {c.get("schema_field") for c in passed if c.get("schema_field")}
    )

    # Per-round (== per-version) mean groundedness across ALL claim rows.
    # Single pass over ALL rows also builds the per-claim tier history that
    # drives the read-only ``is_tier_upgrade`` honesty signal — reusing the
    # EXISTING ``evidence_strength`` tier per version (never recomputed).
    all_rows = active_db.claims_for_run(run_id)
    versions_seen: set[int] = set()
    tiers_by_claim: dict[str, list[tuple[int, str]]] = defaultdict(list)
    grounded_by_claim: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in all_rows:
        try:
            v = int(row.get("version", 1) or 1)
        except (TypeError, ValueError):
            v = 1  # defensive: a non-numeric version coerces to round 1
        versions_seen.add(v)
        claim_id = row.get("id")
        if claim_id:
            grounded_by_claim[claim_id].append(
                (v, _claim_groundedness(row, source_text_by_id))
            )
        strength = row.get("evidence_strength")
        if claim_id and strength:
            tiers_by_claim[claim_id].append((v, strength))
    # ``rounds`` is the number of distinct version levels observed (version N ==
    # round N-1). This is honestly derived from the lineage, independent of the
    # paired-delta math below — a single sorted ascending list of round indices.
    round_indices = sorted(versions_seen)
    # Order each claim's tiers / groundedness oldest→newest (by version) — the
    # same lineage order the claim-history endpoint returns. ``repair_delta`` is
    # computed PAIRED from ``claim_version_groundedness`` (each repaired claim's
    # own first→last lift), never as a mean-of-means over mixed populations.
    claim_version_strengths = {
        cid: [s for _, s in sorted(versions)]
        for cid, versions in tiers_by_claim.items()
    }
    claim_version_groundedness = {
        cid: [g for _, g in sorted(versions)]
        for cid, versions in grounded_by_claim.items()
    }

    return {
        "passed_claims": passed_claims,
        "total_claims": len(latest),
        "required_fields": required_fields,
        "covered_fields": covered_fields,
        "round_indices": round_indices,
        "claim_version_strengths": claim_version_strengths,
        "claim_version_groundedness": claim_version_groundedness,
    }
