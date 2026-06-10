"""Pure QA router — the loop's termination authority (plan Task 10, PURE test #1).

``route`` decides where the graph goes after a QA verdict. It is a pure function:
given the verdict, the current revision round, the round cap, a budget flag, and
an optional assignee, it returns exactly one next-node label.

The critical guarantee is *termination*: a ``reject`` may only loop while we are
strictly under the round cap AND still within budget. The moment ``round >= cap``
or the budget is exhausted, a reject degrades to ``"write_partial"`` (write the
honest partial report) rather than looping forever.
"""


def route(
    *,
    verdict: str,
    round: int,
    cap: int,
    budget_ok: bool,
    assignee: str | None = None,
) -> str:
    """Return the next graph node label for a QA verdict.

    Args:
        verdict: ``"pass"`` or ``"reject"``.
        round: The current (just-completed) revision round.
        cap: The maximum allowed revision rounds.
        budget_ok: ``False`` when the LLM/fetch call budget is exhausted.
        assignee: For a redo, who handles it — ``"collector"`` -> ``"collect"``,
            ``"analyst"`` -> ``"analyze"``. Defaults to ``"collect"``.

    Returns:
        One of ``"write"``, ``"collect"``, ``"analyze"``, ``"write_partial"``.
    """
    if verdict == "pass":
        return "write"

    # verdict == "reject": termination guard takes precedence over re-looping.
    # Hitting the round cap or running out of budget ends the loop honestly.
    if round >= cap or not budget_ok:
        return "write_partial"

    # Still within cap and budget: dispatch the redo to the right agent.
    if assignee == "analyst":
        return "analyze"
    return "collect"
