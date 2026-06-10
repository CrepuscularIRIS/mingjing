"""active_field_schemas(): defaults to the env FIELD_SCHEMAS; overridable per
context via use_domain so a run can analyze a different domain's fields."""
from mingjing import schemas
from mingjing.schemas import FIELD_SCHEMAS, active_field_schemas, use_domain


def test_defaults_to_global_field_schemas():
    assert active_field_schemas() is FIELD_SCHEMAS  # unset → env default


def test_use_domain_overrides_then_resets():
    assert "autonomy_level" not in active_field_schemas()  # default domain
    with use_domain("ai_agent"):
        assert "autonomy_level" in active_field_schemas()  # ai_agent fields visible
    assert "autonomy_level" not in active_field_schemas()  # reset after the block


def test_qa_reads_active_schema_for_domain_field():
    """QA's schema-gap check must use the ACTIVE domain: an ai_agent field's
    required sub-field is only known inside use_domain('ai_agent')."""
    from mingjing.qa.rules import qa_check

    # Pick a real required sub-field of an ai_agent-only field at runtime.
    from mingjing.schema_registry import load_domain
    from mingjing.schemas import IssueCode
    ai = load_domain("ai_agent")
    # find an ai_agent-only field with a non-empty required list
    field = next(f for f, s in ai.items() if f not in FIELD_SCHEMAS and s.get("required"))
    claim = {"id": "C1", "schema_field": field, "claim_type": "fact",
             "competitor": "X", "value": {}, "evidence": [
                 {"source_id": "s1", "snippet": "x", "relevance": "supports"}]}
    claimset = {"claims": [claim], "sources": {"s1": {"raw_text": "x", "source_type": "official", "url": "https://x.com"}},
                "coverage": {"required_fields": [], "covered_fields": []}}
    # Outside: field unknown to default schema → no SCHEMA_GAP from missing sub-fields.
    assert IssueCode.SCHEMA_GAP not in {i.code for i in qa_check(claimset)}
    # Inside ai_agent: the field IS known and its required sub-fields are missing → SCHEMA_GAP.
    with use_domain("ai_agent"):
        assert IssueCode.SCHEMA_GAP in {i.code for i in qa_check(claimset)}


def test_set_active_domain_overrides_and_resets():
    """set_active_domain is the non-context-manager seam the run executor uses."""
    assert "autonomy_level" not in active_field_schemas()
    try:
        schemas.set_active_domain("ai_agent")
        assert "autonomy_level" in active_field_schemas()
        schemas.set_active_domain(None)  # back to env default
        assert "autonomy_level" not in active_field_schemas()
    finally:
        schemas.set_active_domain(None)


def test_empty_active_schema_is_honored_not_defaulted():
    """An explicitly-set EMPTY active schema must be returned as-is (is-None
    sentinel), NOT silently replaced by the default via truthiness."""
    token = schemas._active_schema.set({})
    try:
        assert active_field_schemas() == {}
    finally:
        schemas._active_schema.reset(token)
