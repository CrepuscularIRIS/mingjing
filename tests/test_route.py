"""Unit tests for the pure QA router (plan Task 10, PURE test #1).

The round-cap -> ``write_partial`` case is the load-bearing infinite-loop guard;
it is tested explicitly. ``route`` is pure: no I/O, no state mutation.
"""

from mingjing.qa.route import route


def test_pass() -> None:
    assert route(verdict="pass", round=0, cap=2, budget_ok=True) == "write"


def test_pass_ignores_round_and_budget() -> None:
    # A pass always writes the full report regardless of round / budget.
    assert route(verdict="pass", round=5, cap=2, budget_ok=False) == "write"


def test_reject_to_collector() -> None:
    assert (
        route(verdict="reject", round=0, cap=2, budget_ok=True, assignee="collector")
        == "collect"
    )


def test_reject_to_analyst() -> None:
    assert (
        route(verdict="reject", round=0, cap=2, budget_ok=True, assignee="analyst")
        == "analyze"
    )


def test_reject_default_assignee_is_collect() -> None:
    # No assignee -> default to collect (gather more evidence first).
    assert route(verdict="reject", round=0, cap=2, budget_ok=True) == "collect"


def test_round_cap_terminates() -> None:
    # CRITICAL: at the cap, a reject must NOT loop again -> write_partial.
    assert route(verdict="reject", round=2, cap=2, budget_ok=True) == "write_partial"


def test_round_over_cap_terminates() -> None:
    assert route(verdict="reject", round=3, cap=2, budget_ok=True) == "write_partial"


def test_budget_exceeded_terminates() -> None:
    assert route(verdict="reject", round=0, cap=2, budget_ok=False) == "write_partial"


def test_partial_guard_precedes_assignee() -> None:
    # Even with an assignee, hitting the cap forces termination.
    assert (
        route(verdict="reject", round=2, cap=2, budget_ok=True, assignee="analyst")
        == "write_partial"
    )
