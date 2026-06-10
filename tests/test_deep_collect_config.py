from mingjing.config import DEPTH_TIERS, tier_for


def test_quick_tier_knobs():
    t = tier_for("quick")
    assert t.sub_queries == 5 and "duckduckgo" in t.engines and t.top_k == 8
    # bocha is the CN-reachable primary engine
    assert "bocha" in t.engines


def test_detailed_tier_is_deeper():
    q, d = tier_for("quick"), tier_for("detailed")
    assert d.sub_queries > q.sub_queries and d.top_k > q.top_k
    assert "brave" in d.engines
    # exact detailed values
    assert d.sub_queries == 8
    assert d.top_k == 12
    assert d.engines == ("bocha", "tavily", "brave", "searxng", "duckduckgo")


def test_unknown_depth_falls_back_to_quick():
    assert tier_for("bogus").sub_queries == tier_for("quick").sub_queries


def test_depth_tiers_registry_contract():
    """DEPTH_TIERS["quick"] is the same object returned by tier_for("quick")."""
    assert tier_for("quick") is DEPTH_TIERS["quick"]
    assert tier_for("detailed") is DEPTH_TIERS["detailed"]


def test_settings_load_reads_new_fields(monkeypatch):
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_DEPTH", "detailed")
    from mingjing.config import Settings
    s = Settings.load()
    assert s.depth == "detailed"
    assert s.deep_collect_workers == 8
    assert s.fetch_budget_per_run == 60
    assert s.firecrawl_api_key == ""
    assert s.firecrawl_base_url == "https://api.firecrawl.dev/v1"
