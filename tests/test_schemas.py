import pytest

from mingjing.schemas import FIELD_SCHEMAS, Claim, EvidenceChunk, IssueCode


def test_field_schemas_present():
    assert set(FIELD_SCHEMAS) == {
        "pricing_model",
        "user_sentiment",
        "feature_tree",
        "user_persona",
        "swot",
    }


def test_issue_codes_present():
    assert {c.value for c in IssueCode} == {
        "SCHEMA_GAP",
        "WEAK_EVIDENCE",
        "CONTRADICTION",
        "HALLUCINATED_SNIPPET",
        "LOW_COVERAGE",
        "VALUE_UNSUPPORTED",
    }


def test_claim_requires_evidence_for_fact():
    with pytest.raises(ValueError):
        Claim(
            id="C1",
            run_id="R1",
            competitor="A",
            schema_field="pricing_model",
            claim_type="fact",
            statement="x",
            evidence=[],
            evidence_strength="weak",
            status="draft",
            version=1,
            produced_by="analyst",
        )  # fact w/ no evidence


def test_fact_claim_with_evidence_ok():
    chunk = EvidenceChunk(id="E1", run_id="R1", text="pricing is $10", locator="p:1")
    claim = Claim(
        id="C1",
        run_id="R1",
        competitor="A",
        schema_field="pricing_model",
        claim_type="fact",
        statement="x",
        evidence=[chunk],
        evidence_strength="moderate",
        status="draft",
        version=1,
        produced_by="analyst",
    )
    assert claim.evidence[0].id == "E1"


def test_inference_claim_allows_empty_evidence():
    claim = Claim(
        id="C2",
        run_id="R1",
        competitor="A",
        schema_field="swot",
        claim_type="inference",
        statement="they may expand",
        evidence=[],
        evidence_strength="weak",
        status="draft",
        version=1,
        produced_by="analyst",
    )
    assert claim.evidence == []
