"""Wiring tests for Discovery Mode: api_models, db round-trip, runner pre-step.

The pure discovery core is covered by ``tests/test_discovery.py``; this file
covers the integration seams the runner relies on — request validation, the new
runs columns, ``update_run_competitors``, and the runner's best-effort discovery
pre-step (Directed Mode must NOT discover; Discovery Mode must discover, persist,
and trace).
"""

from __future__ import annotations

import pytest

from mingjing.api_models import CreateRunRequest
from mingjing.db import Database
from mingjing.discovery import DiscoveryResult
from mingjing.runner import _discover_competitors_best_effort

# ---------------------------------------------------------------------------
# api_models validation
# ---------------------------------------------------------------------------


def test_request_directed_mode_ok() -> None:
    req = CreateRunRequest(category="crm", competitors=["A", "B"], goal="g")
    assert req.competitors == ["A", "B"]
    assert req.max_competitors == 4  # default


def test_request_discovery_mode_ok_without_competitors() -> None:
    req = CreateRunRequest(category="通用 AI Agent", goal="g", market_scope="china")
    assert req.competitors == []
    assert req.market_scope == "china"


def test_request_rejects_empty_competitors_and_empty_category() -> None:
    with pytest.raises(ValueError, match="Directed Mode|Discovery Mode"):
        CreateRunRequest(category="   ", competitors=[], goal="g")


def test_request_clamps_max_competitors() -> None:
    assert CreateRunRequest(category="x", competitors=["a"], goal="g", max_competitors=99).max_competitors == 6
    assert CreateRunRequest(category="x", competitors=["a"], goal="g", max_competitors=0).max_competitors == 1


# ---------------------------------------------------------------------------
# db round-trip + update_run_competitors
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "run.db"))
    d.init_schema()
    return d


def test_create_run_persists_discovery_params(db: Database) -> None:
    run_id = db.create_run(
        category="cat",
        competitors=[],
        goal="g",
        market_scope="china",
        max_competitors=3,
        seed_competitors=["Seed"],
    )
    row = db.get_run(run_id)
    assert row is not None
    assert row["competitors"] == []
    assert row["market_scope"] == "china"
    assert row["max_competitors"] == 3
    assert row["seed_competitors"] == ["Seed"]


def test_update_run_competitors(db: Database) -> None:
    run_id = db.create_run(category="cat", competitors=[], goal="g")
    db.update_run_competitors(run_id, ["X", "Y"])
    assert db.get_run(run_id)["competitors"] == ["X", "Y"]


# ---------------------------------------------------------------------------
# runner discovery pre-step (best-effort)
# ---------------------------------------------------------------------------


def _event_types(db: Database, run_id: str) -> set[str]:
    return {e["event_type"] for e in db.trace_events_for_run(run_id)}


def test_discovery_pre_step_persists_and_traces(db: Database) -> None:
    run_id = db.create_run(category="project management", competitors=[], goal="g")
    run_row = db.get_run(run_id)

    def fake_discover(category, **kwargs):
        return DiscoveryResult(
            selected=["Linear", "Asana"],
            candidates=[{"name": "Linear", "source_count": 3, "has_official": True}],
            queries=["q1"],
        )

    selected = _discover_competitors_best_effort(
        db, run_id, run_row, discover_fn=fake_discover
    )
    assert selected == ["Linear", "Asana"]
    assert db.get_run(run_id)["competitors"] == ["Linear", "Asana"]
    assert {"discovery_started", "competitors_discovered"} <= _event_types(db, run_id)


def test_discovery_pre_step_empty_result_traces_empty(db: Database) -> None:
    run_id = db.create_run(category="x", competitors=[], goal="g")
    run_row = db.get_run(run_id)

    def empty_discover(category, **kwargs):
        return DiscoveryResult(selected=[], candidates=[], queries=["q"])

    selected = _discover_competitors_best_effort(
        db, run_id, run_row, discover_fn=empty_discover
    )
    assert selected == []
    assert db.get_run(run_id)["competitors"] == []  # nothing persisted
    assert "discovery_empty" in _event_types(db, run_id)


def test_discovery_pre_step_error_degrades_to_seeds(db: Database) -> None:
    run_id = db.create_run(
        category="x", competitors=[], goal="g", seed_competitors=["Fallback"]
    )
    run_row = db.get_run(run_id)

    def boom(category, **kwargs):
        raise RuntimeError("discovery exploded")

    selected = _discover_competitors_best_effort(
        db, run_id, run_row, discover_fn=boom
    )
    assert selected == ["Fallback"]
    assert db.get_run(run_id)["competitors"] == ["Fallback"]


def test_directed_mode_skips_discovery_in_executor(tmp_path) -> None:
    """When competitors are provided, the executor never calls discover_fn."""
    from mingjing.runner import make_run_executor

    d = Database(str(tmp_path / "run.db"))
    d.init_schema()
    run_id = d.create_run(category="cat", competitors=["Provided"], goal="g")

    calls: list[str] = []

    def spy_discover(category, **kwargs):
        calls.append(category)
        return DiscoveryResult(selected=["Should", "Not", "Happen"], candidates=[], queries=[])

    def empty_collect(query, *, cache, source_cap, mode="live_first"):
        return []

    executor = make_run_executor(
        get_db=lambda: d,
        settings=_min_settings(tmp_path),
        collect_fn=empty_collect,
        discover_fn=spy_discover,
        prewarm=False,
    )
    executor(run_id)
    assert calls == []  # Directed Mode -> discovery never invoked.
    assert d.get_run(run_id)["competitors"] == ["Provided"]


@pytest.mark.slow
def test_closed_loop_discovery_produces_claims(tmp_path) -> None:
    """category → discover(Notion,Linear) → collect-from-corpus → analyze → claims.

    Proves the SAME run goes from a bare category to a populated, analyzed report
    via the real merged corpus (no fake evidence; analyst is faked only to keep
    the test offline+deterministic — the demo script uses the real analyst).
    """
    from mingjing.collector.cache import Cache
    from mingjing.demo.corpus import load_corpus, make_demo_collect_fn
    from mingjing.discovery import DiscoveryResult
    from mingjing.runner import make_run_executor

    d = Database(str(tmp_path / "run.db"))
    d.init_schema()
    run_id = d.create_run(
        category="团队协作 / 项目管理工具", competitors=[], goal="g",
        market_scope="global", max_competitors=2,
    )

    merged: dict = {}
    for name in ("notion", "linear"):
        merged.update(load_corpus(f"demo/corpus/{name}.json"))

    def discover_fn(category, **kwargs):
        return DiscoveryResult(selected=["Notion", "Linear"], candidates=[], queries=["q"])

    def fake_analyze(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        ids = sorted(source_ids)
        return {
            "statement": f"{competitor} {field} claim",
            "claim_type": "fact",
            "value": {"k": "v"},
            "evidence_ref": ids if len(ids) >= 1 else [],
        }

    settings = _min_settings(tmp_path)
    with Cache(settings.cache_db_path):
        executor = make_run_executor(
            lambda: d,
            settings=settings,
            discover_fn=discover_fn,
            collect_fn=make_demo_collect_fn(merged),
            analyze_fn=fake_analyze,
            prewarm=False,
        )
        executor(run_id)

    assert d.get_run(run_id)["competitors"] == ["Notion", "Linear"]  # discovery wired
    assert d.latest_claims_for_run(run_id), "closed loop should produce claims"  # analysis ran


def _min_settings(tmp_path):
    from mingjing.config import Settings

    return Settings(
        minimax_base_url="https://example.invalid/v1",
        minimax_api_key="",
        minimax_model="test-model",
        mode="live_first",
        rate_limiting_enabled=True,
        db_path=str(tmp_path / "run.db"),
        cache_db_path=str(tmp_path / "cache.db"),
        per_field_source_cap=3,
        min_source_chars=0,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth="quick",
        deep_collect_workers=8,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
    )
