"""POST /runs/{id}/survey/import — the REAL survey-research door (问卷调研).

The engine (ingest.ingest_survey: PII anonymization, survey:<id>/q<n> locators,
authoritative source_type="survey") existed with no entry point. This endpoint
is the door: real responses come in as source_mode="INGESTED" rows that keep
authoritative scoring weight — the honest counterpart of the SIMULATED fixture
lane (which is display/grounding-only). A survey_ingested trace event lands in
the audit chain.
"""

import json

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "imp.db"))
    d.init_schema()
    return d


@pytest.fixture()
def run_id(db: Database) -> str:
    return db.create_run(category="CRM", competitors=["Acme"], goal="g")


@pytest.fixture()
def client(db: Database) -> TestClient:
    return TestClient(create_app(db=db, run_executor=None))


_BODY = {
    "survey_id": "SV-REAL-1",
    "responses": [
        {
            "respondent_meta": {"name": "张伟", "email": "zhangwei@example.com"},
            "answers": {
                "pricing": "We pay $10 per user/month on the Basic plan.",
                "sentiment": "Overall satisfied; mobile app is slow.",
            },
        },
        {
            "raw_text": "I am on the free tier. Contact me at 138-0013-8000.",
        },
    ],
}


def test_import_creates_ingested_survey_sources(client, db, run_id):
    resp = client.post(f"/runs/{run_id}/survey/import", json=_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["count"] == 2
    assert len(data["source_ids"]) == 2
    for sid in data["source_ids"]:
        row = db.get_source(sid)
        assert row is not None
        assert row["source_type"] == "survey"
        # REAL ingestion keeps authoritative weight — must be INGESTED,
        # never SIMULATED (and scoring.contributes_to_tier must hold).
        assert row["source_mode"] == "INGESTED"


def test_import_scrubs_pii_before_persistence(client, db, run_id):
    resp = client.post(f"/runs/{run_id}/survey/import", json=_BODY)
    sids = resp.json()["source_ids"]
    all_text = " ".join(
        (db.get_source(sid)["raw_text"] or "") + (db.get_source(sid)["meta_json"] or "")
        for sid in sids
    )
    assert "zhangwei@example.com" not in all_text
    assert "138-0013-8000" not in all_text


def test_import_emits_survey_ingested_trace_event(client, db, run_id):
    client.post(f"/runs/{run_id}/survey/import", json=_BODY)
    events = [
        e for e in db.trace_events_for_run(run_id)
        if e["event_type"] == "survey_ingested"
    ]
    assert len(events) == 1
    payload = json.loads(events[0]["payload_json"])
    assert payload["survey_id"] == "SV-REAL-1"
    assert payload["count"] == 2


def test_import_unknown_run_404(client):
    resp = client.post("/runs/nonexistent/survey/import", json=_BODY)
    assert resp.status_code == 404


def test_import_empty_responses_422(client, run_id):
    resp = client.post(
        f"/runs/{run_id}/survey/import",
        json={"survey_id": "SV-X", "responses": []},
    )
    assert resp.status_code == 422


def test_import_caps_batch_size(client, run_id):
    big = {"survey_id": "SV-BIG", "responses": [{"raw_text": "ok"}] * 51}
    resp = client.post(f"/runs/{run_id}/survey/import", json=big)
    assert resp.status_code == 422


def _count_sources(db: Database, run_id: str) -> int:
    return len(db.sources_for_run(run_id))


@pytest.mark.parametrize(
    "bad_response",
    [
        # Nested non-string answer leaves (would have raised mid-ingest).
        {"answers": {"q1": {"deep": ["x"]}}},
        # answers as a list of dicts instead of strings.
        {"answers": [{"q": "v"}]},
        # respondent_meta as a bare string instead of a dict.
        {"respondent_meta": "张伟", "raw_text": "ok"},
        # No content at all.
        {"title": "empty response"},
        # Empty answer leaf.
        {"answers": {"q1": "  "}},
        # Unknown extra key (extra=forbid).
        {"raw_text": "ok", "injected": {"x": 1}},
        # Unbounded payloads (DoS / prompt-stuffing): too many answers,
        # oversized answer leaf, oversized meta value, too many meta keys.
        {"answers": {f"q{i}": "x" for i in range(21)}},
        {"answers": ["y" * 4_001]},
        {"raw_text": "ok", "respondent_meta": {"bio": "z" * 501}},
        {"raw_text": "ok", "respondent_meta": {f"k{i}": "v" for i in range(21)}},
        {"raw_text": "x" * 20_001},
    ],
)
def test_malformed_nested_payloads_rejected_atomically(client, db, run_id, bad_response):
    """422 + ZERO rows persisted — even when VALID responses precede the bad one.

    Codex stop-review: ingest persists row-by-row, so a mid-batch shape error
    used to leave earlier responses in the DB with no audit event. Strict
    validation now rejects the whole batch before any persistence.
    """
    before = _count_sources(db, run_id)
    body = {
        "survey_id": "SV-BAD",
        "responses": [{"raw_text": "perfectly valid first response"}, bad_response],
    }
    resp = client.post(f"/runs/{run_id}/survey/import", json=body)
    assert resp.status_code == 422
    assert _count_sources(db, run_id) == before, "no partial rows may persist"
    events = [
        e for e in db.trace_events_for_run(run_id)
        if e["event_type"] == "survey_ingested"
    ]
    assert events == [], "no audit event for a rejected batch"
