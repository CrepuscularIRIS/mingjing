"""SAFETY INVARIANT for 维度5: classifying a source as review/forum (instead of
the generic 'web') must NOT change the 3-tier evidence strength.

review/forum are non-authoritative (not in scoring.AUTHORITATIVE_TYPES) exactly
like 'web', so the tier — a function of distinct registrable domains + presence of
an authoritative type + contradiction — must be byte-identical when a non-auth
source is relabelled web↔review↔forum.
"""

from __future__ import annotations

import pytest

from mingjing.scoring import AUTHORITATIVE_TYPES, strength

NON_AUTH = ["web", "review", "forum", "news"]


def test_review_forum_not_authoritative() -> None:
    assert "review" not in AUTHORITATIVE_TYPES
    assert "forum" not in AUTHORITATIVE_TYPES


def test_review_forum_same_admiralty_letter_as_web() -> None:
    # The load-bearing claim behind 维度5: review/forum carry the SAME Admiralty
    # reliability letter (D) as a generic web page, so relabelling web->review/forum
    # changes neither the legend letter nor any Admiralty-derived ranking.
    from mingjing.admiralty import reliability_letter

    assert reliability_letter("web") == "D"
    assert reliability_letter("review") == reliability_letter("web")
    assert reliability_letter("forum") == reliability_letter("web")


@pytest.mark.parametrize("stype", NON_AUTH)
def test_two_nonauth_domains_is_moderate_regardless_of_label(stype: str) -> None:
    # 2 distinct domains, no authoritative type → moderate, for ANY non-auth label.
    s = strength(
        sources=[(stype, "supports", "a.com"), (stype, "supports", "b.com")],
        contradiction=False,
    )
    assert s == "moderate"


@pytest.mark.parametrize("stype", NON_AUTH)
def test_single_nonauth_domain_is_moderate_regardless_of_label(stype: str) -> None:
    # 1 distinct supporting domain → moderate (weak = NO support), for ANY label.
    s = strength(sources=[(stype, "supports", "a.com")], contradiction=False)
    assert s == "moderate"


def test_official_plus_review_still_strong_like_official_plus_web() -> None:
    # An authoritative source + a second distinct domain → strong; the second
    # source's non-auth label (web vs review) must not change the outcome.
    base = strength(
        sources=[("official", "supports", "vendor.com"), ("web", "supports", "x.com")],
        contradiction=False,
    )
    relabelled = strength(
        sources=[("official", "supports", "vendor.com"), ("review", "supports", "x.com")],
        contradiction=False,
    )
    assert base == relabelled == "strong"
