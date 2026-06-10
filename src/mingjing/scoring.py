"""Transparent 3-tier evidence-strength scorer (plan Task 11 / spec §13).

A deliberately *legible* rule — no confidence decimals, no opaque model — so a
judge can read why a claim is strong/moderate/weak. ``strength`` is pure.

The rule, given ``sources`` as a list of ``(source_type, relevance,
registrable_domain)`` tuples and a ``contradiction`` flag. Supporting sources
are first deduped by registrable domain — two sources on the same domain are one
voice (a vendor's blog and its pricing page are not independent), so both the
support count and the "≥2" gate operate on DISTINCT registrable domains:

- **strong**  — at least two *distinct supporting domains* AND at least one of
  the supporting sources is an authoritative type ``{official, survey, interview}``
  AND no unresolved contradiction.
- **moderate** — exactly one distinct supporting domain; OR ≥2 distinct
  supporting domains but all from weak types ``{news, forum, review}``; OR an
  otherwise-strong claim whose contradiction flag is set (contradiction *caps*
  at moderate, never below).
- **weak**     — no ``supports`` evidence at all.

A contradiction can only ever lower a strong claim to moderate; it never promotes
a weak claim.
"""

from typing import Literal

Strength = Literal["strong", "moderate", "weak"]

# Authoritative source types — at least one is required for a strong tier.
# Both `survey` and `interview` are primary-research (human-collected) evidence;
# they lift strength identically. Secondary web types (news/forum/review) do not.
# This matches survey_seed.py, which already seeds interview rows as authoritative.
AUTHORITATIVE_TYPES = frozenset({"official", "survey", "interview"})
# Weak source types — two of these alone cannot reach strong.
WEAK_TYPES = frozenset({"news", "forum", "review"})

# Demo-fixture survey/interview rows are seeded with this source_mode. They are
# DISPLAY-ONLY for credibility: visible (with a 模拟数据 label) and usable for
# verbatim grounding, but they contribute ZERO to the 3-tier scorer, the
# corroboration counters, and contradiction detection — simulated data must not
# mint, lift, or cap any credibility quantity. A REAL ingested survey
# (source_mode="INGESTED") keeps its authoritative lift.
SIMULATED_SOURCE_MODE = "SIMULATED"


def contributes_to_tier(source_row: dict | None) -> bool:
    """True when ``source_row`` may feed credibility computations.

    Simulated (fixture-seeded) rows are excluded ENTIRELY — not merely treated
    as non-authoritative, because a second supporting domain alone can flip the
    ``>=2 distinct domains`` gate even without authority.
    """
    return (source_row or {}).get("source_mode") != SIMULATED_SOURCE_MODE


def strength(*, sources: list[tuple[str, str, str]], contradiction: bool) -> Strength:
    """Score evidence strength into one of three tiers.

    Args:
        sources: ``(source_type, relevance, registrable_domain)`` tuples;
            ``relevance == "supports"`` marks a source that supports the claim.
            Supporting sources are deduped by ``registrable_domain`` so two
            same-domain sources count as a single independent voice.
        contradiction: ``True`` when there is an unresolved contradicting source.

    Returns:
        ``"strong"`` | ``"moderate"`` | ``"weak"``.
    """
    # Collapse supports to one entry per registrable domain. Keep the strongest
    # (authoritative) type seen for each domain so a domain with any
    # authoritative source counts as authoritative.
    domain_authoritative: dict[str, bool] = {}
    for stype, relevance, domain in sources:
        if relevance != "supports":
            continue
        key = domain or ""  # blank-domain supports still count as one bucket
        is_auth = stype in AUTHORITATIVE_TYPES
        domain_authoritative[key] = domain_authoritative.get(key, False) or is_auth

    # No supporting evidence -> weak. Contradiction cannot promote this.
    if not domain_authoritative:
        return "weak"

    # Fewer than two distinct supporting domains -> moderate.
    if len(domain_authoritative) < 2:
        return "moderate"

    # >=2 distinct supporting domains: strong requires an authoritative type
    # among the supporting set AND no contradiction.
    has_authoritative = any(domain_authoritative.values())
    if not has_authoritative:
        # >=2 distinct domains but all weak types -> moderate.
        return "moderate"

    # Otherwise-strong; a contradiction caps it at moderate.
    if contradiction:
        return "moderate"

    return "strong"
