"""Tests for FIELD_QUERY_TEMPLATES / build_query and live_plan_node query shape."""

from mingjing.graph_nodes import (
    build_query,
    live_plan_node,
)

# ---------------------------------------------------------------------------
# build_query — known (templated) fields
# ---------------------------------------------------------------------------


def test_build_query_known_fields():
    """Each templated field produces its natural-language query for 'Notion'."""
    expected = {
        "pricing_model": "Notion pricing plans cost per month",
        "user_sentiment": "Notion reviews pros and cons",
        "feature_tree": "Notion features list overview",
        "user_persona": "Notion who is it for target users",
        "swot": "Notion strengths and weaknesses review",
    }
    for field, want in expected.items():
        got = build_query("Notion", field)
        assert got == want, f"field={field!r}: got {got!r}, want {want!r}"
        # raw field token must NOT appear in the templated result
        assert field not in got, (
            f"raw field name {field!r} leaked into query {got!r}"
        )


# ---------------------------------------------------------------------------
# build_query — unknown / fallback field
# ---------------------------------------------------------------------------


def test_build_query_unknown_field_falls_back():
    """An unrecognised field falls back to 'competitor field'."""
    assert build_query("Acme", "exotic_field") == "Acme exotic_field"


# ---------------------------------------------------------------------------
# build_query — empty competitor
# ---------------------------------------------------------------------------


def test_build_query_empty_competitor():
    """Empty competitor string: templated result must not crash and must be stripped."""
    result = build_query("", "pricing_model")
    assert isinstance(result, str)
    assert result == result.strip(), "result must have no leading/trailing whitespace"
    # Should contain the rest of the template even when competitor is empty
    assert "pricing plans cost per month" in result


# ---------------------------------------------------------------------------
# live_plan_node uses templates
# ---------------------------------------------------------------------------


def test_live_plan_node_uses_templates():
    """live_plan_node tasks carry template-derived queries."""
    state = {
        "intake": {
            "competitors": ["Notion"],
            "fields": ["user_sentiment", "pricing_model"],
        }
    }
    result = live_plan_node(state)

    assert result["phase"] == "plan"
    tasks = result["tasks"]
    assert len(tasks) == 2

    task_map = {t["field"]: t for t in tasks}

    assert task_map["user_sentiment"]["query"] == build_query("Notion", "user_sentiment")
    assert task_map["pricing_model"]["query"] == build_query("Notion", "pricing_model")

    # Sanity: competitor is stored on task
    for task in tasks:
        assert task["competitor"] == "Notion"
