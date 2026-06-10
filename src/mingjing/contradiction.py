"""Pure helper: turn a claim's evidence + sources into ContradictionCard data.

A source-vs-source contradiction is when the claim's evidence carries a
``supports`` stance and a ``refutes`` stance on DISTINCT registrable domains
(mirrors the QA gate's ``_source_contradiction_domains`` notion — count-driven
over structured stance enums, never freeform prose, so it is injection-proof).

When such a conflict exists, the report should not hide it. This returns the
data the frontend ``ContradictionCard`` needs:

    {"source_a": {label, url, grade?}, "source_b": {...}, "from": tier, "to": tier}

``from``/``to`` are the evidence-strength tiers WITHOUT vs WITH the contradiction
cap (via :func:`mingjing.scoring.strength`), so the UI shows the honest confidence
demotion the conflict caused. Returns ``None`` when there is no cross-domain
conflict.
"""

from typing import Any

from . import scoring
from .collector import independence


def _domain(sources: dict[str, Any], source_id: Any) -> str:
    src = sources.get(source_id, {}) if source_id is not None else {}
    return independence.registrable_domain(src.get("url", "") or "")


def _source_card(ev: dict[str, Any], domain: str, sources: dict[str, Any]) -> dict[str, Any]:
    src = sources.get(ev.get("source_id"), {})
    out: dict[str, Any] = {"label": domain, "url": src.get("url", "") or ""}
    grade = ev.get("admiralty")
    if grade:
        out["grade"] = grade
    return out


def summarize_contradiction(
    evidence: list[dict[str, Any]], sources: dict[str, Any]
) -> dict[str, Any] | None:
    """ContradictionCard data for a claim, or ``None`` if no cross-domain conflict."""
    supports: list[tuple[dict[str, Any], str]] = []
    refutes: list[tuple[dict[str, Any], str]] = []
    for ev in evidence:
        # Evidence items may be plain source-id strings (synthetic rows) instead
        # of dicts; a bare id carries no stance, so it can't be a conflict.
        if not isinstance(ev, dict):
            continue
        # SIMULATED (fixture-seeded) rows can be NEITHER side of a visible
        # ContradictionCard: synthetic data must not manufacture a displayed
        # conflict any more than it may cap a tier (mirrors the qa.rules
        # _source_contradiction_domains filter).
        if not scoring.contributes_to_tier(sources.get(ev.get("source_id"), {})):
            continue
        domain = _domain(sources, ev.get("source_id"))
        if not domain:
            continue
        stance = ev.get("stance", "supports")
        if stance == "supports":
            supports.append((ev, domain))
        elif stance == "refutes":
            refutes.append((ev, domain))

    pair = next(
        ((se, sd, re_, rd) for se, sd in supports for re_, rd in refutes if sd != rd),
        None,
    )
    if pair is None:
        return None
    support_ev, support_dom, refute_ev, refute_dom = pair

    tuples = [
        (
            sources.get(ev.get("source_id"), {}).get("source_type", "web"),
            ev.get("relevance", "unrelated"),
            _domain(sources, ev.get("source_id")),
        )
        for ev in evidence
        if isinstance(ev, dict)
        # Simulated rows never feed the from/to tier projection either.
        and scoring.contributes_to_tier(sources.get(ev.get("source_id"), {}))
    ]
    return {
        "source_a": _source_card(support_ev, support_dom, sources),
        "source_b": _source_card(refute_ev, refute_dom, sources),
        "from": scoring.strength(sources=tuples, contradiction=False),
        "to": scoring.strength(sources=tuples, contradiction=True),
    }
