"""Tests for the QA agent assignee routing."""

from mingjing.agents.qa import _ASSIGNEE_BY_CODE
from mingjing.schemas import IssueCode


def test_evidence_gap_codes_route_to_collector() -> None:
    """Evidence-gap codes must re-collect, not re-run the analyst.

    SCHEMA_GAP (missing required sub-field) and VALUE_UNSUPPORTED (claimed value
    not present in cited sources) both mean the *current* evidence is
    insufficient. Re-running the analyst on the same sources can't fix that, so
    these route to the collector (which grows the source cap and fetches more).
    HALLUCINATED_SNIPPET is a genuine analyst fabrication, so it stays "analyst".
    """
    assert _ASSIGNEE_BY_CODE[IssueCode.SCHEMA_GAP] == "collector"
    assert _ASSIGNEE_BY_CODE[IssueCode.VALUE_UNSUPPORTED] == "collector"
    assert _ASSIGNEE_BY_CODE[IssueCode.HALLUCINATED_SNIPPET] == "analyst"


def test_triage_is_pure_static_mapping_no_llm() -> None:
    """Closure ①: redo triage is a pure static dict keyed by deterministic
    IssueCode — there is NO LLM in the triage path, so the subjectivity evicted
    from the verdict cannot return via routing. EVERY issue code must map to a
    fixed collector/analyst assignee (no code falls through to a runtime guess)."""
    # Every deterministic issue code the verifier can emit is statically routed.
    for code in IssueCode:
        assert code in _ASSIGNEE_BY_CODE, f"{code} has no static assignee"
    # The only legal destinations are the two deterministic redo agents.
    assert all(v in ("collector", "analyst") for v in _ASSIGNEE_BY_CODE.values())
