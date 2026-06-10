"""Tests for per-run depth selection (Task 8).

Tests:
- test_post_runs_accepts_depth_detailed: POST with depth="detailed" → 201; persisted row has depth=="detailed".
- test_post_runs_defaults_depth_when_omitted: POST without depth → 201; persisted depth is "quick".
- test_post_runs_rejects_invalid_depth: POST depth="ludicrous" → 422.
- test_create_run_db_persists_and_reads_depth: db.create_run(..., depth="detailed") → get_run returns depth=="detailed".
- test_existing_db_migration_adds_depth_column: init_schema is idempotent (running it twice doesn't error).
- test_settings_for_run_uses_run_depth: _settings_for_run propagates run row depth to the returned settings.
- test_settings_for_run_falls_back_to_settings_depth: _settings_for_run falls back to active_settings.depth when run row has no depth.
- test_list_runs_includes_depth: db.list_runs returns depth in each summary dict.
"""

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Database:
    """A fresh, schema-initialised Database in a temp directory."""
    d = Database(str(tmp_path / "test.db"))
    d.init_schema()
    return d


@pytest.fixture()
def client(db: Database) -> TestClient:
    """A TestClient backed by the fresh DB; no executor injected."""
    app = create_app(db=db, run_executor=None)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_post_runs_accepts_depth_detailed(client: TestClient, db: Database) -> None:
    """POST with depth='detailed' → 201; persisted run row has depth=='detailed'."""
    resp = client.post(
        "/runs",
        json={
            "category": "CRM",
            "competitors": ["Acme"],
            "goal": "compare",
            "depth": "detailed",
        },
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    row = db.get_run(run_id)
    assert row is not None
    assert row["depth"] == "detailed"


def test_post_runs_defaults_depth_when_omitted(client: TestClient, db: Database) -> None:
    """POST without depth → 201; persisted depth defaults to 'quick'."""
    resp = client.post(
        "/runs",
        json={
            "category": "CRM",
            "competitors": ["Acme"],
            "goal": "compare",
        },
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    row = db.get_run(run_id)
    assert row is not None
    assert row["depth"] == "quick"


def test_post_runs_rejects_invalid_depth(client: TestClient) -> None:
    """POST with depth='ludicrous' → 422."""
    resp = client.post(
        "/runs",
        json={
            "category": "CRM",
            "competitors": ["Acme"],
            "goal": "compare",
            "depth": "ludicrous",
        },
    )
    assert resp.status_code == 422, resp.text


def test_create_run_db_persists_and_reads_depth(db: Database) -> None:
    """db.create_run(..., depth='detailed') → get_run returns depth=='detailed'."""
    run_id = db.create_run(
        category="CRM",
        competitors=["Acme", "BetaCo"],
        goal="compare pricing",
        depth="detailed",
    )
    row = db.get_run(run_id)
    assert row is not None
    assert row["depth"] == "detailed"


def test_existing_db_migration_adds_depth_column(tmp_path) -> None:
    """Running init_schema twice is idempotent (exercises the duplicate-column guard)."""
    db = Database(str(tmp_path / "compat.db"))
    # First call creates the tables including depth column.
    db.init_schema()
    # Second call must not raise — the duplicate-column migration guard prevents error.
    db.init_schema()
    # After second call, depth column must exist and defaults apply.
    run_id = db.create_run(
        category="SaaS",
        competitors=["Vendor"],
        goal="audit",
    )
    row = db.get_run(run_id)
    assert row is not None
    assert row["depth"] == "quick"


# ---------------------------------------------------------------------------
# Runner depth-plumbing: _settings_for_run pure-helper tests
# ---------------------------------------------------------------------------


def _make_settings(depth: str = "quick") -> object:
    """Build a minimal frozen Settings-like object for testing."""
    from mingjing.config import Settings

    return Settings(
        minimax_base_url="http://fake",
        minimax_api_key="",
        minimax_model="fake",
        mode="cache_first",
        rate_limiting_enabled=True,
        db_path=":memory:",
        cache_db_path=":memory:",
        per_field_source_cap=3,
        min_source_chars=100,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth=depth,
        deep_collect_workers=2,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="",
    )


def test_settings_for_run_uses_run_depth() -> None:
    """_settings_for_run propagates the run row's depth to the returned settings.

    This is the core depth-plumbing invariant: when a run row carries
    depth='detailed' but the app-level settings say 'quick', the returned
    settings object must use 'detailed' so make_default_collect_fn sees the
    right tier knobs.
    """
    from mingjing.runner import _settings_for_run

    base = _make_settings(depth="quick")
    run_row = {"depth": "detailed"}
    result = _settings_for_run(base, run_row)
    assert result.depth == "detailed", (
        f"expected 'detailed' but got {result.depth!r}; "
        "per-run depth must override the app-level setting"
    )
    # Original must be unchanged (frozen dataclass; replace returns new instance).
    assert base.depth == "quick"


def test_settings_for_run_falls_back_to_settings_depth() -> None:
    """_settings_for_run falls back to active_settings.depth when run row has no depth."""
    from mingjing.runner import _settings_for_run

    base = _make_settings(depth="detailed")
    # Run row with no depth key at all.
    result_no_key = _settings_for_run(base, {})
    assert result_no_key.depth == "detailed"

    # Run row with depth=None (falsy — treated as missing).
    result_none = _settings_for_run(base, {"depth": None})
    assert result_none.depth == "detailed"

    # Run row with depth="" (falsy — treated as missing).
    result_empty = _settings_for_run(base, {"depth": ""})
    assert result_empty.depth == "detailed"


def test_list_runs_includes_depth(db: Database) -> None:
    """db.list_runs() returns a 'depth' key in each summary dict."""
    db.create_run(
        category="CRM",
        competitors=["Acme"],
        goal="compare",
        depth="detailed",
    )
    db.create_run(
        category="CRM",
        competitors=["Beta"],
        goal="compare",
        # depth omitted → defaults to "quick"
    )
    runs = db.list_runs(limit=10)
    assert len(runs) == 2
    depths = {r["depth"] for r in runs}
    assert depths == {"quick", "detailed"}, f"unexpected depth set: {depths}"
