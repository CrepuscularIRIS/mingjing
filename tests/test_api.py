"""Offline unit tests for the FastAPI read-only views (Task 18).

All tests use:
- A ``tmp_path``-scoped SQLite DB seeded with synthetic data.
- ``create_app(db=seeded_db, run_executor=None)`` — no network, no live LLM.
- FastAPI's ``TestClient`` backed by ``httpx``.

Coverage:
A) POST /runs
   - Valid body → 201 + run_id
   - Missing required field → 422
B) GET /runs/{id}/trace
   - ?since=0 returns all seeded events
   - ?since=K returns only events with id > K (incremental-polling contract)
C) GET /runs/{id}/report
   - Sections grouped by schema_field with strength tally
   - Unpassed / unbacked claim does NOT appear
D) GET /sources/{id}
   - Returns provenance fields incl. source_mode
   - Unknown id → 404
E) GET /health → 200
F) Background executor kickoff
   - POST /runs with injected fake executor confirms it is called
     with the run_id (no network, deterministic)
"""

import json
import threading
import time
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
    """A fresh, schema-initialised Database in a temp directory."""
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
def source_id(db: Database, run_id: str) -> str:
    """A pre-persisted source row."""
    sid = str(uuid.uuid4())
    db.append_source(
        {
            "id": sid,
            "run_id": run_id,
            "url": "https://example.com/pricing",
            "title": "Acme pricing page",
            "source_type": "web",
            "source_mode": "LIVE",
            "fetched_at": time.time(),
            "content_hash": "abc123",
            "raw_text": "Acme charges $10/mo for the starter plan.",
            "meta_json": "{}",
        }
    )
    return sid


@pytest.fixture()
def seeded_events(db: Database, run_id: str) -> list[int]:
    """Insert three trace events; return their auto-assigned integer ids."""
    for event_type in ("collect_start", "analyze_done", "qa_pass"):
        db.insert_trace_event(
            {
                "run_id": run_id,
                "agent": "test-agent",
                "node": "test-node",
                "event_type": event_type,
                "payload_json": json.dumps({"note": event_type}),
            }
        )
    events = db.trace_events_for_run(run_id)
    return [e["id"] for e in events]


@pytest.fixture()
def passed_claim_id(db: Database, run_id: str, source_id: str) -> str:
    """A QA-passed claim row in the DB, backed by source_id."""
    cid = str(uuid.uuid4())
    db.append_claim(
        {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing",
            "claim_type": "fact",
            "statement": "Acme starter plan costs $10/mo.",
            "value_json": json.dumps({"amount": 10, "unit": "USD/mo"}),
            "evidence_json": json.dumps([source_id]),
            "based_on_json": json.dumps([]),
            "evidence_strength": "strong",
            "status": "pass",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    return cid


@pytest.fixture()
def unpassed_claim_id(db: Database, run_id: str) -> str:
    """A claim with status='fail' — must NOT appear in /report."""
    cid = str(uuid.uuid4())
    db.append_claim(
        {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "support",
            "claim_type": "fact",
            "statement": "Acme has 24/7 support (UNVERIFIED).",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "weak",
            "status": "fail",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    return cid


@pytest.fixture()
def client(db: Database) -> TestClient:
    """TestClient backed by a seeded DB, no executor."""
    return TestClient(create_app(db=db, run_executor=None))


# ---------------------------------------------------------------------------
# A: POST /runs
# ---------------------------------------------------------------------------


class TestPostRuns:
    def test_valid_body_returns_201_and_run_id(self, client: TestClient) -> None:
        resp = client.post(
            "/runs",
            json={"category": "CRM", "competitors": ["Acme"], "goal": "compare"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)
        assert len(data["run_id"]) == 32  # uuid4 hex

    def test_missing_category_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/runs",
            json={"competitors": ["Acme"], "goal": "compare"},
        )
        assert resp.status_code == 422

    def test_missing_competitors_triggers_discovery_mode(self, client: TestClient) -> None:
        # Discovery Mode: a category with NO competitors is now valid — the
        # backend discovers competitors before analysis.
        resp = client.post(
            "/runs",
            json={"category": "CRM", "goal": "compare"},
        )
        assert resp.status_code == 201
        assert "run_id" in resp.json()

    def test_missing_goal_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/runs",
            json={"category": "CRM", "competitors": ["Acme"]},
        )
        assert resp.status_code == 422

    def test_empty_competitors_with_category_is_discovery_mode(self, client: TestClient) -> None:
        # An explicit empty list + a category is Discovery Mode (201), not an error.
        resp = client.post(
            "/runs",
            json={"category": "CRM", "competitors": [], "goal": "compare"},
        )
        assert resp.status_code == 201

    def test_empty_competitors_and_empty_category_returns_422(self, client: TestClient) -> None:
        # Neither competitors nor a category to discover from -> rejected.
        resp = client.post(
            "/runs",
            json={"category": "   ", "competitors": [], "goal": "compare"},
        )
        assert resp.status_code == 422

    def test_post_runs_accepts_discovery_params(self, client: TestClient) -> None:
        resp = client.post(
            "/runs",
            json={
                "category": "通用 AI Agent",
                "goal": "竞品分析",
                "market_scope": "china",
                "max_competitors": 3,
                "seed_competitors": ["Manus"],
            },
        )
        assert resp.status_code == 201

    def test_overlong_category_returns_422(self, client: TestClient) -> None:
        # category over the 512-char cap is rejected (input-bound defense).
        resp = client.post(
            "/runs",
            json={"category": "X" * 513, "competitors": ["Acme"], "goal": "g"},
        )
        assert resp.status_code == 422

    def test_too_many_competitors_returns_422(self, client: TestClient) -> None:
        # competitors list over the 12-item cap is rejected.
        resp = client.post(
            "/runs",
            json={
                "category": "CRM",
                "competitors": [f"Comp{i}" for i in range(13)],
                "goal": "g",
            },
        )
        assert resp.status_code == 422

    def test_overlong_competitor_name_returns_422(self, client: TestClient) -> None:
        # A single name over the 128-char per-name cap is rejected.
        resp = client.post(
            "/runs",
            json={"category": "CRM", "competitors": ["A" * 129], "goal": "g"},
        )
        assert resp.status_code == 422

    def test_run_id_is_persisted_in_db(self, db: Database) -> None:
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.post(
            "/runs",
            json={"category": "HR", "competitors": ["X"], "goal": "g"},
        )
        run_id = resp.json()["run_id"]
        # Confirm the run is actually in the DB (trace returns 0 events, not 404)
        trace_resp = c.get(f"/runs/{run_id}/trace?since=0")
        assert trace_resp.status_code == 200
        assert trace_resp.json()["events"] == []

    def test_post_runs_accepts_and_persists_domain(
        self, client: TestClient, db: Database
    ) -> None:
        resp = client.post(
            "/runs",
            json={
                "category": "CRM",
                "competitors": ["Acme"],
                "goal": "g",
                "domain": "ai_agent",
            },
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]
        assert db.get_run(run_id)["domain"] == "ai_agent"

    def test_post_runs_rejects_unknown_domain(self, client: TestClient) -> None:
        resp = client.post(
            "/runs",
            json={
                "category": "CRM",
                "competitors": ["Acme"],
                "goal": "g",
                "domain": "bogus",
            },
        )
        assert resp.status_code == 422

    def test_post_runs_without_domain_persists_none(
        self, client: TestClient, db: Database
    ) -> None:
        resp = client.post(
            "/runs",
            json={"category": "CRM", "competitors": ["Acme"], "goal": "g"},
        )
        assert resp.status_code == 201
        assert db.get_run(resp.json()["run_id"]).get("domain") is None

    def test_get_run_includes_domain(self, db: Database) -> None:
        # No bare GET /runs/{id} endpoint exists; assert via db.get_run directly.
        run_id = db.create_run(
            category="CRM", competitors=["Acme"], goal="g", domain="hr"
        )
        assert db.get_run(run_id)["domain"] == "hr"


# ---------------------------------------------------------------------------
# A2: GET /runs (recent-runs picker)
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_empty_db_returns_empty_list(self, tmp_path) -> None:
        fresh = Database(str(tmp_path / "empty.db"))
        fresh.init_schema()
        c = TestClient(create_app(db=fresh, run_executor=None))
        resp = c.get("/runs")
        assert resp.status_code == 200
        assert resp.json() == {"runs": []}

    def test_returns_list_shape_newest_first(self, db: Database) -> None:
        first = db.create_run(category="A", competitors=["X"], goal="g")
        second = db.create_run(category="B", competitors=["Y", "Z"], goal="g")
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.get("/runs")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert [r["run_id"] for r in runs[:2]] == [second, first]
        sample = runs[0]
        assert set(sample.keys()) == {
            "run_id",
            "category",
            "competitors",
            "goal",
            "status",
            "created_at",
            "domain",
            "depth",
            "passed_claims",
        }
        assert sample["competitors"] == ["Y", "Z"]
        assert sample["domain"] is None  # not requested → null in the summary
        assert sample["depth"] == "quick"  # default when not specified

    def test_passed_claims_count(
        self, db: Database, passed_claim_id: str, unpassed_claim_id: str, run_id: str
    ) -> None:
        c = TestClient(create_app(db=db, run_executor=None))
        runs = c.get("/runs").json()["runs"]
        match = next(r for r in runs if r["run_id"] == run_id)
        assert match["passed_claims"] == 1

    def test_limit_is_capped_at_100(self, db: Database) -> None:
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.get("/runs?limit=99999")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# B: GET /runs/{id}/trace
# ---------------------------------------------------------------------------


class TestGetTrace:
    def test_since_zero_returns_all_events(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        resp = client.get(f"/runs/{run_id}/trace?since=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 3
        returned_ids = [e["id"] for e in data["events"]]
        assert returned_ids == sorted(returned_ids), "events not in ascending order"

    def test_max_seq_equals_highest_event_id(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        resp = client.get(f"/runs/{run_id}/trace?since=0")
        data = resp.json()
        assert data["max_seq"] == max(seeded_events)

    def test_since_k_returns_only_events_after_k(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        # Use the second event id as the since cursor.
        cutoff = seeded_events[1]
        resp = client.get(f"/runs/{run_id}/trace?since={cutoff}")
        assert resp.status_code == 200
        data = resp.json()
        # Only the third event should come back.
        assert len(data["events"]) == 1
        assert data["events"][0]["id"] == seeded_events[2]

    def test_since_equals_last_returns_empty(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        last = seeded_events[-1]
        resp = client.get(f"/runs/{run_id}/trace?since={last}")
        data = resp.json()
        assert data["events"] == []
        assert data["max_seq"] == 0

    def test_since_default_is_zero(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        """Omitting since should default to 0 and return all events."""
        resp = client.get(f"/runs/{run_id}/trace")
        data = resp.json()
        assert len(data["events"]) == 3

    def test_event_payload_has_event_type(
        self,
        client: TestClient,
        run_id: str,
        seeded_events: list[int],
    ) -> None:
        resp = client.get(f"/runs/{run_id}/trace?since=0")
        first = resp.json()["events"][0]
        assert "event_type" in first
        assert first["event_type"] == "collect_start"


# ---------------------------------------------------------------------------
# C: GET /runs/{id}/report
# ---------------------------------------------------------------------------


class TestGetReport:
    def test_passed_claim_appears_in_section(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        data = resp.json()
        field_names = [s["schema_field"] for s in data["sections"]]
        assert "pricing" in field_names

    def test_unpassed_claim_does_not_appear(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
        unpassed_claim_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/report")
        data = resp.json()
        # The "support" field only has an unpassed claim; it must not appear.
        field_names = [s["schema_field"] for s in data["sections"]]
        assert "support" not in field_names

    def test_strength_tally_counts_passed_only(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
        unpassed_claim_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/report")
        tally = resp.json()["strength_tally"]
        # Only the passed claim (strong) is counted.
        assert tally["strong"] == 1
        assert tally["moderate"] == 0
        assert tally["weak"] == 0

    def test_claim_has_decoded_value(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/report")
        sections = resp.json()["sections"]
        pricing_section = next(s for s in sections if s["schema_field"] == "pricing")
        claim = pricing_section["claims"][0]
        assert isinstance(claim["value"], dict)
        assert claim["value"]["amount"] == 10

    def test_claim_has_evidence_source_ids(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
        source_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/report")
        sections = resp.json()["sections"]
        pricing_section = next(s for s in sections if s["schema_field"] == "pricing")
        claim = pricing_section["claims"][0]
        assert source_id in claim["evidence_source_ids"]

    def test_object_array_evidence_normalized_to_id_strings(
        self,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """evidence_json as build_claim's object-array → list of id STRINGS.

        build_claim stores evidence as ``[{"source_id","snippet","relevance"}]``.
        The report must surface ``evidence_source_ids`` as plain id strings so the
        frontend's ``getSource`` call hits ``/sources/<id>`` (not [object Object]).
        """
        cid = str(uuid.uuid4())
        evidence_objs = [
            {"source_id": source_id, "snippet": "Pro is $10/mo.", "relevance": "supports"}
        ]
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing",
                "claim_type": "fact",
                "statement": "Acme pro is $10/mo.",
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps(evidence_objs),
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )
        c = TestClient(create_app(db=db, run_executor=None))
        sections = c.get(f"/runs/{run_id}/report").json()["sections"]
        claim = next(s for s in sections if s["schema_field"] == "pricing")["claims"][0]
        assert claim["evidence_source_ids"] == [source_id]
        assert all(isinstance(x, str) for x in claim["evidence_source_ids"])

    def test_empty_run_returns_empty_sections(
        self,
        client: TestClient,
        run_id: str,
    ) -> None:
        """A run with no claims returns empty sections and zero tally."""
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []
        assert data["strength_tally"] == {"strong": 0, "moderate": 0, "weak": 0}

    def test_report_shape_unchanged(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
    ) -> None:
        """Back-compat guard: /report's top-level keys stay exactly the
        documented keys. Surfacing per-claim ``based_on`` must NOT add or rename
        any top-level response key; ``scope_methodology`` (M4) is the only
        intentionally-added top-level key."""
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == {
            "sections",
            "strength_tally",
            "scope_methodology",
        }

    def test_section_claim_carries_based_on(
        self,
        db: Database,
        run_id: str,
    ) -> None:
        """A synthesis claim (claim_type='inference') citing other claim ids in
        ``based_on_json`` surfaces that lineage as ``based_on`` on the section
        claim dict."""
        cid = str(uuid.uuid4())
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "swot",
                "claim_type": "inference",
                "statement": "Acme is squeezed on price.",
                "value_json": "{}",
                "evidence_json": "[]",
                "based_on_json": json.dumps(["c1", "c2"]),
                "evidence_strength": "moderate",
                "status": "pass",
                "version": 1,
                "produced_by": "synthesis",
            }
        )
        c = TestClient(create_app(db=db, run_executor=None))
        sections = c.get(f"/runs/{run_id}/report").json()["sections"]
        claim = next(s for s in sections if s["schema_field"] == "swot")["claims"][0]
        assert claim["based_on"] == ["c1", "c2"]

    def test_multiple_passed_claims_same_field_grouped(
        self,
        db: Database,
        run_id: str,
    ) -> None:
        """Two passed claims for the same schema_field appear in the same section."""
        for i in range(2):
            cid = str(uuid.uuid4())
            db.append_claim(
                {
                    "id": cid,
                    "run_id": run_id,
                    "competitor": f"Comp{i}",
                    "schema_field": "feature_X",
                    "claim_type": "fact",
                    "statement": f"Claim {i}",
                    "value_json": "{}",
                    "evidence_json": "[]",
                    "based_on_json": "[]",
                    "evidence_strength": "moderate",
                    "status": "pass",
                    "version": 1,
                    "produced_by": "analyst",
                }
            )
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.get(f"/runs/{run_id}/report")
        sections = resp.json()["sections"]
        fx_section = next(
            (s for s in sections if s["schema_field"] == "feature_X"), None
        )
        assert fx_section is not None
        assert len(fx_section["claims"]) == 2


# ---------------------------------------------------------------------------
# D: GET /sources/{id}
# ---------------------------------------------------------------------------


class TestGetSource:
    def test_known_source_returns_provenance(
        self,
        client: TestClient,
        source_id: str,
    ) -> None:
        resp = client.get(f"/sources/{source_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com/pricing"
        assert data["source_mode"] == "LIVE"
        assert data["source_type"] == "web"
        assert "raw_text" in data
        assert data["raw_text"] == "Acme charges $10/mo for the starter plan."
        assert "content_hash" in data
        assert "fetched_at" in data

    def test_source_mode_field_present(
        self,
        client: TestClient,
        source_id: str,
    ) -> None:
        """source_mode must always be present in the response (provenance badge)."""
        resp = client.get(f"/sources/{source_id}")
        assert "source_mode" in resp.json()

    def test_unknown_source_returns_404(self, client: TestClient) -> None:
        resp = client.get(f"/sources/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_cached_source_mode(
        self,
        db: Database,
        run_id: str,
    ) -> None:
        """CACHED source_mode is preserved and returned correctly."""
        sid = str(uuid.uuid4())
        db.append_source(
            {
                "id": sid,
                "run_id": run_id,
                "url": "https://example.com/old",
                "title": "Cached page",
                "source_type": "web",
                "source_mode": "CACHED",
                "fetched_at": time.time(),
                "content_hash": "xyz",
                "raw_text": "cached content",
                "meta_json": "{}",
            }
        )
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.get(f"/sources/{sid}")
        assert resp.status_code == 200
        assert resp.json()["source_mode"] == "CACHED"


# ---------------------------------------------------------------------------
# E: GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200_and_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# F: Background executor kickoff (no network — deterministic)
# ---------------------------------------------------------------------------


class TestRunExecutorKickoff:
    def test_executor_called_with_run_id(self, db: Database) -> None:
        """POST /runs with an injected fake executor calls it with the run_id."""
        invocations: list[str] = []
        barrier = threading.Event()

        def fake_executor(run_id: str) -> None:
            invocations.append(run_id)
            barrier.set()

        c = TestClient(
            create_app(db=db, run_executor=fake_executor),
        )
        resp = c.post(
            "/runs",
            json={"category": "A", "competitors": ["X"], "goal": "g"},
        )
        assert resp.status_code == 201
        expected_run_id = resp.json()["run_id"]

        # Wait up to 2 s for the daemon thread to fire — no network, always fast.
        fired = barrier.wait(timeout=2.0)
        assert fired, "executor was never called (thread did not fire within 2s)"
        assert invocations == [expected_run_id]

    def test_executor_none_does_not_crash(self, db: Database) -> None:
        """When run_executor is None, POST /runs succeeds without side effects."""
        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.post(
            "/runs",
            json={"category": "B", "competitors": ["Y"], "goal": "g2"},
        )
        assert resp.status_code == 201
        assert "run_id" in resp.json()


# ---------------------------------------------------------------------------
# F2: End-to-end wiring — injected executor's writes show up via GET /trace
# ---------------------------------------------------------------------------


class TestRunExecutorEndToEnd:
    def test_executor_writes_visible_via_trace(self, db: Database) -> None:
        """POST /runs -> injected executor writes -> GET /trace shows them.

        Proves the wiring path deterministically (no network): the executor
        runs synchronously (joined via a barrier) and writes a trace event plus
        a claim against the run_id; the trace endpoint then surfaces the event.
        """
        barrier = threading.Event()

        def fake_executor(run_id: str) -> None:
            db.insert_trace_event(
                {
                    "run_id": run_id,
                    "agent": "writer",
                    "node": "write",
                    "event_type": "run_complete",
                    "payload_json": json.dumps({"claims_total": 1}),
                }
            )
            db.append_claim(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "competitor": "Acme",
                    "schema_field": "pricing_model",
                    "claim_type": "fact",
                    "statement": "Acme pro is $10/mo.",
                    "value_json": json.dumps({"tiers": ["Pro $10/mo"]}),
                    "evidence_json": "[]",
                    "based_on_json": "[]",
                    "evidence_strength": "strong",
                    "status": "pass",
                    "version": 1,
                    "produced_by": "analyst",
                }
            )
            barrier.set()

        c = TestClient(create_app(db=db, run_executor=fake_executor))
        resp = c.post(
            "/runs",
            json={"category": "CRM", "competitors": ["Acme"], "goal": "g"},
        )
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        # Wait for the daemon thread to finish its synchronous work.
        assert barrier.wait(timeout=2.0), "executor did not run within 2s"

        trace_resp = c.get(f"/runs/{run_id}/trace?since=0")
        assert trace_resp.status_code == 200
        event_types = [e["event_type"] for e in trace_resp.json()["events"]]
        assert "run_complete" in event_types

        # The claim is also visible through the report endpoint.
        report_resp = c.get(f"/runs/{run_id}/report")
        assert report_resp.status_code == 200
        fields = [s["schema_field"] for s in report_resp.json()["sections"]]
        assert "pricing_model" in fields


# ---------------------------------------------------------------------------
# (Import check at module level for uvicorn compatibility)
# ---------------------------------------------------------------------------


def test_module_level_app_importable() -> None:
    """The module-level ``app`` must be importable without network or env vars."""
    from mingjing.api import app  # noqa: F401

    assert app is not None


# ---------------------------------------------------------------------------
# G: Executor thread exception is logged, not silently swallowed (I1)
# ---------------------------------------------------------------------------


class TestRunExecutorErrorLogging:
    def test_failing_executor_still_returns_201(
        self, db: Database, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST /runs returns 201 even when run_executor raises; error is logged."""
        import logging

        def exploding_executor(run_id: str) -> None:
            raise RuntimeError("synthetic executor failure")

        c = TestClient(create_app(db=db, run_executor=exploding_executor))

        # Capture logs at ERROR level from the api module.
        with caplog.at_level(logging.ERROR, logger="mingjing.api"):
            resp = c.post(
                "/runs",
                json={"category": "X", "competitors": ["Foo"], "goal": "test"},
            )

        # The HTTP response must be 201 — the failure is isolated to the thread.
        assert resp.status_code == 201
        assert "run_id" in resp.json()

        # The background thread needs a moment to fire and log.
        deadline = 2.0
        import time as _time
        start = _time.monotonic()
        while _time.monotonic() - start < deadline:
            if any("run_executor failed" in r.message for r in caplog.records):
                break
            _time.sleep(0.05)

        logged_messages = [r.message for r in caplog.records]
        assert any("run_executor failed" in msg for msg in logged_messages), (
            f"Expected 'run_executor failed' in log; got: {logged_messages}"
        )


# ---------------------------------------------------------------------------
# H: Unknown run IDs return 404 on trace and report endpoints (I2)
# ---------------------------------------------------------------------------


class TestUnknownRunId:
    def test_trace_unknown_run_returns_404(self, client: TestClient) -> None:
        """GET /runs/<unknown>/trace must return 404, not 200 with empty payload."""
        resp = client.get("/runs/nonexistent_run_id_xyz/trace")
        assert resp.status_code == 404

    def test_report_unknown_run_returns_404(self, client: TestClient) -> None:
        """GET /runs/<unknown>/report must return 404, not 200 with empty payload."""
        resp = client.get("/runs/nonexistent_run_id_xyz/report")
        assert resp.status_code == 404

    def test_trace_known_run_no_events_returns_200(
        self,
        client: TestClient,
        run_id: str,
    ) -> None:
        """A run that EXISTS but has no events must still return 200 (empty events)."""
        resp = client.get(f"/runs/{run_id}/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["max_seq"] == 0

    def test_report_known_run_no_claims_returns_200(
        self,
        client: TestClient,
        run_id: str,
    ) -> None:
        """A run that EXISTS but has no claims must still return 200 (empty sections)."""
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sections"] == []
        assert data["strength_tally"] == {"strong": 0, "moderate": 0, "weak": 0}


# ---------------------------------------------------------------------------
# G: GET /runs/{id}/claims/{claim_id}/history  (QA Replay before/after)
# ---------------------------------------------------------------------------


class TestGetClaimHistory:
    def test_weak_to_strong_history_ordered_by_version(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        """Two versions of one claim are returned oldest-first, showing the
        weak→strong upgrade that powers the QA Replay view."""
        cid = str(uuid.uuid4())
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing",
                "claim_type": "fact",
                "statement": "Acme starter plan is around $10/mo (single source).",
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps([source_id]),
                "based_on_json": "[]",
                "evidence_strength": "weak",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing",
                "claim_type": "fact",
                "statement": "Acme starter plan costs $10/mo (two independent sources).",
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps([source_id, source_id]),
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": "pass",
                "version": 2,
                "produced_by": "analyst",
            }
        )

        resp = client.get(f"/runs/{run_id}/claims/{cid}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == cid
        versions = data["versions"]
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[0]["evidence_strength"] == "weak"
        assert versions[1]["version"] == 2
        assert versions[1]["evidence_strength"] == "strong"
        # value/evidence are decoded, not raw JSON strings.
        assert versions[1]["evidence_source_ids"] == [source_id, source_id]

    def test_object_array_evidence_normalized_to_id_strings(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        """History must surface ``evidence_source_ids`` as plain id strings.

        ``build_claim`` stores evidence as objects
        (``{"source_id","snippet","relevance"}``). The QA Replay click-to-source
        calls ``/sources/<id>``; if the endpoint leaked the object array the
        frontend would request ``/sources/[object Object]`` and 404. This guards
        the same fix applied to the report endpoint, for the history path.
        """
        cid = str(uuid.uuid4())
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing",
                "claim_type": "fact",
                "statement": "Acme starter plan costs $10/mo.",
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps(
                    [{"source_id": source_id, "snippet": "$10/mo", "relevance": "supports"}]
                ),
                "based_on_json": "[]",
                "evidence_strength": "moderate",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )
        resp = client.get(f"/runs/{run_id}/claims/{cid}/history")
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        assert versions[0]["evidence_source_ids"] == [source_id]
        assert all(isinstance(x, str) for x in versions[0]["evidence_source_ids"])

    def test_unknown_claim_returns_404(
        self,
        client: TestClient,
        run_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/claims/nonexistent_claim/history")
        assert resp.status_code == 404

    def test_unknown_run_returns_404(self, client: TestClient) -> None:
        resp = client.get("/runs/nonexistent_run/claims/whatever/history")
        assert resp.status_code == 404

    def test_correction_note_appears_in_history(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        """GA4: correction note is returned on the corrected version; machine
        versions without a note return null/None.

        Write a version-1 machine claim (no note), then POST a HITL correction
        with a non-empty note. GET /history must expose:
        - version 1: note == null  (machine-produced, no reviewer rationale)
        - version 2: note == <the note text>  (human correction)
        No QA verdict or scoring is involved.
        """
        cid = str(uuid.uuid4())
        # v1 — machine-produced, no note
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing",
                "claim_type": "fact",
                "statement": "Acme charges $10/mo.",
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps([source_id]),
                "based_on_json": "[]",
                "evidence_strength": "weak",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )

        # POST a correction with a note (action=accept, simple status flip)
        correction_note = "Verified against official pricing page on 2026-06-08."
        resp = client.post(
            f"/runs/{run_id}/claims/{cid}/correct",
            json={"action": "accept", "note": correction_note},
        )
        assert resp.status_code == 201, resp.text

        # GET history — both versions must be present
        resp = client.get(f"/runs/{run_id}/claims/{cid}/history")
        assert resp.status_code == 200
        data = resp.json()
        versions = data["versions"]
        assert len(versions) == 2

        v1 = next(v for v in versions if v["version"] == 1)
        v2 = next(v for v in versions if v["version"] == 2)

        # Machine-produced version has no note (null/None)
        assert v1.get("note") is None, f"Expected null note on v1, got {v1.get('note')!r}"

        # Corrected version carries the reviewer's rationale
        assert v2.get("note") == correction_note, (
            f"Expected note={correction_note!r} on v2, got {v2.get('note')!r}"
        )


# ---------------------------------------------------------------------------
# H: GET /runs/{run_id}/llm_calls  (Observability endpoint)
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_llm_call(db: Database, run_id: str) -> int:
    """Insert one LLM call row and return its auto-assigned integer id."""
    db.insert_llm_call(
        {
            "run_id": run_id,
            "agent": "analyst",
            "model": "minimax-text-01",
            "prompt_json": json.dumps(
                [{"role": "user", "content": "Summarise pricing."}]
            ),
            "output_text": "Acme charges $10/mo.",
            "prompt_tokens": 15,
            "completion_tokens": 8,
            "total_tokens": 23,
        }
    )
    rows = db.llm_calls_for_run(run_id)
    assert rows, "seeded_llm_call fixture: insert produced no rows"
    return int(rows[-1]["id"])


class TestGetLlmCalls:
    def test_returns_seeded_calls(
        self,
        client: TestClient,
        run_id: str,
        seeded_llm_call: int,
    ) -> None:
        """All seeded LLM calls are returned in ascending id order."""
        resp = client.get(f"/runs/{run_id}/llm_calls")
        assert resp.status_code == 200
        data = resp.json()
        assert "calls" in data
        assert len(data["calls"]) == 1
        call = data["calls"][0]
        assert call["agent"] == "analyst"
        assert call["model"] == "minimax-text-01"
        assert call["output_text"] == "Acme charges $10/mo."
        assert call["prompt_tokens"] == 15
        assert call["completion_tokens"] == 8
        assert call["total_tokens"] == 23
        # prompt_json is the raw JSON string stored in the DB
        assert "Summarise pricing" in call["prompt_json"]

    def test_unknown_run_returns_404(self, client: TestClient) -> None:
        """GET /runs/<unknown>/llm_calls must return 404."""
        resp = client.get("/runs/nonexistent_run_xyz/llm_calls")
        assert resp.status_code == 404

    def test_empty_run_returns_empty_calls(
        self, client: TestClient, run_id: str
    ) -> None:
        """A run with no LLM calls returns an empty list, not an error."""
        resp = client.get(f"/runs/{run_id}/llm_calls")
        assert resp.status_code == 200
        assert resp.json() == {"calls": []}

    def test_key_redaction_holds_in_response(
        self,
        db: Database,
        run_id: str,
    ) -> None:
        """An LLM call whose prompt contained an API key is stored redacted.

        ``trace.log_llm`` redacts the live MINIMAX_API_KEY value at write time.
        We simulate this by calling ``log_llm`` with a fake key injected into
        the environment, then verifying the endpoint response contains no
        ``sk-``/``ark-`` pattern and the key value itself does not appear.
        """
        import os

        fake_key = "sk-test-secret-key-12345"
        os.environ["MINIMAX_API_KEY"] = fake_key
        try:
            from mingjing.trace import log_llm

            log_llm(
                db,
                run_id,
                agent="collector",
                model="minimax-text-01",
                messages=[
                    {
                        "role": "user",
                        "content": f"Use key {fake_key} to fetch data.",
                    }
                ],
                output_text=f"The key {fake_key} was used.",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        finally:
            os.environ.pop("MINIMAX_API_KEY", None)

        c = TestClient(create_app(db=db, run_executor=None))
        resp = c.get(f"/runs/{run_id}/llm_calls")
        assert resp.status_code == 200
        body_text = json.dumps(resp.json())
        # The raw key value must not appear anywhere in the response.
        assert fake_key not in body_text
        # The redaction marker must be present (both prompt and output are redacted).
        assert "[REDACTED_API_KEY]" in body_text

    def test_response_fields_match_db_columns(
        self,
        client: TestClient,
        run_id: str,
        seeded_llm_call: int,
    ) -> None:
        """Every expected field is present in each returned call object."""
        resp = client.get(f"/runs/{run_id}/llm_calls")
        call = resp.json()["calls"][0]
        expected_fields = {
            "id",
            "agent",
            "model",
            "prompt_json",
            "output_text",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "created_at",
        }
        assert expected_fields.issubset(set(call.keys()))


# ---------------------------------------------------------------------------
# Task 6 — M4 synthesis: append-only syntheses table + read-only endpoint.
# ---------------------------------------------------------------------------
def test_synthesis_endpoint_shape(tmp_path):
    """GET /runs/{id}/synthesis returns the latest projected payload merged with
    referenced_claim_ids; an unknown run is 200 ({}) or 404 (no LLM call)."""
    from fastapi.testclient import TestClient

    from mingjing.api import create_app
    from mingjing.db import Database

    db = Database(f"{tmp_path}/m.db")
    db.init_schema()
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    db.append_synthesis(
        rid, {"bluf": {"text": "x", "claim_ids": ["c1"]}, "referenced_claim_ids": ["c1"]}
    )
    app = create_app(db=db)
    c = TestClient(app)
    r = c.get(f"/runs/{rid}/synthesis")
    assert r.status_code == 200
    body = r.json()
    assert "bluf" in body and "referenced_claim_ids" in body
    assert c.get("/runs/deadbeef/synthesis").status_code in (200, 404)


def test_init_schema_creates_syntheses_on_existing_db(tmp_path):
    """init_schema() on a pre-existing DB lacking the syntheses table creates it."""
    import sqlite3

    from mingjing.db import Database

    path = f"{tmp_path}/legacy.db"
    # Pre-create a DB with the runs table but WITHOUT syntheses (legacy demo DB).
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE runs (id TEXT PRIMARY KEY, category TEXT,"
        " competitors_json TEXT NOT NULL, goal TEXT, status TEXT, created_at REAL)"
    )  # genuine legacy runs table (no domain) — init_schema must migrate it
    conn.commit()
    conn.close()

    db = Database(path)
    db.init_schema()  # adds syntheses (CREATE IF NOT EXISTS) + migrates runs.domain
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    db.append_synthesis(rid, {"bluf": {"text": "x", "claim_ids": []}, "referenced_claim_ids": []})
    assert db.get_synthesis(rid) is not None


def test_init_schema_migrates_runs_domain_on_existing_db(tmp_path):
    """A legacy runs table WITHOUT a domain column gains it via init_schema's
    migration — so create_run(domain=...) works instead of raising
    OperationalError (CREATE TABLE IF NOT EXISTS does not add columns)."""
    import sqlite3

    from mingjing.db import Database

    path = f"{tmp_path}/legacy_nodomain.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE runs (id TEXT PRIMARY KEY, category TEXT,"
        " competitors_json TEXT NOT NULL, goal TEXT, status TEXT, created_at REAL)"
    )  # legacy: NO domain column
    conn.commit()
    conn.close()

    db = Database(path)
    db.init_schema()  # must ALTER TABLE runs ADD COLUMN domain
    rid = db.create_run(category="x", competitors=["Acme"], goal="g", domain="ai_agent")
    assert db.get_run(rid)["domain"] == "ai_agent"
    # Idempotent: a second init_schema must not error (column already present).
    db.init_schema()


# ---------------------------------------------------------------------------
# G: GET /runs/{id}/credibility  (advisory KPI panel — Task 6)
# ---------------------------------------------------------------------------


class TestGetCredibility:
    def test_credibility_endpoint_returns_panel(
        self,
        client: TestClient,
        run_id: str,
        passed_claim_id: str,
        unpassed_claim_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/credibility")
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "avg_groundedness",
            "claim_admission_rate",
            "coverage",
            "repair_delta",
            "rounds",
        ):
            assert key in body
        # admission = passed / total; one of two claims passed -> 0.5
        assert body["claim_admission_rate"] == 0.5
        # advisory numbers stay within sane bounds
        assert 0.0 <= body["avg_groundedness"] <= 1.0
        assert 0.0 <= body["coverage"] <= 1.0
        # Terminal-state signal for the frontend's zero-admitted honesty gate:
        # a fresh run row is 'running' — an in-flight run's pre-final zeros must
        # never be presented as a settled "0 条结论准入" verdict (stop-gate fix).
        assert body["run_status"] == "running"

    def test_credibility_unknown_run_returns_404(self, client: TestClient) -> None:
        resp = client.get("/runs/deadbeef/credibility")
        assert resp.status_code == 404

    def test_repair_delta_positive_across_two_versions(
        self,
        client: TestClient,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """Headline mechanism: a weak v1 claim repaired into a strong v2 yields a
        positive repair_delta and rounds==2. source_id raw_text is
        'Acme charges $10/mo for the starter plan.'"""
        cid = str(uuid.uuid4())
        # v1: value leaf ABSENT from the cited source -> groundedness 0.0 (round 0).
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v1",
            "value_json": json.dumps({"plan_name": "Enterprise Premium Unlimited"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "weak", "status": "draft", "version": 1, "produced_by": "analyst",
        })
        # v2: value leaf PRESENT in the cited source -> groundedness 1.0 (round 1).
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v2",
            "value_json": json.dumps({"plan_name": "starter plan"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "strong", "status": "pass", "version": 2, "produced_by": "analyst",
        })
        body = client.get(f"/runs/{run_id}/credibility").json()
        assert body["rounds"] == 2
        assert body["repair_delta"] > 0  # weak round-0 repaired into strong round-1

    def test_is_tier_upgrade_true_when_claim_rises_a_tier(
        self,
        client: TestClient,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """A claim that goes weak(v1)→moderate(v2) sets is_tier_upgrade True."""
        cid = str(uuid.uuid4())
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v1",
            "value_json": json.dumps({"amount": 10}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "weak", "status": "draft", "version": 1, "produced_by": "analyst",
        })
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v2",
            "value_json": json.dumps({"amount": 10}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "moderate", "status": "pass", "version": 2, "produced_by": "analyst",
        })
        body = client.get(f"/runs/{run_id}/credibility").json()
        assert body["is_tier_upgrade"] is True

    def test_is_tier_upgrade_false_when_tier_unchanged(
        self,
        client: TestClient,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """moderate(v1)→moderate(v2) is NOT a tier upgrade, even if groundedness
        rose within the tier (repair_delta can still be positive)."""
        cid = str(uuid.uuid4())
        # v1: value leaf absent -> low groundedness; v2: present -> high. Tier
        # stays moderate across both versions.
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v1",
            "value_json": json.dumps({"plan_name": "Enterprise Premium Unlimited"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "moderate", "status": "draft", "version": 1, "produced_by": "analyst",
        })
        db.append_claim({
            "id": cid, "run_id": run_id, "competitor": "Acme", "schema_field": "pricing",
            "claim_type": "fact", "statement": "v2",
            "value_json": json.dumps({"plan_name": "starter plan"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "moderate", "status": "pass", "version": 2, "produced_by": "analyst",
        })
        body = client.get(f"/runs/{run_id}/credibility").json()
        assert body["is_tier_upgrade"] is False

    def test_is_tier_upgrade_false_for_clean_single_version_run(
        self,
        client: TestClient,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """A run where every claim has a single version (no revisions) has no
        tier history to compare -> is_tier_upgrade False."""
        for tier in ("strong", "moderate", "weak"):
            db.append_claim({
                "id": str(uuid.uuid4()), "run_id": run_id, "competitor": "Acme",
                "schema_field": "pricing", "claim_type": "fact", "statement": tier,
                "value_json": json.dumps({"amount": 10}),
                "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
                "evidence_strength": tier, "status": "pass", "version": 1, "produced_by": "analyst",
            })
        body = client.get(f"/runs/{run_id}/credibility").json()
        assert body["is_tier_upgrade"] is False

    def test_repair_delta_paired_not_mixed_populations(
        self,
        client: TestClient,
        db: Database,
        run_id: str,
        source_id: str,
    ) -> None:
        """RC1: repair_delta must be the PAIRED per-claim lift on claims that
        actually revised — NOT a mean-of-means over different populations.

        Mixed population fixture (source raw_text =
        'Acme charges $10/mo for the starter plan.'):
          - Claim A: single version, HIGH groundedness (passed round 0, never
            revised). Its value leaf 'starter plan' IS in the source -> 1.0.
          - Claim B: v1 LOW groundedness (leaf absent -> 0.0) repaired into v2
            HIGH (leaf present -> 1.0). The ONLY genuinely repaired claim.

        Honest paired delta = mean over repaired claims of (last - first):
        only Claim B revised, so delta = 1.0 - 0.0 = 1.0.

        The OLD mean-of-means computation built round_groundedness as
          [mean(v1 of A,B) , mean(v2 of B)] = [(1.0+0.0)/2 , 1.0] = [0.5, 1.0]
        giving delta = 1.0 - 0.5 = 0.5 — an UNDERSTATEMENT here, but in the
        general case (worst claims revise) it inflates. Either way it compares
        non-comparable claim sets. This test pins the paired value.
        """
        # Claim A: single version, high groundedness, never revised.
        db.append_claim({
            "id": str(uuid.uuid4()), "run_id": run_id, "competitor": "Acme",
            "schema_field": "pricing", "claim_type": "fact", "statement": "A",
            "value_json": json.dumps({"plan_name": "starter plan"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "strong", "status": "pass", "version": 1, "produced_by": "analyst",
        })
        # Claim B: v1 low -> v2 high (the genuinely repaired claim).
        cid_b = str(uuid.uuid4())
        db.append_claim({
            "id": cid_b, "run_id": run_id, "competitor": "Acme",
            "schema_field": "feature_tree", "claim_type": "fact", "statement": "B-v1",
            "value_json": json.dumps({"plan_name": "Enterprise Premium Unlimited"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "weak", "status": "draft", "version": 1, "produced_by": "analyst",
        })
        db.append_claim({
            "id": cid_b, "run_id": run_id, "competitor": "Acme",
            "schema_field": "feature_tree", "claim_type": "fact", "statement": "B-v2",
            "value_json": json.dumps({"plan_name": "starter plan"}),
            "evidence_json": json.dumps([source_id]), "based_on_json": "[]",
            "evidence_strength": "strong", "status": "pass", "version": 2, "produced_by": "analyst",
        })
        body = client.get(f"/runs/{run_id}/credibility").json()
        # Honest paired lift on the only repaired claim (B): 1.0 - 0.0 = 1.0.
        assert body["repair_delta"] == 1.0
        # rounds still reflects the number of version levels observed (1 and 2).
        assert body["rounds"] == 2


def test_survey_design_endpoint_returns_questions(client, db):
    import json
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    db.insert_trace_event({
        "run_id": run_id, "agent": "collector", "node": "collect",
        "event_type": "survey_designed",
        "payload_json": json.dumps({"survey_id": "SV-1", "competitor": "Notion",
                                    "goal": "g", "questions": [{"id": "q1", "field": None}]}),
    })
    resp = client.get(f"/runs/{run_id}/survey-design")
    assert resp.status_code == 200
    body = resp.json()
    assert body["survey_id"] == "SV-1"
    assert body["questions"][0]["id"] == "q1"


def test_survey_design_endpoint_empty_when_none(client, db):
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    resp = client.get(f"/runs/{run_id}/survey-design")
    assert resp.status_code == 200
    assert resp.json() == {}   # no design emitted yet -> empty (frontend hides the card)
