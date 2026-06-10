"""Unit tests for the bounded competitor-discovery pre-step (``discovery.py``).

All tests are PURE: the orchestration test injects a deterministic fake
``search_fn`` so no network is touched. The properties under test are the
guarantees the runner relies on — bounded query count, deterministic ranking,
seeds always included, top-N clamp, and error-tolerant degradation.
"""

from __future__ import annotations

from mingjing.discovery import (
    Candidate,
    build_discovery_queries,
    discover_competitors,
    extract_candidates,
    rank_candidates,
)

# ---------------------------------------------------------------------------
# build_discovery_queries
# ---------------------------------------------------------------------------


def test_queries_are_bounded() -> None:
    qs = build_discovery_queries("CRM", max_queries=2)
    assert len(qs) == 2


def test_queries_clamp_high_and_low() -> None:
    assert len(build_discovery_queries("CRM", max_queries=99)) <= 6
    assert len(build_discovery_queries("CRM", max_queries=0)) == 1


def test_queries_empty_category() -> None:
    assert build_discovery_queries("   ") == []


def test_queries_scope_token_localized() -> None:
    qs = build_discovery_queries("AI Agent", market_scope="china", max_queries=6)
    assert any("中国" in q for q in qs)


def test_queries_scope_passthrough_raw() -> None:
    qs = build_discovery_queries("CRM", market_scope="EMEA", max_queries=6)
    assert any("EMEA" in q for q in qs)


def test_queries_goal_appended() -> None:
    qs = build_discovery_queries("CRM", goal="pricing", max_queries=6)
    assert any("pricing" in q for q in qs)


def test_queries_deduped() -> None:
    qs = build_discovery_queries("CRM", max_queries=6)
    assert len(qs) == len({q.lower() for q in qs})


# ---------------------------------------------------------------------------
# extract_candidates
# ---------------------------------------------------------------------------


def _previews() -> list[dict[str, str]]:
    return [
        {"url": "https://linear.app/pricing", "title": "Linear – Plan and build products", "snippet": "Linear is the issue tracker."},
        {"url": "https://g2.com/categories/project", "title": "Best Project Tools | G2", "snippet": "Compare Linear, Asana, and Jira."},
        {"url": "https://asana.com/", "title": "Asana · Manage your team's work", "snippet": "Asana project management."},
        {"url": "https://techcrunch.com/2026/01/01/linear", "title": "Linear raises a round | TechCrunch", "snippet": "Linear and Asana compete."},
    ]


def test_extract_finds_official_brands() -> None:
    cands = extract_candidates(_previews(), category="project management")
    names = {c.name.lower() for c in cands}
    assert "linear" in names
    assert "asana" in names


def test_extract_official_flag_and_source_count() -> None:
    cands = {c.name.lower(): c for c in extract_candidates(_previews(), category="project")}
    linear = cands["linear"]
    assert linear.has_official is True
    # linear.app (official) + g2 + techcrunch mention it -> >= 2 distinct domains.
    assert linear.source_count >= 2


def test_extract_filters_noise_domains() -> None:
    # g2 / techcrunch are aggregators/press: never candidates themselves.
    cands = {c.name.lower() for c in extract_candidates(_previews(), category="project")}
    assert "g2" not in cands
    assert "techcrunch" not in cands


def test_extract_tolerates_garbage() -> None:
    bad = [{"url": ""}, {"title": "no url"}, "not a dict", {"url": "http://"}]
    assert extract_candidates(bad, category="x") == []  # type: ignore[arg-type]


def test_extract_skips_category_words() -> None:
    previews = [{"url": "https://example.com/crm", "title": "CRM - the best CRM", "snippet": "crm"}]
    cands = {c.name.lower() for c in extract_candidates(previews, category="CRM")}
    assert "crm" not in cands


def test_extract_folds_cjk_alias_into_ascii_sibling() -> None:
    # "扣子 Coze" (title head) must merge into "Coze" (domain brand), not double-count.
    previews = [
        {"url": "https://coze.com/", "title": "Coze - AI agent platform", "snippet": "Coze"},
        {"url": "https://coze.cn/", "title": "扣子 Coze - 新一代 AI 应用开发平台", "snippet": "扣子 Coze"},
    ]
    names = [c.name for c in extract_candidates(previews, category="AI agent")]
    coze_like = [n for n in names if "coze" in n.lower()]
    assert len(coze_like) == 1  # one product, one candidate


def test_extract_short_ascii_slug_no_substring_falsepos() -> None:
    # A 2-char brand "Go" must NOT be credited a mention from inside "mango".
    previews = [
        {"url": "https://go.dev/", "title": "Go - programming", "snippet": "Go language"},
        {"url": "https://fruitblog.example/", "title": "Mango recipes", "snippet": "fresh mango smoothie"},
    ]
    go = next((c for c in extract_candidates(previews, category="lang") if c.name.lower() == "go"), None)
    assert go is not None
    # Only its official domain counts — the mango blog must not be credited.
    assert go.source_count == 1
    assert "fruitblog.example" not in go.domains


def test_extract_collapses_whitespace_in_name() -> None:
    previews = [{"url": "https://x.example/", "title": "Acme\n  Tool - the agent", "snippet": "Acme"}]
    names = [c.name for c in extract_candidates(previews, category="agent")]
    assert all("\n" not in n for n in names)


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


def test_rank_seeds_always_first() -> None:
    cands = [Candidate(name="Discovered", domains={"d.com"}, source_count=9, has_official=True)]
    out = rank_candidates(cands, max_competitors=4, seed_competitors=("Seed",))
    assert out[0] == "Seed"
    assert "Discovered" in out


def test_rank_clamps_to_max() -> None:
    cands = [Candidate(name=f"P{i}", domains={f"{i}.com"}, source_count=i) for i in range(10)]
    assert len(rank_candidates(cands, max_competitors=3)) == 3


def test_rank_official_outranks_more_sources() -> None:
    cands = [
        Candidate(name="Popular", domains={"a.com", "b.com", "c.com"}, source_count=3, has_official=False),
        Candidate(name="Official", domains={"official.com"}, source_count=1, has_official=True),
    ]
    out = rank_candidates(cands, max_competitors=2)
    assert out[0] == "Official"


def test_rank_deduplicates_seed_and_discovery() -> None:
    cands = [Candidate(name="linear", domains={"linear.app"}, source_count=2, has_official=True)]
    out = rank_candidates(cands, max_competitors=4, seed_competitors=("Linear",))
    # Same product via seed + discovery -> appears once.
    assert sum(1 for n in out if n.lower() == "linear") == 1


def test_rank_is_deterministic() -> None:
    cands = [
        Candidate(name="A", domains={"a.com"}, source_count=2),
        Candidate(name="B", domains={"b.com"}, source_count=2),
    ]
    first = rank_candidates(cands, max_competitors=2)
    second = rank_candidates(cands, max_competitors=2)
    assert first == second


# ---------------------------------------------------------------------------
# discover_competitors (orchestration, fake search_fn)
# ---------------------------------------------------------------------------


def test_discover_is_query_bounded() -> None:
    calls: list[str] = []

    def fake_search(q: str) -> list[dict[str, str]]:
        calls.append(q)
        return _previews()

    discover_competitors("project management", search_fn=fake_search, max_queries=2)
    assert len(calls) == 2  # exactly max_queries searches, no more.


def test_discover_returns_bounded_selection() -> None:
    res = discover_competitors(
        "project management", search_fn=lambda q: _previews(), max_competitors=2
    )
    assert len(res.selected) <= 2
    assert res.queries  # the queries actually issued are reported back.


def test_discover_includes_seeds() -> None:
    res = discover_competitors(
        "project management",
        search_fn=lambda q: _previews(),
        seed_competitors=("MySeed",),
        max_competitors=4,
    )
    assert "MySeed" in res.selected


def test_discover_error_degrades_to_seeds() -> None:
    def boom(q: str) -> list[dict[str, str]]:
        raise RuntimeError("network down")

    res = discover_competitors(
        "x", search_fn=boom, seed_competitors=("Fallback",), max_competitors=4
    )
    assert res.selected == ["Fallback"]
    assert res.candidates == []


def test_discover_payload_roundtrip() -> None:
    res = discover_competitors("project", search_fn=lambda q: _previews(), max_competitors=3)
    payload = res.as_payload()
    assert set(payload) == {"selected", "candidates", "queries"}
    assert payload["selected"] == res.selected
