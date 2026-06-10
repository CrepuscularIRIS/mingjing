"""Writer projection invariant (plan Task 14, PURE test #5).

The Writer is a pure deterministic projection over QA-passed claim rows. The
load-bearing invariant: every rendered ``referenced_id`` must exist in the
passed-claims set. Any id that is referenced but NOT in the passed set is
dropped — the report can never cite an unbacked claim.

These tests are fully offline (no LLM in the claim->text path) and also confirm
the four agent modules import cleanly.
"""

from mingjing.agents.writer import render_report


def test_no_unbacked_claim_renders():
    passed = [{"id": "C1", "statement": "x", "schema_field": "pricing_model"}]
    report = render_report(passed_claims=passed, all_referenced_ids=["C1", "C2"])
    assert "C2" not in report.referenced_ids  # C2 not in passed set -> dropped
    assert report.referenced_ids == ["C1"]


def test_empty_passed_drops_everything():
    report = render_report(passed_claims=[], all_referenced_ids=["C1", "C2"])
    assert report.referenced_ids == []


def test_deterministic_and_order_follows_passed_set():
    passed = [
        {"id": "C3", "statement": "c", "schema_field": "swot"},
        {"id": "C1", "statement": "a", "schema_field": "pricing_model"},
    ]
    referenced = ["C1", "C3", "C9"]
    r1 = render_report(passed_claims=passed, all_referenced_ids=referenced)
    r2 = render_report(passed_claims=passed, all_referenced_ids=referenced)
    # Pure + deterministic: identical inputs -> identical projection.
    assert r1.referenced_ids == r2.referenced_ids
    assert r1.body == r2.body
    # Only passed ids survive; C9 (referenced, not passed) is dropped.
    assert set(r1.referenced_ids) == {"C1", "C3"}
    # The rendered body mentions each surviving claim's statement.
    assert "a" in r1.body and "c" in r1.body


def test_statement_text_is_templated_not_generated():
    passed = [{"id": "C1", "statement": "Pricing starts at $10/mo.", "schema_field": "pricing_model"}]
    report = render_report(passed_claims=passed, all_referenced_ids=["C1"])
    # The exact statement string is templated verbatim into the body (no LLM).
    assert "Pricing starts at $10/mo." in report.body


def test_agents_import_cleanly():
    # The three orchestration agents must be importable offline (no network/key).
    import mingjing.agents.analyst  # noqa: F401
    import mingjing.agents.collector  # noqa: F401
    import mingjing.agents.qa  # noqa: F401
    import mingjing.agents.writer  # noqa: F401
