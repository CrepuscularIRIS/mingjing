"""The LangGraph skeleton must compile/instantiate (plan Task 10).

Live execution is deferred to Task 15; here we only assert the StateGraph builds
into a runnable, exposes all eight nodes, and that ``RunState`` carries the
expected field-keyed shape.
"""

from mingjing.graph import (
    _GRAPH_RECURSION_LIMIT,
    GraphDeps,
    RunState,
    _route_branch,
    build_graph,
    intake_node,
)


def test_graph_compiles() -> None:
    graph = build_graph()
    # A compiled LangGraph exposes get_graph(); nodes include our eight + I/O.
    nodes = set(graph.get_graph().nodes)
    expected = {"intake", "plan", "collect", "analyze", "qa", "route", "revise", "write"}
    assert expected <= nodes


def test_live_graph_sets_explicit_recursion_limit_backstop() -> None:
    """The live (deps-backed) graph carries an explicit recursion_limit ceiling.

    The pure router (qa/route.py) terminates the revise loop; this is only a
    defensive backstop so a wiring bug can never spin forever. The compile-only
    skeleton stays bare so its existing build/route tests are unaffected.
    """
    live = build_graph(deps=GraphDeps(db=None, cache=None, settings=None))
    assert (live.config or {}).get("recursion_limit") == _GRAPH_RECURSION_LIMIT
    # with_config must not change the runnable surface existing callers rely on.
    assert hasattr(live, "invoke")
    assert hasattr(live, "get_graph")
    # The skeleton path must NOT carry the override (bare compile).
    skeleton = build_graph()
    assert (skeleton.config or {}).get("recursion_limit") is None


def test_run_state_fields() -> None:
    keys = set(RunState.__annotations__)
    expected = {
        "run_id",
        "intake",
        "tasks",
        "sources",
        "claims",
        "qc_reports",
        "revision_round",
        "phase",
        "budget_calls",
        # Task 15a / code-review minor-3: budget arm carriers must also be present.
        "cap",
        "budget_ok",
    }
    assert expected <= keys


# ---------------------------------------------------------------------------
# Task 15a — budget arm wiring in RunState / intake_node / _route_branch
# ---------------------------------------------------------------------------


def test_intake_node_seeds_budget_fields(monkeypatch):
    """intake_node must return cap, budget_ok, and budget_max in its delta."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    result = intake_node({})
    assert "cap" in result, "intake_node must seed 'cap'"
    assert "budget_ok" in result, "intake_node must seed 'budget_ok'"
    assert "budget_max" in result, "intake_node must seed 'budget_max'"
    assert result["budget_ok"] is True
    assert isinstance(result["cap"], int)
    assert isinstance(result["budget_max"], int)


def test_route_branch_budget_exhausted_degrades_to_write():
    """When budget is exhausted (budget_calls >= budget_max), reject → write."""
    state: RunState = {
        "verdict": "reject",
        "revision_round": 0,
        "cap": 2,
        "budget_calls": 50,
        "budget_max": 40,
        "budget_ok": False,  # stale; route_node should recompute if needed
    }
    assert _route_branch(state) == "write"


def test_route_branch_budget_ok_and_within_cap_revises():
    """When budget is fine and round < cap, reject → revise."""
    state: RunState = {
        "verdict": "reject",
        "revision_round": 0,
        "cap": 2,
        "budget_calls": 5,
        "budget_max": 40,
        "budget_ok": True,
    }
    assert _route_branch(state) == "revise"


def test_run_state_has_budget_max_field():
    """RunState TypedDict must include budget_max."""
    assert "budget_max" in RunState.__annotations__


# ---------------------------------------------------------------------------
# Code-review IMPORTANT 2 — ValueError from Settings.load() must propagate
# ---------------------------------------------------------------------------


def test_intake_node_propagates_rate_limit_value_error(monkeypatch) -> None:
    """intake_node must NOT swallow a ValueError from Settings.load().

    Settings.load() raises ValueError when rate limiting is disabled (the
    tracker silently no-ops otherwise).  This is a fail-fast invariant; a bare
    ``except Exception`` would hide it and leave the graph running without the
    guard.
    """
    import pytest

    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "false")
    with pytest.raises(ValueError, match="rate_limiting"):
        intake_node({})


def test_intake_node_uses_env_cap_and_budget(monkeypatch) -> None:
    """intake_node must read cap and budget_max from environment when valid."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_REVISE_CAP", "5")
    monkeypatch.setenv("MINGJING_BUDGET_CALLS", "100")
    result = intake_node({})
    assert result["cap"] == 5
    assert result["budget_max"] == 100


def test_intake_node_defaults_when_env_absent(monkeypatch) -> None:
    """intake_node returns config-driven defaults when optional env vars absent."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.delenv("MINGJING_REVISE_CAP", raising=False)
    monkeypatch.delenv("MINGJING_BUDGET_CALLS", raising=False)
    result = intake_node({})
    # Defaults mirror config.py: revise_round_cap=2, budget_calls_max=40.
    assert result["cap"] == 2
    assert result["budget_max"] == 40
