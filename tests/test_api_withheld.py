"""GET /runs/{run_id}/withheld — expose the withheld-claims disclosure over HTTP.

The backend already computes ``build_withheld_disclosure`` (claims that stayed
``draft`` because the last QA round flagged them, + their issue codes), but it
was only reachable in-process. The frontend needs it to render a self-explaining
empty/partial run ("N claims withheld because VALUE_UNSUPPORTED…") instead of a
blank panel. This endpoint serves that disclosure verbatim.
"""

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "test.db"))
    d.init_schema()
    return d


@pytest.fixture()
def client(db: Database) -> TestClient:
    return TestClient(create_app(db=db, run_executor=None))


def _seed_flagged_claim(db: Database, *, round_idx: int = 2) -> str:
    """Seed a run with one draft claim flagged by the LAST QA round."""
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    db.append_claim(
        {
            "id": "c1",
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing_model",
            "claim_type": "fact",
            "statement": "Pro tier costs $10 per month",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "weak",
            "status": "draft",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    db.append_qc_report(
        {
            "id": "qc1",
            "run_id": run_id,
            "claim_id": "c1",
            "round": round_idx,
            "verdict": "reject",
            "issues_json": '["VALUE_UNSUPPORTED", "WEAK_EVIDENCE"]',
        }
    )
    return run_id


def test_withheld_endpoint_returns_disclosure(client: TestClient, db: Database) -> None:
    run_id = _seed_flagged_claim(db, round_idx=2)
    resp = client.get(f"/runs/{run_id}/withheld")
    assert resp.status_code == 200
    body = resp.json()
    assert "withheld" in body
    items = body["withheld"]
    assert len(items) == 1
    assert items[0]["claim_id"] == "c1"
    assert "VALUE_UNSUPPORTED" in items[0]["issue_codes"]
    assert items[0]["round"] == 2


def test_withheld_endpoint_empty_for_clean_run(client: TestClient, db: Database) -> None:
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    resp = client.get(f"/runs/{run_id}/withheld")
    assert resp.status_code == 200
    assert resp.json() == {"withheld": []}


def test_withheld_endpoint_unknown_run_404(client: TestClient) -> None:
    resp = client.get("/runs/does-not-exist/withheld")
    assert resp.status_code == 404
