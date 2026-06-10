"""Compliance tests (Task 18, step 5).

Two invariants verified offline:

1. ``test_collector_calls_robots_before_fetch`` — Confirms the Collector gates
   every URL through ``robots.is_allowed`` BEFORE calling ``fetch_with_fallback``.
   Monkeypatches ``robots.is_allowed`` to return False; asserts that no fetch
   attempt is made and the hit is recorded as ``skipped_robots``.

2. ``test_ingested_meta_is_anonymized`` — Confirms that survey/interview ingest
   stores NO name / email / phone PII in the DB. Uses synthetic PII-rich input
   and scans all stored rows (meta_json, raw_text, evidence_chunks.text).

No network, no live LLM.
"""

import json
import re

import pytest

from mingjing.collector import robots as robots_mod
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.ingest import _EMAIL_PATTERN, _PHONE_PATTERN, ingest_interview, ingest_survey

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "test.db"))
    db.init_schema()
    return db


def _all_sources(db: Database, run_id: str) -> list[dict]:
    cur = db._conn.execute("SELECT * FROM sources WHERE run_id = ?", (run_id,))
    return [dict(r) for r in cur.fetchall()]


def _all_chunks(db: Database, run_id: str) -> list[dict]:
    cur = db._conn.execute(
        "SELECT * FROM evidence_chunks WHERE run_id = ?", (run_id,)
    )
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# 1. Robots gate wired into Collector
# ---------------------------------------------------------------------------


def test_collector_calls_robots_before_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """robots.is_allowed must be called BEFORE fetch_with_fallback for each hit.

    Strategy:
    - Patch ``search_mod`` (the search callable) in the collector agent module
      to return one synthetic hit without hitting the network.
    - Patch ``robots.is_allowed`` to return False (URL disallowed).
    - Patch ``fetch_with_fallback`` to raise if called — it must NOT be called.
    - Assert the result records ``fetched=False, reason="skipped_robots"``.

    Note: In ``agents/collector.py``, the search callable is imported as
    ``_search_fn`` (``from ..collector.search import search as _search_fn``), so
    the collector calls ``_search_fn(query, ...)`` directly.  We monkeypatch the
    name ``_search_fn`` on the agent module's namespace.
    """
    import mingjing.agents.collector as collector_agent
    from mingjing.collector import fetch as fetch_mod

    FAKE_URL = "https://blocked.example.com/page"
    FAKE_HIT = {"url": FAKE_URL, "title": "blocked page", "snippet": ""}

    # Patch the search callable in the agent module to return one synthetic hit.
    def _fake_search(*a, **kw):  # type: ignore[no-untyped-def]
        return [FAKE_HIT]

    monkeypatch.setattr(collector_agent, "_search_fn", _fake_search)

    # Patch robots gate to disallow the URL.
    robots_called_with: list[str] = []

    def fake_is_allowed(url: str, fetch_robots_fn) -> bool:
        robots_called_with.append(url)
        return False  # disallow

    monkeypatch.setattr(robots_mod, "is_allowed", fake_is_allowed)

    # Patch fetch_with_fallback so any call raises — proving it was never invoked.
    def must_not_be_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError(
            "fetch_with_fallback was called despite robots disallow — gate not wired"
        )

    monkeypatch.setattr(fetch_mod, "fetch_with_fallback", must_not_be_called)
    # Also patch it on the agent module's namespace in case it closed over it.
    monkeypatch.setattr(collector_agent, "fetch_with_fallback", must_not_be_called)

    # Run the collector with a dummy cache and a no-op fetch_robots callable.
    class _DummyCache:
        def get(self, url: str) -> FetchResult | None:
            return None

    result = collector_agent.collect(
        "test query",
        _DummyCache(),
        max_results=5,
        source_cap=3,
        fetch_robots=lambda domain: "",  # injected no-op robots fetcher
    )

    # robots.is_allowed must have been called with the URL.
    assert FAKE_URL in robots_called_with, (
        f"robots.is_allowed was NOT called for {FAKE_URL!r}; "
        f"called with: {robots_called_with}"
    )

    # The hit must be recorded as skipped_robots, not fetched.
    assert len(result) == 1
    hit = result[0]
    assert hit["fetched"] is False, f"expected fetched=False, got {hit.get('fetched')}"
    assert hit.get("reason") == "skipped_robots", (
        f"expected reason='skipped_robots', got {hit.get('reason')!r}"
    )


# ---------------------------------------------------------------------------
# 2. Ingested meta is anonymized
# ---------------------------------------------------------------------------


_PII_SURVEY_RESPONSES = [
    {
        "respondent_meta": {
            "name": "Jane Doe",
            "email": "jane.doe@company.example",
            "phone": "415-555-9876",
            "mobile": "+1 800 555 1234",
            "role": "Product Manager",
            "segment": "Enterprise",
        },
        "answers": {
            "q_name": "My name is Jane Doe",
            "q_contact": "Reach me at jane.doe@company.example",
            "q_opinion": "The product pricing is competitive.",
        },
        "raw_text": "Email jane.doe@company.example or call 415-555-9876 for follow-up.",
    },
]

_PII_TRANSCRIPT = [
    {
        "speaker_meta": {
            "name": "Bob Smith",
            "email": "bob.smith@interview.example",
            "phone": "650-555-4321",
            "role": "CTO",
        },
        "text": "Contact me at bob.smith@interview.example or +44 20 7946 0123.",
    },
]


def test_survey_open_text_strong_pii_scrubbed_in_chunks(tmp_path) -> None:
    """ingest_survey must ENFORCE the strong open-text scrubber on persistence.

    A survey answer carrying a trigger-phrase name, an email, a CN mobile, and
    an 18-digit CN national ID must have all of them stripped from the persisted
    evidence-chunk text (not just the weaker email/phone redaction).
    """
    responses = [
        {
            "respondent_meta": {"role": "PM", "segment": "Enterprise"},
            "answers": {
                "q_open": (
                    "我叫张伟，邮箱 zhang@example.com，手机 13812345678，"
                    "身份证 11010119900307123X，整体满意。"
                ),
            },
            "raw_text": "Contact me at zhang@example.com.",
        },
    ]
    db = _make_db(tmp_path)
    run_id = db.create_run(category="comp", competitors=["X"], goal="test")
    ingest_survey(db, run_id, responses, survey_id="SV-STRONG-1")

    chunks = _all_chunks(db, run_id)
    assert chunks, "expected at least one evidence chunk"
    blob = " ".join(c.get("text") or "" for c in chunks)
    # Strong-PII tokens that the open-text scrubber must remove.
    assert "张伟" not in blob, f"trigger-phrase name survived: {blob!r}"
    assert "zhang@example.com" not in blob, f"email survived: {blob!r}"
    assert "13812345678" not in blob, f"CN mobile survived: {blob!r}"
    assert "11010119900307123X" not in blob, f"CN national ID survived: {blob!r}"
    # And the placeholder tokens prove the scrubber ran (not just dropped text).
    assert "[ID]" in blob and "[NAME]" in blob, (
        f"expected scrubber placeholders in persisted chunk: {blob!r}"
    )


def test_ingested_meta_is_anonymized(tmp_path) -> None:
    """Survey and interview ingest must store NO name/email/phone PII in ANY DB field.

    Checks all stored rows: sources.meta_json, sources.raw_text, and
    evidence_chunks.text. The input contains PII in meta, answers, and raw_text.
    """
    db = _make_db(tmp_path)
    run_id = db.create_run(category="comp", competitors=["X"], goal="test")

    # Ingest survey with PII.
    ingest_survey(db, run_id, _PII_SURVEY_RESPONSES, survey_id="SV-COMPLY-1")

    # Ingest interview with PII.
    ingest_interview(db, run_id, _PII_TRANSCRIPT, interview_id="INT-COMPLY-1")

    sources = _all_sources(db, run_id)
    chunks = _all_chunks(db, run_id)

    # All raw PII strings that must NOT appear in any stored field.
    pii_literals = [
        "jane.doe@company.example",
        "bob.smith@interview.example",
        "415-555-9876",
        "650-555-4321",
        "+1 800 555 1234",
        "+44 20 7946 0123",
    ]

    # Identity keys that must NOT appear as top-level keys in meta_json.
    identity_keys = {"name", "email", "phone", "mobile", "cell", "tel",
                     "firstname", "lastname", "surname"}

    for src in sources:
        meta = json.loads(src.get("meta_json") or "{}")
        for bad_key in identity_keys:
            assert bad_key not in meta, (
                f"identity key {bad_key!r} survived in stored meta_json: {meta}"
            )
        for field_name in ("meta_json", "raw_text"):
            text = (src.get(field_name) or "").lower()
            for pii in pii_literals:
                assert pii.lower() not in text, (
                    f"PII {pii!r} found in sources.{field_name}: {text!r}"
                )
        # Regex-level check for any email/phone pattern.
        for field_name in ("meta_json", "raw_text"):
            text = src.get(field_name) or ""
            assert not re.search(_EMAIL_PATTERN, text), (
                f"email pattern in sources.{field_name}: {text!r}"
            )
            assert not re.search(_PHONE_PATTERN, text), (
                f"phone pattern in sources.{field_name}: {text!r}"
            )

    for chunk in chunks:
        text = chunk.get("text") or ""
        for pii in pii_literals:
            assert pii.lower() not in text.lower(), (
                f"PII {pii!r} found in evidence_chunks.text: {text!r}"
            )
        assert not re.search(_EMAIL_PATTERN, text), (
            f"email pattern in evidence_chunks.text: {text!r}"
        )
        assert not re.search(_PHONE_PATTERN, text), (
            f"phone pattern in evidence_chunks.text: {text!r}"
        )
