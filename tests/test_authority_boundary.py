"""Authority-boundary invariants: deterministic gate = sole veto;
writer projection drops any sentence without a passed claim_id."""
from mingjing.qa.route import route
from mingjing.synthesis import project_synthesis


def test_pass_verdict_always_writes_regardless_of_round_or_budget() -> None:
    # A deterministic 'pass' can never be overridden into a loop.
    for rnd in (0, 1, 5):
        for budget_ok in (True, False):
            assert route(verdict="pass", round=rnd, cap=2, budget_ok=budget_ok) == "write"


def test_reject_at_cap_degrades_to_partial_never_loops_forever() -> None:
    assert route(verdict="reject", round=2, cap=2, budget_ok=True) == "write_partial"
    assert route(verdict="reject", round=0, cap=2, budget_ok=False) == "write_partial"


def test_projection_drops_sentence_without_passed_claim_id() -> None:
    # The real project_synthesis consumes a flat payload keyed by report section
    # (bluf / swot / comparison / recommendations / intelligence_gap /
    # key_assumptions), where each factual sentence is {text, claim_ids:[...]}.
    # ``comparison`` is a NON-scaffold list section, so the drop rule applies
    # cleanly: keep iff claim_ids is non-empty AND a subset of passed ids.
    payload = {
        "comparison": [
            {"text": "Backed sentence.", "claim_ids": ["C1"]},
            {"text": "Unbacked sentence.", "claim_ids": ["C-MISSING"]},
            {"text": "No-cite sentence.", "claim_ids": []},
        ]
    }
    out = project_synthesis(payload=payload, passed_claim_ids={"C1"})
    texts = [s["text"] for s in out["comparison"]]
    assert "Backed sentence." in texts
    assert "Unbacked sentence." not in texts  # cites a non-passed id -> dropped
    assert "No-cite sentence." not in texts    # no claim_id -> dropped


def test_route_is_independent_of_advisory_signals() -> None:
    """Closure ②: groundedness / Prover-Refuter confidence / contradiction are
    ADVISORY. The route decision is a pure function of (verdict, round, cap,
    budget_ok, assignee). route() does not even accept an advisory parameter — so
    by construction an advisory signal cannot reach a gate boolean. If a later
    change ever adds a groundedness/confidence param to route(), this FAILS."""
    import inspect

    params = set(inspect.signature(route).parameters)
    assert params == {"verdict", "round", "cap", "budget_ok", "assignee"}
    for verdict in ("pass", "reject"):
        d1 = route(verdict=verdict, round=0, cap=2, budget_ok=True)
        d2 = route(verdict=verdict, round=0, cap=2, budget_ok=True)
        assert d1 == d2
