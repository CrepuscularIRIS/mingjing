"""Tests for summarize_contradiction — the pure helper that turns a claim's
evidence + sources into ContradictionCard data (source_a, source_b, from, to)
or None when there is no source-vs-source conflict.

A conflict = the claim's evidence carries a ``supports`` stance and a ``refutes``
stance on DISTINCT registrable domains. ``from``/``to`` are the evidence-strength
tiers WITHOUT vs WITH the contradiction cap, so the UI can show the honest
confidence demotion."""

import json

from mingjing import api
from mingjing.contradiction import summarize_contradiction


def _ev(source_id: str, stance: str, relevance: str = "supports") -> dict:
    return {"source_id": source_id, "snippet": "x", "relevance": relevance, "stance": stance}


def test_no_conflict_returns_none():
    """All-supporting evidence (no refutes) → no contradiction."""
    evidence = [_ev("s1", "supports"), _ev("s2", "supports")]
    sources = {
        "s1": {"url": "https://a.example.com/p", "source_type": "official"},
        "s2": {"url": "https://b.example.com/p", "source_type": "official"},
    }
    assert summarize_contradiction(evidence, sources) is None


def test_supports_and_refutes_same_domain_is_not_a_conflict():
    """A single site supporting and refuting itself is NOT a cross-source conflict."""
    evidence = [_ev("s1", "supports"), _ev("s2", "refutes")]
    sources = {
        "s1": {"url": "https://a.example.com/p1", "source_type": "official"},
        "s2": {"url": "https://a.example.com/p2", "source_type": "official"},  # same domain
    }
    assert summarize_contradiction(evidence, sources) is None


def test_cross_domain_conflict_returns_card_data_with_demotion():
    """supports on domain A + refutes on domain B (distinct registrable domains)
    → card data with the two domains and a confidence demotion (stronger → 'weak')."""
    evidence = [_ev("s1", "supports"), _ev("s2", "refutes")]
    sources = {
        "s1": {"url": "https://acme.com/p", "source_type": "official"},
        "s2": {"url": "https://trustpilot.com/p", "source_type": "review"},
    }
    card = summarize_contradiction(evidence, sources)
    assert card is not None
    labels = {card["source_a"]["label"], card["source_b"]["label"]}
    assert labels == {"acme.com", "trustpilot.com"}
    # The contradiction DEMOTES confidence: 'to' tier is strictly weaker than 'from'.
    rank = {"weak": 0, "moderate": 1, "strong": 2}
    assert rank[card["to"]] < rank[card["from"]]


def test_card_carries_url_and_optional_grade():
    """Each conflict source carries its url; grade is included when the evidence
    item has an admiralty grade."""
    evidence = [
        {"source_id": "s1", "stance": "supports", "relevance": "supports", "admiralty": "B2"},
        {"source_id": "s2", "stance": "refutes", "relevance": "supports"},
    ]
    sources = {
        "s1": {"url": "https://acme.com/p", "source_type": "official"},
        "s2": {"url": "https://trustpilot.com/p", "source_type": "review"},
    }
    card = summarize_contradiction(evidence, sources)
    assert card is not None
    by_label = {card["source_a"]["label"]: card["source_a"], card["source_b"]["label"]: card["source_b"]}
    assert by_label["acme.com"]["url"] == "https://acme.com/p"
    assert by_label["acme.com"].get("grade") == "B2"


def _passed_claim(evidence: list[dict], *, cid: str = "C1") -> dict:
    return {
        "status": "pass", "id": cid, "schema_field": "pricing_model",
        "competitor": "X", "statement": "Pro tier.", "evidence_strength": "weak",
        "value_json": "{}", "based_on_json": "[]", "version": 1,
        "evidence_json": json.dumps(evidence),
    }


def test_report_attaches_contradiction_for_conflicting_claim():
    """_build_report_sections attaches a `contradiction` object to a claim whose
    evidence has a cross-domain supports/refutes split."""
    claims = [_passed_claim([
        {"source_id": "s1", "stance": "supports", "relevance": "supports"},
        {"source_id": "s2", "stance": "refutes", "relevance": "supports"},
    ])]
    sources = {
        "s1": {"url": "https://acme.com/p", "source_type": "official"},
        "s2": {"url": "https://trustpilot.com/p", "source_type": "review"},
    }
    report = api._build_report_sections(claims, sources)
    claim = report["sections"][0]["claims"][0]
    assert "contradiction" in claim
    labels = {claim["contradiction"]["source_a"]["label"], claim["contradiction"]["source_b"]["label"]}
    assert labels == {"acme.com", "trustpilot.com"}


def test_report_omits_contradiction_when_clean():
    """A claim with only supporting evidence has no `contradiction` key."""
    claims = [_passed_claim(
        [{"source_id": "s1", "stance": "supports", "relevance": "supports"}], cid="C2"
    )]
    sources = {"s1": {"url": "https://acme.com/p", "source_type": "official"}}
    report = api._build_report_sections(claims, sources)
    assert "contradiction" not in report["sections"][0]["claims"][0]
