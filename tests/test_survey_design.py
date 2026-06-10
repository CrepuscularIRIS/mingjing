"""Tests for survey.design_survey and survey.scrub_open_text (Task D).

Coverage:
- Questionnaire structure, dimensions, types, options
- pii_scrub flags on open questions
- n parameter truncation
- Compliance canary: all four PII types stripped in one pass
- Clean text returned unchanged (count == 0)
- No false positives on non-6-digit numbers ("2024")
"""

from __future__ import annotations

from mingjing.survey import design_survey, scrub_open_text

# ---------------------------------------------------------------------------
# design_survey tests
# ---------------------------------------------------------------------------


class TestDesignSurvey:
    def test_returns_10_questions_by_default(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        assert len(result["questions"]) == 10

    def test_question_ids_are_q1_to_q10(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        ids = [q["id"] for q in result["questions"]]
        assert ids == [f"q{i}" for i in range(1, 11)]

    def test_dimension_set(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        expected_dimensions = {
            "qualification",
            "overall_satisfaction",
            "feature_satisfaction",
            "nps",
            "nps_rationale",
            "feature_gaps",
            "switching_intent",
            "willingness_to_pay",
            "switching_barrier",
            "open_feedback",
        }
        actual_dimensions = {q["dimension"] for q in result["questions"]}
        assert actual_dimensions == expected_dimensions

    def test_q4_is_nps_with_correct_scale(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        q4 = next(q for q in result["questions"] if q["id"] == "q4")
        assert q4["type"] == "nps"
        assert q4["scale"]["min"] == 0
        assert q4["scale"]["max"] == 10

    def test_q5_and_q10_have_pii_scrub_true(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        by_id = {q["id"]: q for q in result["questions"]}
        assert by_id["q5"].get("pii_scrub") is True
        assert by_id["q10"].get("pii_scrub") is True

    def test_competitor_name_appears_in_question_text(self) -> None:
        result = design_survey("Notion", "compare AI agents")
        texts = " ".join(q["text"] for q in result["questions"])
        assert "Notion" in texts

    def test_n_5_returns_5_questions(self) -> None:
        result = design_survey("Notion", "compare AI agents", n=5)
        assert len(result["questions"]) == 5
        ids = [q["id"] for q in result["questions"]]
        assert ids == ["q1", "q2", "q3", "q4", "q5"]

    def test_metadata_fields_echoed(self) -> None:
        result = design_survey("Feishu", "measure adoption", survey_id="SV-99")
        assert result["survey_id"] == "SV-99"
        assert result["competitor"] == "Feishu"
        assert result["goal"] == "measure adoption"

    def test_response_schema_keys_match_questions(self) -> None:
        result = design_survey("Notion", "compare AI agents", n=5)
        question_ids = {q["id"] for q in result["questions"]}
        assert set(result["response_schema"].keys()) == question_ids

    def test_goal_interpolated_in_text(self) -> None:
        result = design_survey("Lark", "measure AI adoption")
        texts = " ".join(q["text"] for q in result["questions"])
        assert "measure AI adoption" in texts


# ---------------------------------------------------------------------------
# scrub_open_text tests
# ---------------------------------------------------------------------------


class TestScrubOpenText:
    # ---- Compliance canary -----------------------------------------------

    def test_compliance_canary_strips_all_pii_types(self) -> None:
        """Canary containing name (trigger), email, CN mobile, and CN ID."""
        cn_id = "11010119900307123X"  # 18-char CN national ID (fictional)
        canary = (
            f"我叫张伟，联系我：test@example.com，"
            f"手机 13812345678，身份证号 {cn_id}，"
            f"希望产品能改进。"
        )
        scrubbed, count = scrub_open_text(canary)

        # (1) No email substring remains
        assert "test@example.com" not in scrubbed, "email not scrubbed"

        # (2) No phone digit-run remains
        assert "13812345678" not in scrubbed, "mobile not scrubbed"

        # (3) Name token is gone
        assert "张伟" not in scrubbed, "name not scrubbed"

        # (4) 18-digit CN ID is gone
        assert cn_id not in scrubbed, "national ID not scrubbed"

        # (5) At least 4 PII tokens were redacted
        assert count >= 4, f"expected >= 4 redactions, got {count}"

        # (6) Placeholder tokens are present
        assert "[EMAIL]" in scrubbed
        assert "[PHONE]" in scrubbed
        assert "[NAME]" in scrubbed
        assert "[ID]" in scrubbed

    # ---- Clean text -------------------------------------------------------

    def test_clean_text_unchanged_count_zero(self) -> None:
        """A sentence with no PII should come back identical."""
        clean = "产品功能很强大，希望未来增加更多集成选项。"
        scrubbed, count = scrub_open_text(clean)
        assert scrubbed == clean
        assert count == 0

    # ---- No false positives -----------------------------------------------

    def test_no_false_zip_on_4digit_year(self) -> None:
        """'2024' must NOT be redacted as a ZIP (only 6-digit codes are ZIPs)."""
        text = "the 2024 plan looks solid, Q3 revenue up 15%."
        scrubbed, count = scrub_open_text(text)
        assert "2024" in scrubbed, "'2024' was incorrectly redacted"
        assert "[ZIP]" not in scrubbed
        assert count == 0

    # ---- Individual pattern checks ----------------------------------------

    def test_email_redacted(self) -> None:
        text = "reach me at alice@corp.io for details"
        scrubbed, count = scrub_open_text(text)
        assert "alice@corp.io" not in scrubbed
        assert "[EMAIL]" in scrubbed
        assert count >= 1

    def test_cn_mobile_redacted(self) -> None:
        text = "call me at 13912345678 anytime"
        scrubbed, count = scrub_open_text(text)
        assert "13912345678" not in scrubbed
        assert "[PHONE]" in scrubbed
        assert count >= 1

    def test_cn_landline_redacted(self) -> None:
        text = "office number is 010-87654321"
        scrubbed, count = scrub_open_text(text)
        assert "010-87654321" not in scrubbed
        assert "[PHONE]" in scrubbed
        assert count >= 1

    def test_cn_national_id_redacted(self) -> None:
        text = "my ID is 11010119900307123X please verify"
        scrubbed, count = scrub_open_text(text)
        assert "11010119900307123X" not in scrubbed
        assert "[ID]" in scrubbed
        assert count >= 1

    def test_name_trigger_english_my_name_is(self) -> None:
        text = "my name is JohnDoe and I think the product is fine"
        scrubbed, count = scrub_open_text(text)
        assert "JohnDoe" not in scrubbed
        assert "[NAME]" in scrubbed
        assert "my name is" in scrubbed
        assert count >= 1

    def test_no_over_redaction_on_i_am_adjective(self) -> None:
        # The broad "I am"/"I'm" triggers were intentionally dropped: in survey
        # feedback they precede an adjective far more often than a name, so they
        # must NOT redact the following word.
        text = "I am happy with the product and I'm satisfied overall"
        scrubbed, count = scrub_open_text(text)
        assert scrubbed == text
        assert count == 0

    def test_none_and_empty_do_not_crash(self) -> None:
        assert scrub_open_text(None) == ("", 0)
        assert scrub_open_text("") == ("", 0)

    def test_n_bounds_are_clamped(self) -> None:
        # n is clamped to [1, 10]; out-of-range values must not crash.
        assert len(design_survey("X", "g", n=0)["questions"]) == 1
        assert len(design_survey("X", "g", n=20)["questions"]) == 10

    def test_name_trigger_preserves_rest_of_sentence(self) -> None:
        text = "我叫李明，产品反馈：界面简洁"
        scrubbed, _ = scrub_open_text(text)
        assert "李明" not in scrubbed
        # The trigger phrase itself must still be present
        assert "我叫" in scrubbed
        assert "产品反馈" in scrubbed

    def test_zip_code_redacted(self) -> None:
        text = "send mail to postal code 100001 in Beijing"
        scrubbed, count = scrub_open_text(text)
        assert "100001" not in scrubbed
        assert "[ZIP]" in scrubbed
        assert count >= 1

    def test_id_not_partially_eaten_by_zip(self) -> None:
        """An 18-digit CN ID must be replaced by [ID], not have first 6 as [ZIP]."""
        cn_id = "11010119900307123X"
        text = f"my ID number is {cn_id} ok"
        scrubbed, _ = scrub_open_text(text)
        assert "[ID]" in scrubbed
        # The ID should be gone as a whole; no [ZIP] should appear
        assert cn_id not in scrubbed
        # There should be no leftover digits from the ID
        assert "110101" not in scrubbed  # first 6 digits of the ID
