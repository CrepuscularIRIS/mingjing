"""Tests for collector/dedupe.py — dedupe_and_rank (pure, deterministic, no I/O).

All tests are offline.  Where authority differentiation is needed we monkeypatch
``infer_source_type`` so the test does not depend on URL-token matching logic.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mingjing.collector.dedupe import _SPAM_PENALTY, DEFAULT_SOURCE_WEIGHTS, dedupe_and_rank

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(url: str, engine: str = "google", title: str = "T", snippet: str = "S") -> dict:
    """Build a minimal preview dict."""
    return {"url": url, "title": title, "snippet": snippet, "engine": engine}


# ---------------------------------------------------------------------------
# test_exact_url_dedup
# ---------------------------------------------------------------------------

def test_exact_url_dedup() -> None:
    """Same URL returned by 2 engines → one entry with agreement == 2."""
    previews = [
        _p("https://feishu.cn/pricing", engine="google"),
        _p("https://feishu.cn/pricing", engine="bing"),
    ]
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="feishu")
    assert len(results) == 1
    assert results[0]["agreement"] == 2
    assert results[0]["url"] == "https://feishu.cn/pricing"


# ---------------------------------------------------------------------------
# test_per_domain_cap
# ---------------------------------------------------------------------------

def test_per_domain_cap() -> None:
    """3 URLs on the same registrable domain with cap=2 → exactly 2 kept."""
    previews = [
        _p("https://feishu.cn/page1"),
        _p("https://feishu.cn/page2"),
        _p("https://feishu.cn/page3"),
    ]
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=2, competitor="feishu")
    assert len(results) == 2


# ---------------------------------------------------------------------------
# test_authoritative_ranks_above_forum
# ---------------------------------------------------------------------------

def test_authoritative_ranks_above_forum() -> None:
    """An official-typed URL ranks above a forum/web-typed URL."""
    previews = [
        _p("https://forum.example.com/thread/1"),
        _p("https://official.example.com/product"),
    ]

    def _fake_infer(url: str, competitor: str) -> str:
        if "official" in url:
            return "official"
        return "forum"

    with patch("mingjing.collector.dedupe.infer_source_type", side_effect=_fake_infer):
        results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="example")

    assert len(results) == 2
    urls = [r["url"] for r in results]
    assert urls.index("https://official.example.com/product") < urls.index(
        "https://forum.example.com/thread/1"
    )


# ---------------------------------------------------------------------------
# test_new_registrable_domain_independence_bonus
# ---------------------------------------------------------------------------

def test_new_registrable_domain_independence_bonus() -> None:
    """First URL of each distinct registrable domain receives the independence bonus."""
    previews = [
        _p("https://siteA.com/page1"),
        _p("https://siteB.com/page1"),
    ]

    # Both are "web" — the only differentiator should be the independence bonus.
    # With two completely new domains both get the bonus; quality should be equal
    # (stable order preserved).  Confirm both carry quality > 0.
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="X")
    assert len(results) == 2
    for r in results:
        assert r["quality"] > 0, f"Expected quality > 0, got {r['quality']}"


def test_new_registrable_domain_independence_bonus_ordering() -> None:
    """First-seen URL per registrable domain earns the independence bonus; later
    URLs from the same domain do not."""
    previews = [
        _p("https://siteA.com/page1"),   # first from siteA — gets bonus
        _p("https://siteA.com/page2"),   # second from siteA — no bonus
        _p("https://siteB.com/page1"),   # first from siteB — gets bonus
    ]
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="X")
    url_to_quality = {r["url"]: r["quality"] for r in results}
    # page1 (first-seen from siteA) should have higher quality than page2 (second from siteA)
    assert url_to_quality["https://siteA.com/page1"] > url_to_quality["https://siteA.com/page2"]


# ---------------------------------------------------------------------------
# test_cross_engine_agreement_breaks_ties
# ---------------------------------------------------------------------------

def test_cross_engine_agreement_breaks_ties() -> None:
    """Two same-authority, same-domain-bonus URLs: the one from 2 engines ranks higher."""
    previews = [
        _p("https://siteA.com/page1", engine="google"),
        _p("https://siteA.com/page1", engine="bing"),  # same URL — agreement=2
        _p("https://siteA.com/page2", engine="google"),  # agreement=1
    ]
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="X")
    # page1 was seen by 2 engines, page2 by 1 — page1 should rank first
    assert results[0]["url"] == "https://siteA.com/page1"
    assert results[0]["agreement"] == 2


# ---------------------------------------------------------------------------
# test_typosquat_penalized_below_genuine_independent
# ---------------------------------------------------------------------------

def test_typosquat_penalized_below_genuine_independent() -> None:
    """Spam penalty is what pushes the typosquat below the genuine source.

    Setup: the typosquat gets 3 cross-engine agreement hits so that PRE-PENALTY
    it would outscore the genuine independent.  Only _SPAM_PENALTY drops it
    below.  This verifies that the penalty is actually exercised (not that
    authority alone separated the two).

    Source types:
      feishu.cn/home  → official (auth=4) — shorter label, higher authority
      feiishu.com.cn  → web      (auth=2) — longer label (+1 char edit-dist),
                                            lower authority → penalty fires
      36kr.com        → news     (auth=3) — genuine independent

    Pre-penalty scores (independence bonus = +1 each, all first-seen domains):
      feishu.cn    : 4 + 1 + 1 = 6
      feiishu      : 2 + 1 + 3 = 6  (3 engines → agreement=3; ties/beats genuine)
      36kr         : 3 + 1 + 1 = 5

    After penalty:
      feiishu      : 6 - 5 = 1  → drops below genuine (5)
    """
    previews = [
        _p("https://feishu.cn/home", engine="google"),
        # typosquat seen by 3 engines → pre-penalty quality ties feishu.cn
        _p("https://feiishu.com.cn/home", engine="google"),
        _p("https://feiishu.com.cn/home", engine="bing"),
        _p("https://feiishu.com.cn/home", engine="sogou"),
        _p("https://36kr.com/article/123", engine="google"),
    ]

    def _fake_infer(url: str, competitor: str) -> str:
        if "feishu.cn" in url and "feiishu" not in url:
            return "official"   # auth weight 4
        if "36kr" in url:
            return "news"       # auth weight 3
        return "web"            # auth weight 2 (feiishu typosquat)

    with patch("mingjing.collector.dedupe.infer_source_type", side_effect=_fake_infer):
        results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="feishu")

    url_to_quality = {r["url"]: r["quality"] for r in results}
    typosquat_q = url_to_quality["https://feiishu.com.cn/home"]
    genuine_q = url_to_quality["https://36kr.com/article/123"]

    # Pre-penalty: feiishu (auth=2 + bonus=1 + agreement=3 = 6) ≥ genuine (3+1+1=5)
    # Only the spam penalty brings it below.
    assert typosquat_q < genuine_q, (
        f"Expected typo-squat quality ({typosquat_q}) < genuine ({genuine_q})"
    )
    # Confirm the penalty is reflected in the returned quality value.
    expected_pre_penalty = 2.0 + 1.0 + 3.0  # auth + independence + agreement
    assert typosquat_q == pytest.approx(expected_pre_penalty - _SPAM_PENALTY), (
        f"Typosquat quality {typosquat_q} != pre-penalty {expected_pre_penalty} - "
        f"_SPAM_PENALTY {_SPAM_PENALTY}"
    )


# ---------------------------------------------------------------------------
# test_top_k_truncation
# ---------------------------------------------------------------------------

def test_top_k_truncation() -> None:
    """More than top_k inputs → exactly top_k returned."""
    previews = [_p(f"https://site{i}.com/page") for i in range(20)]
    results = dedupe_and_rank(previews, top_k=5, per_domain_cap=10, competitor="X")
    assert len(results) == 5


# ---------------------------------------------------------------------------
# test_stable_order_on_ties
# ---------------------------------------------------------------------------

def test_stable_order_on_ties() -> None:
    """Equal scores preserve original (first-seen) input order."""
    # All 'web', distinct domains, single engine — identical scores.
    previews = [
        _p("https://alpha.com/p"),
        _p("https://beta.com/p"),
        _p("https://gamma.com/p"),
    ]
    results = dedupe_and_rank(previews, top_k=10, per_domain_cap=10, competitor="X")
    urls = [r["url"] for r in results]
    # All have equal quality; stable sort preserves input order.
    assert urls == ["https://alpha.com/p", "https://beta.com/p", "https://gamma.com/p"]


# ---------------------------------------------------------------------------
# Smoke: DEFAULT_SOURCE_WEIGHTS mirrors default.json
# ---------------------------------------------------------------------------

def test_default_source_weights_keys() -> None:
    """DEFAULT_SOURCE_WEIGHTS contains all expected source type keys."""
    expected = {"official", "news", "review", "survey", "forum", "web", "blog"}
    assert set(DEFAULT_SOURCE_WEIGHTS.keys()) == expected


def test_default_source_weights_values() -> None:
    """Admiralty letters map correctly (B=most, E=least authoritative)."""
    assert DEFAULT_SOURCE_WEIGHTS["official"] == "B"
    assert DEFAULT_SOURCE_WEIGHTS["news"] == "C"
    assert DEFAULT_SOURCE_WEIGHTS["blog"] == "E"


# ---------------------------------------------------------------------------
# Query relevance bonus — on-topic candidates outrank authoritative-irrelevant.
# ---------------------------------------------------------------------------

from mingjing.collector.dedupe import dedupe_and_rank as _dar  # noqa: E402


def test_relevance_lifts_ontopic_over_authoritative_irrelevant():
    """With a query, a relevant page outranks an authoritative but off-topic one."""
    previews = [
        # Authoritative (gov) but irrelevant to the query.
        {"url": "https://www.frbsf.org/report.pdf", "title": "Economic report",
         "snippet": "monetary policy analysis", "engine": "bing"},
        # Lower-authority but on-topic.
        {"url": "https://zhuanlan.zhihu.com/p/1", "title": "Notion 定价解析",
         "snippet": "Notion pricing tiers and plans", "engine": "bocha"},
    ]
    ranked = _dar(previews, top_k=2, per_domain_cap=2, competitor="", query="Notion pricing")
    assert ranked[0]["url"] == "https://zhuanlan.zhihu.com/p/1", "on-topic must rank first"


def test_empty_query_preserves_legacy_order():
    """No query → no relevance bonus → ranking identical to the legacy behavior."""
    previews = [
        {"url": "https://www.frbsf.org/report.pdf", "title": "Economic report",
         "snippet": "x", "engine": "bing"},
        {"url": "https://zhuanlan.zhihu.com/p/1", "title": "Notion 定价",
         "snippet": "Notion pricing", "engine": "bocha"},
    ]
    with_q = [r["url"] for r in _dar(previews, top_k=2, per_domain_cap=2, competitor="", query="")]
    # Both are distinct-domain D-grade with agreement 1 → tie → first-seen order kept.
    assert with_q == ["https://www.frbsf.org/report.pdf", "https://zhuanlan.zhihu.com/p/1"]
