"""Advisory source-type third axis on the report projection (维度3).

The per-claim ``source_types`` tally is READ-SIDE only: it must enrich the report
without changing the strength tally, evidence_strength, or which claims appear.
"""

from __future__ import annotations

import json

from mingjing.api_helpers import _build_report_sections, _source_type_breakdown


def test_breakdown_counts_by_type_with_web_default() -> None:
    sources = {
        "s1": {"source_type": "official"},
        "s2": {"source_type": "official"},
        "s3": {"source_type": "news"},
        # s4 missing from the map -> defaults to "web"
    }
    out = _source_type_breakdown(["s1", "s2", "s3", "s4"], sources)
    assert out == {"official": 2, "news": 1, "web": 1}


def test_breakdown_empty() -> None:
    assert _source_type_breakdown([], {}) == {}


def _claim(cid: str, field: str, strength: str, ev_ids: list[str]) -> dict:
    return {
        "id": cid,
        "competitor": "Acme",
        "schema_field": field,
        "statement": "s",
        "evidence_strength": strength,
        "status": "pass",
        "value_json": "{}",
        "evidence_json": json.dumps([{"source_id": sid, "snippet": "x", "relevance": "supports"} for sid in ev_ids]),
    }


def test_projection_carries_source_types_without_changing_tally() -> None:
    claims = [
        _claim("c1", "pricing_model", "strong", ["s1", "s2"]),
        _claim("c2", "user_sentiment", "weak", ["s3"]),
    ]
    sources = {
        "s1": {"source_type": "official"},
        "s2": {"source_type": "review"},
        "s3": {"source_type": "web"},
    }
    out = _build_report_sections(claims, sources)
    # Tally + strengths are unchanged by the new axis.
    assert out["strength_tally"] == {"strong": 1, "moderate": 0, "weak": 1}
    by_id = {c["id"]: c for s in out["sections"] for c in s["claims"]}
    assert by_id["c1"]["evidence_strength"] == "strong"
    assert by_id["c1"]["source_types"] == {"official": 1, "review": 1}
    assert by_id["c2"]["source_types"] == {"web": 1}


def test_non_pass_claim_still_excluded_with_axis() -> None:
    claims = [{**_claim("c1", "pricing_model", "weak", ["s1"]), "status": "draft"}]
    out = _build_report_sections(claims, {"s1": {"source_type": "official"}})
    assert out["sections"] == []  # admission unchanged
    assert out["strength_tally"] == {"strong": 0, "moderate": 0, "weak": 0}
