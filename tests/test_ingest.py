"""Offline unit tests for survey/interview ingest (Task 17, Deliverable 1).

All tests use synthetic data and a tmp_path-scoped SQLite DB — no network,
no live LLM. Coverage:

A) anonymize_respondent_meta — pure function unit tests
   - Drops identity-named keys (name, email, phone, mobile, cell, tel,
     firstname, lastname, surname, fullname, case-insensitive)
   - Drops extended identity keys: respondent, speaker, interviewer,
     interviewee, participant, contact_person, contact, user, author
   - Keeps non-identity keys (role, segment, region, company, …)
   - Redacts email-shaped values in surviving keys (strict regex check)
   - Redacts phone-shaped values in surviving keys (strict regex check)
   - Recurses into nested dicts/lists (C1)
   - Redacts integer phone values (C2)
   - Returns a NEW dict (input not mutated, no shared references)
   - Empty input returns empty dict

B) ingest_survey — integration tests against a real tmp_path DB
   - Sources are persisted with source_type="survey"
   - Evidence chunks carry locators of the form survey:<id>/q<n>
   - respondent_meta stored in DB has NO name/email/phone/lastname key or value
   - Returns the correct number of source_ids

C) ingest_interview — integration tests against a real tmp_path DB
   - Sources are persisted with source_type="interview"
   - Evidence chunks carry locators of the form interview:<id>/seg<n>
   - speaker_meta stored in DB has NO name/email/phone key or value
   - Segments with empty text are skipped
   - Returns the correct number of source_ids

D) PII-free invariant — exhaustive check that NO stored meta_json, raw_text,
   or evidence_chunks.text contains any recognizable email/phone PII.
"""

import json
import re

from mingjing.db import Database
from mingjing.ingest import (
    _EMAIL_PATTERN,
    _PHONE_PATTERN,
    anonymize_respondent_meta,
    ingest_interview,
    ingest_survey,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "test.db"))
    db.init_schema()
    return db


def _all_sources(db: Database, run_id: str) -> list[dict]:
    """Fetch all source rows for a run."""
    cur = db._conn.execute(
        "SELECT * FROM sources WHERE run_id = ?", (run_id,)
    )
    return [dict(r) for r in cur.fetchall()]


def _all_chunks(db: Database, run_id: str) -> list[dict]:
    """Fetch all evidence_chunk rows for a run."""
    cur = db._conn.execute(
        "SELECT * FROM evidence_chunks WHERE run_id = ?", (run_id,)
    )
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# A: anonymize_respondent_meta – pure function tests
# ---------------------------------------------------------------------------


class TestAnonymizeRespondentMeta:
    def test_drops_name_key(self) -> None:
        result = anonymize_respondent_meta({"name": "Alice Smith", "role": "PM"})
        assert "name" in {"name": "Alice Smith"}  # sanity: key was there
        assert "name" not in result
        assert result["role"] == "PM"

    def test_drops_email_key(self) -> None:
        result = anonymize_respondent_meta({"email": "alice@example.com", "segment": "B2B"})
        assert "email" not in result
        assert result["segment"] == "B2B"

    def test_drops_phone_key(self) -> None:
        result = anonymize_respondent_meta({"phone": "555-123-4567", "region": "US"})
        assert "phone" not in result
        assert result["region"] == "US"

    def test_drops_mobile_key(self) -> None:
        result = anonymize_respondent_meta({"mobile": "+1 800 555 1234"})
        assert "mobile" not in result

    def test_drops_cell_key(self) -> None:
        result = anonymize_respondent_meta({"cell": "415-555-0100"})
        assert "cell" not in result

    def test_drops_tel_key(self) -> None:
        result = anonymize_respondent_meta({"tel": "+44 20 7946 0958"})
        assert "tel" not in result

    def test_drops_firstname_key(self) -> None:
        result = anonymize_respondent_meta({"firstname": "Bob"})
        assert "firstname" not in result

    def test_drops_lastname_key(self) -> None:
        result = anonymize_respondent_meta({"lastname": "Jones"})
        assert "lastname" not in result

    def test_drops_surname_key(self) -> None:
        result = anonymize_respondent_meta({"surname": "Williams"})
        assert "surname" not in result

    def test_drops_fullname_key(self) -> None:
        result = anonymize_respondent_meta({"fullname": "Carol Danvers"})
        assert "fullname" not in result

    def test_case_insensitive_key_drop(self) -> None:
        result = anonymize_respondent_meta(
            {"Name": "Dave", "EMAIL": "d@x.com", "PhoneNumber": "555-0101"}
        )
        assert "Name" not in result
        assert "EMAIL" not in result
        assert "PhoneNumber" not in result

    def test_keeps_non_identity_keys(self) -> None:
        meta = {
            "role": "Engineer",
            "segment": "Enterprise",
            "region": "APAC",
            "company_size": "50-200",
            "years_exp": 5,
        }
        result = anonymize_respondent_meta(meta)
        assert result == meta

    def test_redacts_email_value_in_surviving_key(self) -> None:
        # 'contact' is now an identity key (dropped), so use a neutral key
        result = anonymize_respondent_meta({"note": "reach me at user@corp.io please"})
        assert "user@corp.io" not in result["note"]
        assert "[REDACTED]" in result["note"]

    def test_redacts_phone_value_in_surviving_key(self) -> None:
        result = anonymize_respondent_meta({"note": "call 415-555-0199 anytime"})
        assert "415-555-0199" not in result["note"]
        assert "[REDACTED]" in result["note"]

    def test_returns_new_dict_input_not_mutated(self) -> None:
        original = {"name": "Eve", "role": "designer"}
        result = anonymize_respondent_meta(original)
        # Input unchanged
        assert original == {"name": "Eve", "role": "designer"}
        # Output is a different object
        assert result is not original
        assert "name" not in result
        assert result["role"] == "designer"

    def test_empty_input_returns_empty(self) -> None:
        assert anonymize_respondent_meta({}) == {}

    def test_no_email_string_survives_in_output(self) -> None:
        """Strict check: no raw email pattern survives in any output value (I3)."""
        dirty = {
            "role": "user@example.com is great",
            "firstname": "ignored",
            "contact": "ping bob@test.org",
        }
        result = anonymize_respondent_meta(dirty)
        for val in result.values():
            if isinstance(val, str):
                assert not re.search(_EMAIL_PATTERN, val), (
                    f"raw email pattern survived in output value: {val!r}"
                )

    def test_no_phone_substring_survives_in_output(self) -> None:
        """Strict check: no raw phone pattern survives in any output value (I3/M2)."""
        dirty = {
            "note": "call +1 800 555 9999",
            "phone": "650-555-0100",
        }
        result = anonymize_respondent_meta(dirty)
        assert "phone" not in result
        # The "note" key survives but phone digits should be redacted
        note = result.get("note", "")
        assert not re.search(_PHONE_PATTERN, note), (
            f"raw phone pattern survived in output note: {note!r}"
        )

    # -- C1: nested dict PII leak --

    def test_nested_dict_identity_key_dropped(self) -> None:
        """Identity key inside a nested dict is dropped recursively (C1)."""
        result = anonymize_respondent_meta(
            {"data": {"name": "Jane Doe", "email": "j@x.com"}, "role": "PM"}
        )
        # name key must not appear anywhere
        assert "name" not in result
        nested = result.get("data", {})
        assert "name" not in nested, f"'name' key survived in nested dict: {nested}"
        # no raw email anywhere in serialized output
        result_str = json.dumps(result)
        assert not re.search(_EMAIL_PATTERN, result_str), (
            f"raw email survived in nested output: {result_str!r}"
        )
        # non-identity key preserved
        assert result.get("role") == "PM"

    def test_nested_dict_input_not_mutated(self) -> None:
        """Original input dict and nested dicts are NOT mutated (C1 immutability)."""
        inner = {"name": "Jane Doe", "email": "j@x.com"}
        original = {"data": inner, "role": "PM"}
        anonymize_respondent_meta(original)
        # Inner dict must be untouched
        assert inner == {"name": "Jane Doe", "email": "j@x.com"}, (
            "nested input dict was mutated"
        )
        assert original == {"data": inner, "role": "PM"}, (
            "top-level input dict was mutated"
        )

    def test_nested_list_pii_redacted(self) -> None:
        """Email/phone in a list value is redacted recursively (C1)."""
        result = anonymize_respondent_meta(
            {"tags": ["admin", "j@x.com", "415-555-0101"]}
        )
        tags = result.get("tags", [])
        for item in tags:
            if isinstance(item, str):
                assert not re.search(_EMAIL_PATTERN, item), (
                    f"raw email in list item: {item!r}"
                )
                assert not re.search(_PHONE_PATTERN, item), (
                    f"raw phone in list item: {item!r}"
                )

    # -- C2: integer phone value --

    def test_integer_phone_value_redacted(self) -> None:
        """An integer value that looks like a phone number is redacted (C2).

        The key 'callback_number' does not match any identity-key pattern so the
        key survives to Rule 2/3, where the integer value is stringified and
        matched against _PHONE_PATTERN.
        """
        result = anonymize_respondent_meta({"callback_number": 4155550101})
        assert result.get("callback_number") == "[REDACTED]", (
            f"integer phone value was not redacted: {result.get('callback_number')!r}"
        )

    def test_integer_non_phone_value_kept(self) -> None:
        """An integer value that does NOT match a phone pattern is kept (C2)."""
        result = anonymize_respondent_meta({"years_exp": 5, "score": 99})
        assert result.get("years_exp") == 5
        assert result.get("score") == 99

    # -- I1: extended identity key allowlist --

    def test_drops_respondent_key(self) -> None:
        """'respondent' key is an identity key and must be dropped (I1)."""
        result = anonymize_respondent_meta({"respondent": "Jane Doe", "role": "PM"})
        assert "respondent" not in result
        assert result.get("role") == "PM"

    def test_drops_speaker_key(self) -> None:
        result = anonymize_respondent_meta({"speaker": "Alice"})
        assert "speaker" not in result

    def test_drops_interviewer_key(self) -> None:
        result = anonymize_respondent_meta({"interviewer": "Bob"})
        assert "interviewer" not in result

    def test_drops_interviewee_key(self) -> None:
        result = anonymize_respondent_meta({"interviewee": "Carol"})
        assert "interviewee" not in result

    def test_drops_participant_key(self) -> None:
        result = anonymize_respondent_meta({"participant": "Dave"})
        assert "participant" not in result

    def test_drops_contact_person_key(self) -> None:
        result = anonymize_respondent_meta({"contact_person": "Eve"})
        assert "contact_person" not in result

    def test_drops_contact_key(self) -> None:
        result = anonymize_respondent_meta({"contact": "Frank"})
        assert "contact" not in result

    def test_drops_user_key(self) -> None:
        result = anonymize_respondent_meta({"user": "Grace"})
        assert "user" not in result

    def test_drops_author_key(self) -> None:
        result = anonymize_respondent_meta({"author": "Heidi"})
        assert "author" not in result

    def test_all_i1_identity_keys_dropped(self) -> None:
        """All I1 identity keys are dropped, non-identity keys preserved."""
        meta = {
            "respondent": "Jane Doe",
            "speaker": "Alice",
            "interviewer": "Bob",
            "interviewee": "Carol",
            "participant": "Dave",
            "contact_person": "Eve",
            "contact": "Frank",
            "user": "Grace",
            "author": "Heidi",
            "role": "PM",
            "segment": "Enterprise",
        }
        result = anonymize_respondent_meta(meta)
        for key in ("respondent", "speaker", "interviewer", "interviewee",
                    "participant", "contact_person", "contact", "user", "author"):
            assert key not in result, f"identity key {key!r} survived"
        assert result.get("role") == "PM"
        assert result.get("segment") == "Enterprise"


# ---------------------------------------------------------------------------
# B: ingest_survey
# ---------------------------------------------------------------------------


SURVEY_ID = "SV-TEST-1"

SYNTHETIC_RESPONSES = [
    {
        "respondent_meta": {
            "name": "Alice Smith",
            "email": "alice@example.com",
            "phone": "415-555-0101",
            "role": "Product Manager",
            "segment": "Enterprise",
            "region": "NA",
        },
        "answers": {
            "q_satisfaction": "Very satisfied with the pricing tiers",
            "q_feature": "The collaboration features are excellent",
            "q_recommend": "Would recommend to colleagues",
        },
        "raw_text": "Overall positive experience.",
    },
    {
        "respondent_meta": {
            "firstname": "Bob",
            "lastname": "Jones",
            "role": "Engineer",
            "segment": "SMB",
        },
        "answers": ["Pricing is competitive", "UI could be improved"],
        "raw_text": "Good product overall.",
    },
]


class TestIngestSurvey:
    def test_returns_source_ids_count(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ids = ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        assert len(ids) == len(SYNTHETIC_RESPONSES)

    def test_sources_have_survey_type(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        sources = _all_sources(db, run_id)
        assert len(sources) == len(SYNTHETIC_RESPONSES)
        for src in sources:
            assert src["source_type"] == "survey", (
                f"expected 'survey', got {src['source_type']!r}"
            )

    def test_source_ids_returned_are_persisted(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ids = ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        for sid in ids:
            assert db.get_source(sid) is not None, f"source {sid} not persisted"

    def test_evidence_chunks_have_survey_locators(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        chunks = _all_chunks(db, run_id)
        assert chunks, "expected at least one evidence chunk"
        for chunk in chunks:
            locator = chunk.get("locator") or ""
            assert locator.startswith(f"survey:{SURVEY_ID}/q"), (
                f"locator should be survey:{SURVEY_ID}/qN, got {locator!r}"
            )

    def test_respondent_meta_pii_stripped_from_db(self, tmp_path) -> None:
        """Persisted meta_json must NOT contain name/email/phone/firstname/lastname."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        sources = _all_sources(db, run_id)
        for src in sources:
            meta = json.loads(src.get("meta_json") or "{}")
            meta_str = json.dumps(meta).lower()
            # Key-level checks
            for bad_key in ("name", "email", "phone", "firstname", "lastname"):
                assert bad_key not in meta, (
                    f"PII key {bad_key!r} survived in stored meta: {meta}"
                )
            # Value-level checks: no email/phone pattern in any string value
            assert "alice@example.com" not in meta_str, (
                f"email value survived in meta: {meta}"
            )
            assert "415-555-0101" not in meta_str, (
                f"phone value survived in meta: {meta}"
            )
            # Non-PII keys must be preserved
            if "role" in json.loads(src.get("meta_json") or "{}"):
                assert meta.get("role") in ("Product Manager", "Engineer")

    def test_no_pii_in_any_stored_meta(self, tmp_path) -> None:
        """Exhaustive: no email/phone/name substring in any stored meta_json."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        sources = _all_sources(db, run_id)
        pii_values = [
            "alice@example.com",
            "alice",
            "smith",
            "bob",
            "jones",
            "415-555-0101",
        ]
        for src in sources:
            meta_str = (src.get("meta_json") or "").lower()
            for pii in pii_values:
                assert pii.lower() not in meta_str, (
                    f"PII fragment {pii!r} found in stored meta_json: {meta_str!r}"
                )

    def test_dict_answers_create_per_q_chunks(self, tmp_path) -> None:
        """Dict-keyed answers each become a distinct evidence chunk."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        response = {
            "respondent_meta": {"role": "designer"},
            "answers": {"q1": "answer one", "q2": "answer two", "q3": "answer three"},
        }
        ingest_survey(db, run_id, [response], survey_id="SV-DICT")
        chunks = _all_chunks(db, run_id)
        locators = [c["locator"] for c in chunks]
        assert "survey:SV-DICT/q1" in locators
        assert "survey:SV-DICT/q2" in locators
        assert "survey:SV-DICT/q3" in locators

    def test_list_answers_create_per_q_chunks(self, tmp_path) -> None:
        """List answers each become a distinct evidence chunk."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        response = {
            "respondent_meta": {"role": "developer"},
            "answers": ["first answer", "second answer"],
        }
        ingest_survey(db, run_id, [response], survey_id="SV-LIST")
        chunks = _all_chunks(db, run_id)
        locators = [c["locator"] for c in chunks]
        assert "survey:SV-LIST/q1" in locators
        assert "survey:SV-LIST/q2" in locators


# ---------------------------------------------------------------------------
# C: ingest_interview
# ---------------------------------------------------------------------------


INTERVIEW_ID = "INT-TEST-1"

SYNTHETIC_TRANSCRIPT = [
    {
        "speaker_meta": {
            "name": "Carol Danvers",
            "email": "carol@example.com",
            "phone": "650-555-0200",
            "role": "CTO",
        },
        "text": "We chose this product primarily for its API integrations.",
        "title": "Intro",
    },
    {
        "speaker_meta": {
            "firstname": "Dave",
            "role": "Engineer",
            "years_exp": 8,
        },
        "text": "The pricing model is transparent and easy to understand.",
    },
    {
        # Segment with empty text — should be skipped
        "speaker_meta": {"role": "Intern"},
        "text": "",
    },
]


class TestIngestInterview:
    def test_returns_source_ids_count_skips_empty(self, tmp_path) -> None:
        """Empty-text segments are skipped; only 2 of 3 segments have text."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ids = ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        assert len(ids) == 2  # 3rd segment has no text

    def test_sources_have_interview_type(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        sources = _all_sources(db, run_id)
        assert len(sources) == 2
        for src in sources:
            assert src["source_type"] == "interview", (
                f"expected 'interview', got {src['source_type']!r}"
            )

    def test_source_ids_returned_are_persisted(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ids = ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        for sid in ids:
            assert db.get_source(sid) is not None, f"source {sid} not persisted"

    def test_evidence_chunks_have_interview_locators(self, tmp_path) -> None:
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        chunks = _all_chunks(db, run_id)
        assert len(chunks) == 2
        for chunk in chunks:
            locator = chunk.get("locator") or ""
            assert locator.startswith(f"interview:{INTERVIEW_ID}/seg"), (
                f"locator should be interview:{INTERVIEW_ID}/segN, got {locator!r}"
            )

    def test_locator_uses_original_segment_index(self, tmp_path) -> None:
        """Locators are numbered by original position, not by skipped-count."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        # Segment 1 has text (seg1), segment 2 is empty (skipped), segment 3 has text (seg3)
        transcript = [
            {"speaker_meta": {"role": "PM"}, "text": "First segment content"},
            {"speaker_meta": {"role": "Dev"}, "text": ""},
            {"speaker_meta": {"role": "CEO"}, "text": "Third segment content"},
        ]
        ingest_interview(db, run_id, transcript, interview_id="INT-IDX")
        chunks = _all_chunks(db, run_id)
        locators = {c["locator"] for c in chunks}
        assert "interview:INT-IDX/seg1" in locators
        assert "interview:INT-IDX/seg3" in locators
        assert "interview:INT-IDX/seg2" not in locators

    def test_speaker_meta_pii_stripped_from_db(self, tmp_path) -> None:
        """Persisted meta_json must NOT contain name/email/phone/firstname."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        sources = _all_sources(db, run_id)
        for src in sources:
            meta = json.loads(src.get("meta_json") or "{}")
            for bad_key in ("name", "email", "phone", "firstname"):
                assert bad_key not in meta, (
                    f"PII key {bad_key!r} survived in stored meta: {meta}"
                )
            meta_str = json.dumps(meta).lower()
            assert "carol@example.com" not in meta_str
            assert "carol danvers" not in meta_str
            assert "650-555-0200" not in meta_str

    def test_no_pii_in_any_stored_meta(self, tmp_path) -> None:
        """Exhaustive: no PII substring in any stored meta_json."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        sources = _all_sources(db, run_id)
        pii_values = [
            "carol danvers",
            "carol@example.com",
            "650-555-0200",
            "dave",
        ]
        for src in sources:
            meta_str = (src.get("meta_json") or "").lower()
            for pii in pii_values:
                assert pii.lower() not in meta_str, (
                    f"PII fragment {pii!r} found in meta_json: {meta_str!r}"
                )

    def test_non_pii_meta_preserved(self, tmp_path) -> None:
        """Non-identity keys (role, years_exp) are kept in the stored meta."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        sources = _all_sources(db, run_id)
        roles = [
            json.loads(s.get("meta_json") or "{}").get("role")
            for s in sources
        ]
        assert "CTO" in roles or "Engineer" in roles, (
            f"expected at least one role preserved, got {roles}"
        )


# ---------------------------------------------------------------------------
# D: PII-free invariant — extended to raw_text and evidence_chunks (I2)
# ---------------------------------------------------------------------------


class TestPIIFreeInvariantAllStorage:
    """I2: email/phone must not survive in ANY stored field: meta_json,
    sources.raw_text, OR evidence_chunks.text.

    Free-text CONTENT (answers/segments) is preserved EXCEPT for redacted
    email/phone PII; name tokens in answer/segment content are NOT removed
    (NER is required for that — known, documented limitation).
    """

    def test_survey_raw_text_no_email_phone(self, tmp_path) -> None:
        """sources.raw_text must not contain raw email/phone after ingest (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        responses_with_pii_in_text = [
            {
                "respondent_meta": {"role": "PM"},
                "answers": {"q1": "Contact me at survey_user@corp.io for follow-up"},
                "raw_text": "Please reach out at survey_user@corp.io or 415-555-0200",
            }
        ]
        ingest_survey(db, run_id, responses_with_pii_in_text, survey_id="SV-RAWTEXT")
        sources = _all_sources(db, run_id)
        for src in sources:
            raw = src.get("raw_text") or ""
            assert not re.search(_EMAIL_PATTERN, raw), (
                f"raw email survived in sources.raw_text: {raw!r}"
            )
            assert not re.search(_PHONE_PATTERN, raw), (
                f"raw phone survived in sources.raw_text: {raw!r}"
            )

    def test_survey_chunks_no_email_phone(self, tmp_path) -> None:
        """evidence_chunks.text must not contain raw email/phone after survey ingest (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        responses_with_pii_in_answers = [
            {
                "respondent_meta": {"role": "dev"},
                "answers": {
                    "q1": "Reach me at chunk_user@example.com",
                    "q2": "My backup number is 650-555-0300",
                },
            }
        ]
        ingest_survey(db, run_id, responses_with_pii_in_answers, survey_id="SV-CHUNKS")
        chunks = _all_chunks(db, run_id)
        assert chunks, "expected evidence chunks"
        for chunk in chunks:
            text = chunk.get("text") or ""
            assert not re.search(_EMAIL_PATTERN, text), (
                f"raw email survived in evidence_chunks.text: {text!r}"
            )
            assert not re.search(_PHONE_PATTERN, text), (
                f"raw phone survived in evidence_chunks.text: {text!r}"
            )

    def test_interview_raw_text_no_email_phone(self, tmp_path) -> None:
        """sources.raw_text must not contain raw email/phone after interview ingest (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        transcript_with_pii = [
            {
                "speaker_meta": {"role": "CTO"},
                "text": "You can reach our team at int_seg@company.org or +44 20 7946 0958",
            }
        ]
        ingest_interview(db, run_id, transcript_with_pii, interview_id="INT-RAWTEXT")
        sources = _all_sources(db, run_id)
        for src in sources:
            raw = src.get("raw_text") or ""
            assert not re.search(_EMAIL_PATTERN, raw), (
                f"raw email survived in sources.raw_text: {raw!r}"
            )
            assert not re.search(_PHONE_PATTERN, raw), (
                f"raw phone survived in sources.raw_text: {raw!r}"
            )

    def test_interview_chunks_no_email_phone(self, tmp_path) -> None:
        """evidence_chunks.text must not contain raw email/phone after interview ingest (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        transcript_with_pii = [
            {
                "speaker_meta": {"role": "Engineer"},
                "text": "Please email int_chunk@example.com or call 800-555-1234",
            }
        ]
        ingest_interview(db, run_id, transcript_with_pii, interview_id="INT-CHUNKS")
        chunks = _all_chunks(db, run_id)
        assert chunks, "expected evidence chunks"
        for chunk in chunks:
            text = chunk.get("text") or ""
            assert not re.search(_EMAIL_PATTERN, text), (
                f"raw email survived in evidence_chunks.text: {text!r}"
            )
            assert not re.search(_PHONE_PATTERN, text), (
                f"raw phone survived in evidence_chunks.text: {text!r}"
            )

    def test_exhaustive_no_email_phone_anywhere_survey(self, tmp_path) -> None:
        """Comprehensive: no email/phone regex match anywhere in meta_json, raw_text,
        or evidence_chunks.text for a survey with PII scattered in all fields (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_survey(db, run_id, SYNTHETIC_RESPONSES, survey_id=SURVEY_ID)
        sources = _all_sources(db, run_id)
        chunks = _all_chunks(db, run_id)

        for src in sources:
            for field_name in ("meta_json", "raw_text"):
                text = src.get(field_name) or ""
                assert not re.search(_EMAIL_PATTERN, text), (
                    f"email in sources.{field_name}: {text!r}"
                )
                assert not re.search(_PHONE_PATTERN, text), (
                    f"phone in sources.{field_name}: {text!r}"
                )

        for chunk in chunks:
            text = chunk.get("text") or ""
            assert not re.search(_EMAIL_PATTERN, text), (
                f"email in evidence_chunks.text: {text!r}"
            )
            assert not re.search(_PHONE_PATTERN, text), (
                f"phone in evidence_chunks.text: {text!r}"
            )

    def test_exhaustive_no_email_phone_anywhere_interview(self, tmp_path) -> None:
        """Comprehensive: no email/phone anywhere for interview with PII in all fields (I2)."""
        db = _make_db(tmp_path)
        run_id = db.create_run(category="cat", competitors=["Acme"], goal="test")
        ingest_interview(db, run_id, SYNTHETIC_TRANSCRIPT, interview_id=INTERVIEW_ID)
        sources = _all_sources(db, run_id)
        chunks = _all_chunks(db, run_id)

        for src in sources:
            for field_name in ("meta_json", "raw_text"):
                text = src.get(field_name) or ""
                assert not re.search(_EMAIL_PATTERN, text), (
                    f"email in sources.{field_name}: {text!r}"
                )
                assert not re.search(_PHONE_PATTERN, text), (
                    f"phone in sources.{field_name}: {text!r}"
                )

        for chunk in chunks:
            text = chunk.get("text") or ""
            assert not re.search(_EMAIL_PATTERN, text), (
                f"email in evidence_chunks.text: {text!r}"
            )
            assert not re.search(_PHONE_PATTERN, text), (
                f"phone in evidence_chunks.text: {text!r}"
            )
