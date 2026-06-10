"""Every survey question (except the qualification gate) maps to a real
default-domain schema field, and design_survey echoes the field."""
from mingjing.schema_registry import load_domain
from mingjing.survey import design_survey


def test_every_question_has_a_valid_field():
    default_fields = set(load_domain("default"))
    design = design_survey("Notion", "compare note apps")
    for q in design["questions"]:
        assert "field" in q, f"{q['id']} missing field"
        if q["field"] is not None:  # q1 qualification gate has no field
            assert q["field"] in default_fields, f"{q['id']} -> {q['field']!r} not a default field"


def test_qualification_question_has_no_field():
    design = design_survey("Notion", "g")
    q1 = next(q for q in design["questions"] if q["id"] == "q1")
    assert q1["field"] is None
