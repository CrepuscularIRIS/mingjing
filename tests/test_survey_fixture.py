from mingjing.survey_fixture import fixture_for


def test_fixture_for_demo_competitor_returns_per_field_text():
    fx = fixture_for("Notion")
    assert fx is not None
    assert "user_sentiment" in fx["survey"]["fields"]
    assert isinstance(fx["survey"]["fields"]["user_sentiment"], str)
    assert fx["survey"]["survey_id"] == "SV-1"
    assert fx["interview"]["interview_id"] == "IV-1"
    assert fx["interview"]["fields"]


def test_fixture_for_match_is_case_insensitive():
    assert fixture_for("notion") is not None
    assert fixture_for("NOTION") is not None


def test_fixture_for_unknown_competitor_is_none():
    assert fixture_for("Acme Unknown Co") is None
