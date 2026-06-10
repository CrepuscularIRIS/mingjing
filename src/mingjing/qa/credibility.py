"""Quantified credibility KPIs — the numbers no competitor surfaces.

All pure functions over the ledger. Headline KPI is repair_delta: how much
groundedness improved from the first round to the last (proves the loop is a
real weak→strong closed loop, not a 伪闭环).

Lives in ``qa/credibility.py`` (not ``qa/metrics.py``) to avoid confusion with
the pre-existing ``mingjing.metrics`` module (``compute_metrics``)."""

# Tier ordering for the honest weak→strong signal. Higher rank == stronger.
# These are the EXISTING ``evidence_strength`` tier names from scoring.py
# (Strength = Literal["strong", "moderate", "weak"]); this module only ORDERS
# them, it never recomputes a claim's tier.
_TIER_RANK = {"weak": 0, "moderate": 1, "strong": 2}


def _has_tier_upgrade(claim_version_strengths: dict[str, list[str]]) -> bool:
    """True iff some claim's version chain shows a strict tier increase.

    Read-only derived signal. For each logical claim (keyed by id/lineage), the
    value is its tiers ordered oldest→newest (the same order the claim-history
    endpoint returns). A claim counts as upgraded when ANY later version ranks
    strictly higher than ANY earlier version (weak→moderate, weak→strong, or
    moderate→strong). Unknown tier strings are ignored (do not raise). This is
    additive and never alters a claim's strength or any verdict.
    """
    for tiers in claim_version_strengths.values():
        ranks = [_TIER_RANK[t] for t in tiers if t in _TIER_RANK]
        # A strict increase anywhere in the chain means max-so-far at a later
        # index exceeds an earlier rank; equivalently max(after) > min(before).
        running_min = None
        for rank in ranks:
            if running_min is not None and rank > running_min:
                return True
            if running_min is None or rank < running_min:
                running_min = rank
    return False


def _paired_repair_delta(
    claim_version_groundedness: dict[str, list[float]],
) -> float:
    """Mean per-claim groundedness lift over claims that actually revised.

    Each value is one logical claim's groundedness ordered oldest→newest by
    version. Only claims with >=2 versions count as repaired; for each, the lift
    is ``last - first`` (its OWN before vs after — a paired comparison on the
    same claim, never a mean-of-means across different claim populations). The
    result is the mean lift across repaired claims. When no claim revised the
    delta is 0.0 (honest: nothing was repaired). Signed: a negative value
    honestly reflects a groundedness regression on repaired claims.
    """
    lifts = [
        scores[-1] - scores[0]
        for scores in claim_version_groundedness.values()
        if len(scores) >= 2
    ]
    return round(sum(lifts) / len(lifts), 3) if lifts else 0.0


def credibility_panel(
    *,
    passed_claims: list[dict],
    total_claims: int,
    required_fields: list[str],
    covered_fields: list[str],
    round_indices: list[int] | None = None,
    claim_version_strengths: dict[str, list[str]] | None = None,
    claim_version_groundedness: dict[str, list[float]] | None = None,
) -> dict:
    """Compute the credibility KPI panel for one run.

    All rates and ``coverage`` are 0..1; ``repair_delta`` is signed (a negative
    value honestly reflects a groundedness regression). Empty inputs degrade to
    0.0 rather than raising. ``rounds`` is the number of distinct version levels
    observed (``len(round_indices)``).

    ``repair_delta`` is the PAIRED mean per-claim lift over claims that actually
    revised (>=2 versions), derived from ``claim_version_groundedness``: each
    repaired claim's last-version groundedness minus its own first-version
    groundedness, averaged. Claims that never revised do not contribute, so the
    metric measures the lift on claims that were genuinely repaired — NOT a
    mean-of-means over different "before"/"after" claim populations (RC1). When
    no claim revised, ``repair_delta`` is 0.0 (honest: nothing was repaired).
    (Task 6 will promote the return to a TypedDict once the API consumes it.)

    ``is_tier_upgrade`` is an ADDITIVE, read-only honesty signal derived from
    ``claim_version_strengths`` (a mapping of claim id → oldest→newest tier
    list using the existing ``evidence_strength`` values). It is True iff at
    least one claim's version chain shows a strict tier increase
    (weak<moderate<strong). Unlike ``repair_delta`` (a groundedness scalar that
    can move within a single tier), this reflects a TRUE tier promotion — it
    does not change ``repair_delta`` or any other field.
    """
    n = len(passed_claims)
    covered = set(covered_fields)
    avg_g = round(sum(c.get("groundedness", 0.0) for c in passed_claims) / n, 3) if n else 0.0
    admission = round(n / total_claims, 3) if total_claims else 0.0
    hits = sum(1 for f in required_fields if f in covered)
    cov = round(hits / len(required_fields), 3) if required_fields else 0.0
    delta = _paired_repair_delta(claim_version_groundedness or {})
    # Admission waterfall (ADVISORY): proposed → admitted → withheld. Counts are
    # over distinct latest-version claims: the caller contract (api.py passes
    # total_claims = len(latest_claims_for_run)) guarantees a claim revised
    # across rounds is counted once — this pure function does not itself dedup.
    # Makes "少而精" legible: a low admitted/proposed ratio is the QA gate
    # working, not failure.
    withheld = max(total_claims - n, 0)
    # Coverage gaps (ADVISORY): field NAMES only (schema, never values → no leak).
    # Bounded to required_fields and kept in the schema's declared order.
    covered_in_req = [f for f in required_fields if f in covered]
    uncovered = [f for f in required_fields if f not in covered]
    return {
        "avg_groundedness": avg_g,
        "claim_admission_rate": admission,
        "coverage": cov,
        "repair_delta": delta,
        "rounds": len(round_indices or []),
        "proposed_claims": total_claims,
        "admitted_claims": n,
        "withheld_claims": withheld,
        "covered_fields": covered_in_req,
        "uncovered_fields": uncovered,
        "is_tier_upgrade": _has_tier_upgrade(claim_version_strengths or {}),
    }
