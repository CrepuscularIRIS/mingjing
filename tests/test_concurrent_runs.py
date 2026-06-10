"""Run-level concurrency smoke test (开题 Q&A: 并发 nice-to-have).

POST /runs spawns one daemon worker thread per run with NO global mutex —
concurrent submissions are supported by design; the SQLite single-writer lock
(`db._base._WRITE_LOCK`) serializes COMMITS, not runs. This test proves the
two properties judges would ask about, deterministically:

1. CONCURRENCY: two executors are alive inside their run simultaneously
   (a Barrier(2) only releases when both threads reach it — if runs were
   serialized the barrier would time out and the test would fail).
2. ISOLATION: each run's trace events land only under its own run_id.
"""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database

_BODY = {"category": "CRM", "competitors": ["Acme"], "goal": "g"}


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "conc.db"))
    d.init_schema()
    return d


def test_two_runs_execute_concurrently_without_cross_pollution(db):
    barrier = threading.Barrier(2, timeout=5)
    done: list[str] = []

    def executor(run_id: str) -> None:
        # Both worker threads must be in flight at the same time to pass.
        barrier.wait()
        db.insert_trace_event(
            {
                "run_id": run_id,
                "agent": "system",
                "node": "intake",
                "event_type": "smoke",
                "payload_json": json.dumps({"run": run_id}),
            }
        )
        done.append(run_id)

    client = TestClient(create_app(db=db, run_executor=executor))
    r1 = client.post("/runs", json=_BODY).json()["run_id"]
    r2 = client.post("/runs", json=_BODY).json()["run_id"]

    deadline = time.time() + 5
    while len(done) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert set(done) == {r1, r2}, "both runs must complete (no serialization deadlock)"

    # Isolation: each run's events live only under its own run_id.
    for rid, other in ((r1, r2), (r2, r1)):
        events = db.trace_events_for_run(rid)
        smoke = [e for e in events if e["event_type"] == "smoke"]
        assert len(smoke) == 1
        assert json.loads(smoke[0]["payload_json"])["run"] == rid != other
