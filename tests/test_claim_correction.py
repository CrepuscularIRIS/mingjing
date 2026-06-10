"""Tests for POST /runs/{run_id}/claims/{claim_id}/correct (Task 25).

Verifies human-in-the-loop claim correction: accept / reject / edit actions
all create an append-only superseding version, preserve audit history, and are
attributable to produced_by="human:correction".
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Database:
    """Fresh schema-initialised Database in a temp directory."""
    d = Database(str(tmp_path / "test.db"))
    d.init_schema()
    return d


@pytest.fixture()
def run_id(db: Database) -> str:
    """A pre-created run in the DB."""
    return db.create_run(
        category="CRM",
        competitors=["Acme", "BetaCo"],
        goal="compare pricing",
    )


@pytest.fixture()
def client(db: Database) -> TestClient:
    """TestClient backed by the injected DB (no network, no LLM)."""
    return TestClient(create_app(db=db))


def _seed_claim(db: Database, run_id: str, **overrides) -> str:
    """Append a minimal claim row; return its id."""
    cid = str(uuid.uuid4())
    row = {
        "id": cid,
        "run_id": run_id,
        "competitor": "Acme",
        "schema_field": "pricing",
        "claim_type": "fact",
        "statement": "Acme starter plan costs $10/mo.",
        "value_json": json.dumps({"amount": 10, "unit": "USD/mo"}),
        "evidence_json": json.dumps([]),
        "based_on_json": json.dumps([]),
        "evidence_strength": "moderate",
        "status": "draft",
        "version": 1,
        "produced_by": "analyst",
    }
    row.update(overrides)
    db.append_claim(row)
    return cid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_accept_promotes_claim_to_pass(db, run_id, client):
    """action=accept sets status to 'pass' and bumps version."""
    claim_id = _seed_claim(db, run_id)

    resp = client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "accept"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["claim_id"] == claim_id
    assert data["status"] == "pass"
    assert data["produced_by"] == "human:correction"
    assert data["version"] == 2

    latest_rows = db.latest_claims_for_run(run_id)
    latest = next(r for r in latest_rows if r["id"] == claim_id)
    assert latest["status"] == "pass"
    assert latest["version"] == 2
    assert latest["produced_by"] == "human:correction"


def test_reject_sets_rejected(db, run_id, client):
    """action=reject sets status to 'rejected'."""
    claim_id = _seed_claim(db, run_id)

    resp = client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "reject"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "rejected"

    latest_rows = db.latest_claims_for_run(run_id)
    latest = next(r for r in latest_rows if r["id"] == claim_id)
    assert latest["status"] == "rejected"
    assert latest["produced_by"] == "human:correction"


def test_edit_updates_value_and_statement(db, run_id, client):
    """action=edit updates statement and value_json; status becomes 'pass'."""
    claim_id = _seed_claim(db, run_id)
    new_statement = "Acme starter plan now costs $12/mo."
    new_value = {"amount": 12, "unit": "USD/mo"}

    resp = client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={
            "action": "edit",
            "statement": new_statement,
            "value": new_value,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pass"
    assert resp.json()["produced_by"] == "human:correction"

    latest_rows = db.latest_claims_for_run(run_id)
    latest = next(r for r in latest_rows if r["id"] == claim_id)
    assert latest["statement"] == new_statement
    assert json.loads(latest["value_json"]) == new_value
    assert latest["status"] == "pass"
    assert latest["produced_by"] == "human:correction"


def test_correct_unknown_run_404(db, client):
    """Correcting a claim in a non-existent run returns 404."""
    resp = client.post(
        "/runs/doesnotexist/claims/alsofake/correct",
        json={"action": "accept"},
    )
    assert resp.status_code == 404
    assert "Run" in resp.json()["detail"]


def test_correct_unknown_claim_404(db, run_id, client):
    """Correcting a non-existent claim in a real run returns 404."""
    resp = client.post(
        f"/runs/{run_id}/claims/no-such-claim/correct",
        json={"action": "accept"},
    )
    assert resp.status_code == 404
    assert "Claim" in resp.json()["detail"]


def test_correction_is_append_only(db, run_id, client):
    """After correction the original version row still exists (audit preserved)."""
    claim_id = _seed_claim(db, run_id)

    before = db.claim_versions(run_id, claim_id)
    assert len(before) == 1
    original_status = before[0]["status"]

    client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "reject"},
    )

    after = db.claim_versions(run_id, claim_id)
    assert len(after) == 2  # one new version appended

    # Original version 1 row is still present and unchanged
    v1 = next(r for r in after if r["version"] == 1)
    assert v1["status"] == original_status
    assert v1["produced_by"] == "analyst"

    # New version 2 is the correction
    v2 = next(r for r in after if r["version"] == 2)
    assert v2["status"] == "rejected"
    assert v2["produced_by"] == "human:correction"


# ---------------------------------------------------------------------------
# G7: correction note persistence (HITL audit trail; advisory, no scoring impact)
# ---------------------------------------------------------------------------


def test_correction_persists_note(db, run_id, client):
    claim_id = _seed_claim(db, run_id)
    resp = client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "accept", "note": "verified the pricing page myself"},
    )
    assert resp.status_code == 201
    assert resp.json()["note"] == "verified the pricing page myself"
    v2 = max(db.claim_versions(run_id, claim_id), key=lambda r: int(r.get("version", 1)))
    assert v2.get("note") == "verified the pricing page myself"


def test_correction_without_note_leaves_null(db, run_id, client):
    claim_id = _seed_claim(db, run_id)
    resp = client.post(f"/runs/{run_id}/claims/{claim_id}/correct", json={"action": "accept"})
    assert resp.status_code == 201
    v2 = max(db.claim_versions(run_id, claim_id), key=lambda r: int(r.get("version", 1)))
    assert v2.get("note") is None


def test_correction_note_does_not_change_verdict(db, run_id, client):
    claim_id = _seed_claim(db, run_id, evidence_strength="moderate")
    client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "accept", "note": "a note"},
    )
    v2 = max(db.claim_versions(run_id, claim_id), key=lambda r: int(r.get("version", 1)))
    # Note is advisory: status/strength are driven by the action, not the note.
    assert v2["status"] == "pass"
    assert v2["evidence_strength"] == "moderate"


def test_note_not_carried_forward(db, run_id, client):
    claim_id = _seed_claim(db, run_id)
    client.post(
        f"/runs/{run_id}/claims/{claim_id}/correct",
        json={"action": "accept", "note": "first note"},
    )
    client.post(f"/runs/{run_id}/claims/{claim_id}/correct", json={"action": "accept"})
    v3 = max(db.claim_versions(run_id, claim_id), key=lambda r: int(r.get("version", 1)))
    assert int(v3["version"]) == 3
    assert v3.get("note") is None  # a later correction without a note leaves it NULL
