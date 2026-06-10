"""QA agent — thin orchestration over the deterministic verifier + scorer.

Wraps :func:`mingjing.qa.rules.qa_check` (the 6 rules, which themselves call
:func:`mingjing.scoring.strength`) into a single ``review`` call that returns a
verdict, the found issues, and concrete :class:`~mingjing.schemas.RevisionTask`
dispatch hints. The verdict is computed purely from claim/evidence metadata —
never from a freeform LLM judgement — so an injected string cannot flip it.
"""

import uuid
from typing import Any

from ..qa import rules
from ..schemas import IssueCode

# Which agent each issue code routes its redo to.
#
# Evidence-gap codes (SCHEMA_GAP, VALUE_UNSUPPORTED) route to the collector, not
# the analyst: a missing required sub-field or a claimed value absent from the
# cited sources means the *current* evidence is insufficient. Re-running the
# analyst on the same sources can't fix that — the collect node grows
# ``source_cap = 1 + revision_round`` and fetches MORE sources, after which the
# graph re-runs analyze->qa on the richer evidence. HALLUCINATED_SNIPPET stays
# on the analyst because it's a genuine fabrication (re-collecting won't help).
_ASSIGNEE_BY_CODE: dict[IssueCode, str] = {
    IssueCode.SCHEMA_GAP: "collector",
    IssueCode.WEAK_EVIDENCE: "collector",
    IssueCode.CONTRADICTION: "collector",
    IssueCode.HALLUCINATED_SNIPPET: "analyst",
    IssueCode.LOW_COVERAGE: "collector",
    IssueCode.VALUE_UNSUPPORTED: "collector",
}


def review(claimset: dict[str, Any], *, run_id: str = "", round: int = 0) -> dict[str, Any]:
    """Run the verifier over ``claimset`` and produce a QA result.

    Args:
        claimset: The QA input (``claims``/``sources``/``coverage``) per
            :func:`mingjing.qa.rules.qa_check`.
        run_id: Owning run id (stamped onto revision tasks).
        round: Current revision round (stamped onto revision tasks).

    Returns:
        A dict ``{"verdict", "issues", "revision_tasks"}`` where ``verdict`` is
        ``"pass"`` (no issues) or ``"reject"``, and each revision task carries an
        ``assignee`` so the router can dispatch the redo.
    """
    issues = rules.qa_check(claimset)
    verdict = "pass" if not issues else "reject"

    revision_tasks: list[dict[str, Any]] = []
    for issue in issues:
        assignee = _ASSIGNEE_BY_CODE.get(issue.code, "collector")
        revision_tasks.append(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "claim_id": issue.claim_id,
                "assignee": assignee,
                "issue_code": issue.code.value,
                "instruction": issue.detail,
                # Thread Issue.meta through so the contradiction Issue's
                # supports_domains/refutes_domains reach the verdict/trace path
                # (the frontend ContradictionCard renders them).
                "meta": dict(issue.meta),
                "status": "open",
                "round": round,
            }
        )

    return {
        "verdict": verdict,
        "issues": [
            {
                "code": i.code.value,
                "claim_id": i.claim_id,
                "detail": i.detail,
                "meta": dict(i.meta),
            }
            for i in issues
        ],
        "revision_tasks": revision_tasks,
    }
