"""Pure-compute metrics for the MingJing business-loop KPI bar.

All functions in this module are PURE: they accept already-loaded lists/dicts
and return plain Python dicts with no I/O side-effects. The API layer is
responsible for loading data from the DB and passing it here.

Metrics exposed (organizer names in parentheses):
- coverage        覆盖率  — distinct schema_field coverage among passed claims
- citation_rate   引用率  — fraction of passed claims with ≥1 cited source
- strong_rate     准确率 PROXY — fraction of cited-passed claims with strong evidence
- human_correction_rate  人工修正率 — fraction of claims touched by a human override
- efficiency      耗时/资源 — wall-clock seconds, source count, LLM calls, total tokens
"""

from __future__ import annotations

import json
import math
from typing import Any

from .schemas import FIELD_SCHEMAS

# The static honesty caveat surfaced alongside the strong_rate metric so the
# dashboard caller is never misled into treating strong evidence as verified truth.
ACCURACY_CAVEAT: str = (
    "强证据率 is necessary-not-sufficient for factual accuracy — each claim has a"
    " strong evidence link, not that the evidence is correct."
    " Supplement with a human spot-check of ≥20 sampled claims."
)

# Human-analyst baseline for ONE manual competitive-analysis pass (search →
# read sources → extract claims → cross-check → write up). This is an INDUSTRY
# ESTIMATE, NOT a measured quantity: a single analyst typically spends roughly
# 2–5 working days (16–40 hours) on a multi-competitor desk study with sourced
# claims. Surfaced ONLY to contextualize the machine's MEASURED wall-clock; the
# speedup ratio below is always derived from real ``elapsed_s``, never invented.
HUMAN_BASELINE_HOURS_LOW: int = 16
HUMAN_BASELINE_HOURS_HIGH: int = 40

# Below this measured wall-clock the speedup is SUPPRESSED (left None). A
# sub-second run (e.g. two trace events fired within one fast/cached node) would
# otherwise divide-by-near-zero into absurd, dishonest-looking ratios
# ("本次 0s … 约 576,000×"). Honesty floor — not a cap on real fast runs.
MIN_CREDIBLE_ELAPSED_S: float = 1.0


def _round_ratio(ratio: float) -> float | int:
    """Round a speedup ratio honestly. ``>= 10x`` → whole number. ``[1, 10)`` →
    one decimal. ``< 1`` (a run genuinely SLOWER than the human-low estimate) is
    FLOORED to one decimal — never rounded up — so e.g. 0.96 shows ``0.9x`` and
    is never flattered up to a parity-claiming ``1.0x``."""
    if ratio >= 10:
        return round(ratio)
    if ratio < 1:
        return math.floor(ratio * 10) / 10
    return round(ratio, 1)


def _extract_source_ids(evidence_json_raw: str | None) -> list[str]:
    """Decode an ``evidence_json`` column value to a list of source id strings.

    Kept local to ``metrics`` (which must stay pure) rather than shared with
    ``api._evidence_source_ids``: the contracts differ deliberately — this
    helper takes the **raw JSON string** straight from the DB column and decodes
    it, whereas ``api._evidence_source_ids`` takes an **already-decoded** list.
    This one also normalizes every id with ``str(...)`` so non-string ids count
    consistently. Both plain string-id lists (old synthetic rows) and object
    arrays (``build_claim`` format ``{"source_id", "snippet", …}``) are handled.

    Args:
        evidence_json_raw: The raw JSON string from the DB column, or ``None``.

    Returns:
        A list of non-empty source-id strings (may be empty on any error).
    """
    try:
        raw: Any = json.loads(evidence_json_raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            sid = entry.get("source_id")
        else:
            sid = entry
        if sid:
            out.append(str(sid))
    return out


def compute_metrics(
    claims: list[dict[str, Any]],
    llm_calls: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    trace_events: list[dict[str, Any]],
    intake: dict[str, Any],
) -> dict[str, Any]:
    """Compute all KPI-bar metrics from pre-loaded run data.

    This function is PURE — it performs no I/O. The caller loads all data from
    the DB and passes it in as plain Python lists/dicts.

    Args:
        claims: Latest-version claim row dicts for the run (from
            ``Database.latest_claims_for_run``). Each dict has at minimum the
            keys ``id``, ``status``, ``schema_field``, ``evidence_json``,
            ``evidence_strength``, and ``produced_by``.
        llm_calls: LLM call row dicts for the run (from
            ``Database.llm_calls_for_run``). Each dict may have
            ``total_tokens`` (int or None).
        sources: Source row dicts for the run (from
            ``Database.sources_for_run``). Only the count is used here.
        trace_events: Trace event row dicts (from
            ``Database.trace_events_for_run``). Each dict has a ``created_at``
            float column. Used to derive wall-clock elapsed time.
        intake: The run row dict (from ``Database.get_run``). Currently not
            used for field derivation — required_fields comes from
            ``FIELD_SCHEMAS``. If a future schema-registry change populates an
            ``intake["fields"]`` list, prefer that over the static dict.

    Returns:
        A dict with keys:
        ``coverage``, ``citation_rate``, ``strong_rate``,
        ``human_correction_rate``, ``efficiency`` (nested dict),
        ``accuracy_caveat`` (static string).
        All float values are rounded to 4 decimal places.
    """
    # ---- required_fields --------------------------------------------------
    # Prefer intake["fields"] if the run was started with an explicit field list
    # (future schema-registry path). Fall back to the frozen FIELD_SCHEMAS keys.
    run_fields: list[str] | None = (
        intake.get("fields") if isinstance(intake, dict) else None
    )
    if run_fields:
        required_fields = len(run_fields)
    else:
        required_fields = len(FIELD_SCHEMAS)

    # ---- pass-filtered claims ---------------------------------------------
    passed = [c for c in claims if c.get("status") == "pass"]

    # ---- coverage  (覆盖率) -----------------------------------------------
    passed_fields = len({c.get("schema_field") for c in passed if c.get("schema_field")})
    coverage = round(passed_fields / required_fields, 4) if required_fields else 0.0

    # ---- citation_rate  (引用率) -------------------------------------------
    total_passed = len(passed)
    cited_passed = [
        c for c in passed if _extract_source_ids(c.get("evidence_json"))
    ]
    citation_rate = (
        round(len(cited_passed) / total_passed, 4) if total_passed else 0.0
    )

    # ---- strong_rate  (准确率 PROXY) ----------------------------------------
    claims_with_evidence = cited_passed  # same set: passed + ≥1 source
    strong_claims = [
        c for c in claims_with_evidence
        if (c.get("evidence_strength") or "").lower() == "strong"
    ]
    claims_with_any_evidence_count = len(claims_with_evidence)
    strong_rate = (
        round(len(strong_claims) / claims_with_any_evidence_count, 4)
        if claims_with_any_evidence_count
        else 0.0
    )

    # ---- human_correction_rate  (人工修正率) --------------------------------
    # Denominator: total distinct claims (regardless of status).
    distinct_claim_ids = {c.get("id") for c in claims if c.get("id")}
    total_distinct = len(distinct_claim_ids)
    human_corrected = [
        c for c in claims if c.get("produced_by") == "human:correction"
    ]
    human_correction_rate = (
        round(len(human_corrected) / total_distinct, 4) if total_distinct else 0.0
    )

    # ---- efficiency  (耗时) ------------------------------------------------
    created_ats = [
        float(e["created_at"])
        for e in trace_events
        if e.get("created_at") is not None
    ]
    elapsed_s: float = 0.0
    if len(created_ats) >= 2:
        elapsed_s = round(max(created_ats) - min(created_ats), 4)

    total_tokens = sum(
        int(lc["total_tokens"]) for lc in llm_calls if lc.get("total_tokens") is not None
    )

    # ---- honest measured-vs-human-estimate speedup -------------------------
    # MEASURED machine time (elapsed_s) vs an ESTIMATED human-analyst range.
    # Computed ONLY when elapsed_s >= MIN_CREDIBLE_ELAPSED_S — below that a
    # divide-by-near-zero would print absurd ratios, so the fields stay None and
    # the UI falls back to a plain estimate caption. Ratios keep one decimal
    # under 10× (a >16h run honestly shows <1×, never rounded up). The human
    # range is advisory — it never feeds any other metric and is always labeled
    # as an estimate downstream.
    speedup_low: float | None = None
    speedup_high: float | None = None
    if elapsed_s >= MIN_CREDIBLE_ELAPSED_S:
        speedup_low = _round_ratio(HUMAN_BASELINE_HOURS_LOW * 3600 / elapsed_s)
        speedup_high = _round_ratio(HUMAN_BASELINE_HOURS_HIGH * 3600 / elapsed_s)

    efficiency: dict[str, Any] = {
        "elapsed_s": elapsed_s,
        "source_count": len(sources),
        "llm_calls": len(llm_calls),
        "total_tokens": total_tokens,
        # Human baseline (ESTIMATE, not measured) + derived speedup vs real time.
        "human_baseline_hours_low": HUMAN_BASELINE_HOURS_LOW,
        "human_baseline_hours_high": HUMAN_BASELINE_HOURS_HIGH,
        "speedup_low": speedup_low,
        "speedup_high": speedup_high,
    }

    return {
        "coverage": coverage,
        "citation_rate": citation_rate,
        "strong_rate": strong_rate,
        "human_correction_rate": human_correction_rate,
        "efficiency": efficiency,
        "accuracy_caveat": ACCURACY_CAVEAT,
    }
