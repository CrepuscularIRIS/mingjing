"""Unit tests for the Admiralty two-axis grade (SECONDARY metadata, bands only).

These tests run OFFLINE — no network or LLM calls. They assert the pure
reliability/credibility mapping and that the grade attached to evidence items in
``build_claim`` never disturbs the PRIMARY ``evidence_strength``.
"""

import pytest

from mingjing.admiralty import credibility_number, grade, reliability_letter
from mingjing.claim_builder import build_claim
from mingjing.db import Database


def test_reliability_by_source_type():
    assert reliability_letter("official") == "B"
    assert reliability_letter("review") == "D"
    assert reliability_letter("unknown_brand_new") == "F"


def test_credibility_by_corroboration():
    assert credibility_number(independent_corroborators=2, contradictors=0) == 1
    assert credibility_number(independent_corroborators=1, contradictors=0) == 2
    assert credibility_number(independent_corroborators=0, contradictors=0) == 3
    assert credibility_number(independent_corroborators=0, contradictors=2) == 5


def test_grade_is_band_not_decimal():
    g = grade("official", independent_corroborators=2, contradictors=0)
    assert g == "B1"
    assert "." not in g  # never a decimal


@pytest.fixture()
def db(tmp_path):
    d = Database(str(tmp_path / "admiralty_claim.db"))
    d.init_schema()
    return d


def test_admiralty_attached_without_touching_evidence_strength(db):
    """The SECONDARY Admiralty grade must not disturb the PRIMARY evidence_strength.

    Every evidence item gains a band-only ``admiralty`` tag (e.g. ``"B2"``, no
    decimal point), while ``evidence_strength`` stays one of strong/moderate/weak.
    """
    task = {"field": "pricing_model", "competitor": "Acme"}
    src_rows = [
        {
            "id": "src-001",
            "url": "https://acme.example.com/pricing",
            "raw_text": "Acme pricing: free tier available and pro tier at $10/month.",
            "source_type": "official",
        }
    ]
    payload = {
        "claim_type": "fact",
        "statement": "Acme has a free tier.",
        "value": {"tiers": ["free", "pro"]},
        "evidence_ref": ["src-001"],
        "stances": {"src-001": "supports"},
    }
    result = build_claim(db, "run-1", task, src_rows, payload)

    assert result["evidence_strength"] in {"strong", "moderate", "weak"}
    assert result["evidence"], "expected at least one evidence item"
    for ev in result["evidence"]:
        band = ev["admiralty"]
        assert isinstance(band, str) and band
        assert "." not in band  # band only, never a decimal
        # Existing keys preserved.
        for key in ("source_id", "snippet", "relevance", "stance", "locator"):
            assert key in ev
