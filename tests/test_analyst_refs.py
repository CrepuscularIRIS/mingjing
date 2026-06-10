"""Unit tests for the Analyst's evidence-ref validation guard (M4).

``filter_evidence_refs`` is a pure helper: it drops any ``evidence_ref`` whose
source_id was not actually supplied to the model, so a hallucinated or empty
citation never flows downstream into claims.
"""

from mingjing.agents.analyst import filter_evidence_refs


def test_drops_unknown_source_ids() -> None:
    payload = {
        "statement": "Pro costs $10.",
        "claim_type": "fact",
        "value": {"price": 10},
        "evidence_ref": ["S1", "S99", "S2"],
    }
    cleaned = filter_evidence_refs(payload, {"S1", "S2"})
    assert cleaned["evidence_ref"] == ["S1", "S2"]


def test_drops_empty_refs() -> None:
    payload = {"evidence_ref": ["S1", "", None]}
    cleaned = filter_evidence_refs(payload, {"S1"})
    assert cleaned["evidence_ref"] == ["S1"]


def test_preserves_order_and_other_fields() -> None:
    payload = {
        "statement": "s",
        "value": {"k": "v"},
        "evidence_ref": ["S2", "S1"],
    }
    cleaned = filter_evidence_refs(payload, {"S1", "S2"})
    assert cleaned["evidence_ref"] == ["S2", "S1"]
    assert cleaned["statement"] == "s"
    assert cleaned["value"] == {"k": "v"}


def test_does_not_mutate_input() -> None:
    payload = {"evidence_ref": ["S1", "BAD"]}
    filter_evidence_refs(payload, {"S1"})
    assert payload["evidence_ref"] == ["S1", "BAD"]


def test_missing_evidence_ref_is_untouched() -> None:
    payload = {"statement": "s"}
    cleaned = filter_evidence_refs(payload, {"S1"})
    assert "evidence_ref" not in cleaned or cleaned.get("evidence_ref") is None
