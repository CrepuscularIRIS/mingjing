"""Unit tests for the transparent 3-tier evidence-strength scorer.

Plan Task 11 / spec §13 (PURE test #3). No decimals anywhere — the output is one
of three tiers. ``sources`` is a list of ``(source_type, relevance,
registrable_domain)`` tuples; supports are deduped by registrable domain so two
same-domain sources count as one voice; ``contradiction`` caps an
otherwise-strong claim at moderate.
"""

from mingjing.scoring import strength


def test_strong() -> None:
    # >=2 independent supports (distinct domains), >=1 of {official, survey}, no contradiction.
    assert (
        strength(
            sources=[
                ("official", "supports", "vendor.com"),
                ("review", "supports", "g2.com"),
            ],
            contradiction=False,
        )
        == "strong"
    )


def test_strong_with_survey() -> None:
    assert (
        strength(
            sources=[
                ("survey", "supports", "research.org"),
                ("news", "supports", "techcrunch.com"),
            ],
            contradiction=False,
        )
        == "strong"
    )


def test_moderate_single() -> None:
    # Exactly one supports source -> moderate.
    assert (
        strength(sources=[("review", "supports", "g2.com")], contradiction=False)
        == "moderate"
    )


def test_moderate_two_but_all_weak_types() -> None:
    # >=2 supports (distinct domains) but none official/survey (all weak types) -> moderate.
    assert (
        strength(
            sources=[
                ("news", "supports", "techcrunch.com"),
                ("forum", "supports", "reddit.com"),
            ],
            contradiction=False,
        )
        == "moderate"
    )


def test_moderate_two_supports_same_domain() -> None:
    # Two supports on the SAME registrable domain collapse to one voice; even
    # with an authoritative type, a single distinct domain cannot reach strong.
    assert (
        strength(
            sources=[
                ("official", "supports", "vendor.com"),
                ("review", "supports", "vendor.com"),
            ],
            contradiction=False,
        )
        == "moderate"
    )


def test_strong_interview_is_authoritative() -> None:
    # interview is primary-research evidence: two distinct domains with one
    # interview source reaches strong, identically to survey/official.
    assert (
        strength(
            sources=[
                ("interview", "supports", "primary-research"),
                ("review", "supports", "g2.com"),
            ],
            contradiction=False,
        )
        == "strong"
    )


def test_weak_no_supports() -> None:
    # No relevance == "supports" evidence -> weak.
    assert (
        strength(sources=[("forum", "unrelated", "reddit.com")], contradiction=False)
        == "weak"
    )


def test_weak_empty() -> None:
    assert strength(sources=[], contradiction=False) == "weak"


def test_contradiction_caps() -> None:
    # Would-be strong, but an unresolved contradiction caps it at moderate.
    assert (
        strength(
            sources=[
                ("official", "supports", "vendor.com"),
                ("survey", "supports", "research.org"),
            ],
            contradiction=True,
        )
        == "moderate"
    )


def test_contradiction_does_not_promote_weak() -> None:
    # Contradiction only caps; it never lifts a no-support claim above weak.
    assert (
        strength(sources=[("forum", "unrelated", "reddit.com")], contradiction=True)
        == "weak"
    )
