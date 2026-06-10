"""Tests for metrics.py (pure-function layer) and GET /runs/{id}/metrics.

Layer 1 — Pure function tests: build plain dicts/lists in-memory and assert
          each computed metric value with no DB or HTTP involved.
Layer 2 — Endpoint tests: seed a real DB via fixtures (same pattern as
          test_api.py) and exercise the HTTP endpoint via TestClient.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database
from mingjing.metrics import (
    ACCURACY_CAVEAT,
    HUMAN_BASELINE_HOURS_HIGH,
    HUMAN_BASELINE_HOURS_LOW,
    compute_metrics,
)
from mingjing.schemas import FIELD_SCHEMAS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _claim(
    *,
    id: str | None = None,
    status: str = "pass",
    schema_field: str = "pricing_model",
    evidence_json: str = "[]",
    evidence_strength: str = "strong",
    produced_by: str | None = "analyst",
) -> dict:
    return {
        "id": id or str(uuid.uuid4()),
        "run_id": "run-1",
        "competitor": "Acme",
        "schema_field": schema_field,
        "claim_type": "fact",
        "statement": "some statement",
        "value_json": "{}",
        "evidence_json": evidence_json,
        "based_on_json": "[]",
        "evidence_strength": evidence_strength,
        "status": status,
        "version": 1,
        "produced_by": produced_by,
    }


def _llm_call(total_tokens: int | None = 100) -> dict:
    return {
        "id": 1,
        "run_id": "run-1",
        "agent": "analyst",
        "model": "test-model",
        "prompt_json": "[]",
        "output_text": "ok",
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "total_tokens": total_tokens,
        "created_at": time.time(),
    }


def _source(run_id: str = "run-1") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "run_id": run_id,
        "url": "https://example.com",
        "source_type": "web",
        "source_mode": "LIVE",
        "created_at": time.time(),
    }


def _trace_event(created_at: float) -> dict:
    return {
        "id": 1,
        "run_id": "run-1",
        "agent": "collector",
        "node": "n",
        "event_type": "start",
        "payload_json": "{}",
        "created_at": created_at,
    }


_EMPTY_INTAKE: dict = {
    "id": "run-1",
    "category": "CRM",
    "competitors": ["Acme"],
    "goal": "compare",
    "status": "running",
    "created_at": time.time(),
}


# ---------------------------------------------------------------------------
# Layer 1 — Pure-function tests (no DB, no HTTP)
# ---------------------------------------------------------------------------


class TestComputeMetricsEmpty:
    """Guard divide-by-zero on all-empty inputs."""

    def test_all_zeros_on_empty_claims(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["coverage"] == 0.0
        assert result["citation_rate"] == 0.0
        assert result["strong_rate"] == 0.0
        assert result["human_correction_rate"] == 0.0

    def test_efficiency_zero_elapsed_on_fewer_than_two_events(self) -> None:
        result = compute_metrics([], [], [], [_trace_event(1000.0)], _EMPTY_INTAKE)
        assert result["efficiency"]["elapsed_s"] == 0.0

    def test_efficiency_zero_tokens_on_no_llm_calls(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["efficiency"]["total_tokens"] == 0

    def test_accuracy_caveat_present(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["accuracy_caveat"] == ACCURACY_CAVEAT


class TestCoverageMetric:
    """coverage = distinct passed schema_fields / len(FIELD_SCHEMAS)."""

    def test_zero_when_no_passed_claims(self) -> None:
        c = _claim(status="reject")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["coverage"] == 0.0

    def test_one_field_over_five_schemas(self) -> None:
        # FIELD_SCHEMAS has 5 keys; one passed claim on one field → 1/5
        c = _claim(status="pass", schema_field="pricing_model")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        expected = round(1 / len(FIELD_SCHEMAS), 4)
        assert result["coverage"] == expected

    def test_two_claims_same_field_count_once(self) -> None:
        c1 = _claim(status="pass", schema_field="pricing_model")
        c2 = _claim(status="pass", schema_field="pricing_model")
        result = compute_metrics([c1, c2], [], [], [], _EMPTY_INTAKE)
        # Still only 1 distinct field
        expected = round(1 / len(FIELD_SCHEMAS), 4)
        assert result["coverage"] == expected

    def test_two_distinct_fields(self) -> None:
        c1 = _claim(status="pass", schema_field="pricing_model")
        c2 = _claim(status="pass", schema_field="user_sentiment")
        result = compute_metrics([c1, c2], [], [], [], _EMPTY_INTAKE)
        expected = round(2 / len(FIELD_SCHEMAS), 4)
        assert result["coverage"] == expected

    def test_full_coverage_all_five_fields(self) -> None:
        claims = [
            _claim(status="pass", schema_field=f) for f in FIELD_SCHEMAS.keys()
        ]
        result = compute_metrics(claims, [], [], [], _EMPTY_INTAKE)
        assert result["coverage"] == 1.0

    def test_intake_fields_override_schema(self) -> None:
        """If intake has a 'fields' key, required_fields uses its length."""
        intake = {**_EMPTY_INTAKE, "fields": ["a", "b", "c"]}
        c = _claim(status="pass", schema_field="a")
        result = compute_metrics([c], [], [], [], intake)
        expected = round(1 / 3, 4)
        assert result["coverage"] == expected


class TestCitationRate:
    """citation_rate = cited_passed / total_passed; 0.0 when no passed claims."""

    def test_zero_when_no_passed_claims(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["citation_rate"] == 0.0

    def test_all_cited(self) -> None:
        src_id = str(uuid.uuid4())
        c = _claim(evidence_json=json.dumps([src_id]))
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["citation_rate"] == 1.0

    def test_none_cited(self) -> None:
        c = _claim(evidence_json="[]")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["citation_rate"] == 0.0

    def test_one_cited_one_not(self) -> None:
        src_id = str(uuid.uuid4())
        c1 = _claim(evidence_json=json.dumps([src_id]))
        c2 = _claim(evidence_json="[]")
        result = compute_metrics([c1, c2], [], [], [], _EMPTY_INTAKE)
        assert result["citation_rate"] == 0.5

    def test_object_array_evidence_counted(self) -> None:
        """build_claim stores evidence as objects; citation_rate must count them."""
        src_id = str(uuid.uuid4())
        evidence_obj = [{"source_id": src_id, "snippet": "text", "relevance": "supports"}]
        c = _claim(evidence_json=json.dumps(evidence_obj))
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["citation_rate"] == 1.0

    def test_unpassed_claims_not_counted_in_denominator(self) -> None:
        src_id = str(uuid.uuid4())
        passed = _claim(status="pass", evidence_json=json.dumps([src_id]))
        rejected = _claim(status="reject", evidence_json="[]")
        result = compute_metrics([passed, rejected], [], [], [], _EMPTY_INTAKE)
        # denominator = 1 (only passed), numerator = 1 (cited)
        assert result["citation_rate"] == 1.0


class TestStrongRate:
    """strong_rate = strong_cited_passed / cited_passed; 0.0 when no cited claims."""

    def test_zero_when_no_cited_claims(self) -> None:
        c = _claim(evidence_json="[]", evidence_strength="strong")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["strong_rate"] == 0.0

    def test_all_strong(self) -> None:
        src_id = str(uuid.uuid4())
        c = _claim(evidence_json=json.dumps([src_id]), evidence_strength="strong")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["strong_rate"] == 1.0

    def test_mixed_strong_and_weak(self) -> None:
        src_id = str(uuid.uuid4())
        strong = _claim(evidence_json=json.dumps([src_id]), evidence_strength="strong")
        weak = _claim(evidence_json=json.dumps([src_id]), evidence_strength="weak")
        result = compute_metrics([strong, weak], [], [], [], _EMPTY_INTAKE)
        assert result["strong_rate"] == 0.5

    def test_moderate_not_counted_as_strong(self) -> None:
        src_id = str(uuid.uuid4())
        c = _claim(evidence_json=json.dumps([src_id]), evidence_strength="moderate")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["strong_rate"] == 0.0


class TestHumanCorrectionRate:
    """human_correction_rate = latest-human-corrected / total distinct claims."""

    def test_zero_when_no_claims(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["human_correction_rate"] == 0.0

    def test_one_human_corrected_out_of_one(self) -> None:
        c = _claim(produced_by="human:correction")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["human_correction_rate"] == 1.0

    def test_one_human_corrected_out_of_three(self) -> None:
        c1 = _claim(produced_by="analyst")
        c2 = _claim(produced_by="analyst")
        c3 = _claim(produced_by="human:correction")
        result = compute_metrics([c1, c2, c3], [], [], [], _EMPTY_INTAKE)
        assert result["human_correction_rate"] == round(1 / 3, 4)

    def test_machine_produced_is_not_human_corrected(self) -> None:
        c = _claim(produced_by="analyst")
        result = compute_metrics([c], [], [], [], _EMPTY_INTAKE)
        assert result["human_correction_rate"] == 0.0

    def test_latest_version_human_corrected_counts(self) -> None:
        """latest_claims_for_run already de-duplicates; this exercises the metric."""
        cid = str(uuid.uuid4())
        # Simulate: only the latest version (v2, human:correction) is passed in
        latest = _claim(id=cid, produced_by="human:correction")
        other = _claim(produced_by="analyst")
        result = compute_metrics([latest, other], [], [], [], _EMPTY_INTAKE)
        # 1 out of 2 distinct claims (different ids)
        assert result["human_correction_rate"] == 0.5


class TestEfficiencyMetric:
    """efficiency dict: elapsed_s, source_count, llm_calls, total_tokens."""

    def test_elapsed_s_two_events(self) -> None:
        events = [_trace_event(1000.0), _trace_event(1005.5)]
        result = compute_metrics([], [], [], events, _EMPTY_INTAKE)
        assert result["efficiency"]["elapsed_s"] == pytest.approx(5.5, abs=1e-3)

    def test_elapsed_s_zero_with_one_event(self) -> None:
        result = compute_metrics([], [], [], [_trace_event(1000.0)], _EMPTY_INTAKE)
        assert result["efficiency"]["elapsed_s"] == 0.0

    def test_elapsed_s_zero_with_no_events(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        assert result["efficiency"]["elapsed_s"] == 0.0

    def test_source_count(self) -> None:
        sources = [_source(), _source()]
        result = compute_metrics([], [], sources, [], _EMPTY_INTAKE)
        assert result["efficiency"]["source_count"] == 2

    def test_llm_calls_count(self) -> None:
        calls = [_llm_call(50), _llm_call(75)]
        result = compute_metrics([], calls, [], [], _EMPTY_INTAKE)
        assert result["efficiency"]["llm_calls"] == 2

    def test_total_tokens_summed(self) -> None:
        calls = [_llm_call(50), _llm_call(75)]
        result = compute_metrics([], calls, [], [], _EMPTY_INTAKE)
        assert result["efficiency"]["total_tokens"] == 125

    def test_none_tokens_treated_as_zero(self) -> None:
        calls = [_llm_call(None), _llm_call(30)]
        result = compute_metrics([], calls, [], [], _EMPTY_INTAKE)
        assert result["efficiency"]["total_tokens"] == 30


class TestHumanBaselineSpeedup:
    """efficiency: honest MEASURED-vs-ESTIMATED human-baseline speedup.

    Machine time is real (elapsed_s); the human range is an industry ESTIMATE.
    Speedup is derived from real elapsed_s and never divides by zero.
    """

    def test_human_baseline_fields_always_present(self) -> None:
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        eff = result["efficiency"]
        assert eff["human_baseline_hours_low"] == HUMAN_BASELINE_HOURS_LOW
        assert eff["human_baseline_hours_high"] == HUMAN_BASELINE_HOURS_HIGH

    def test_speedup_null_when_elapsed_zero(self) -> None:
        """elapsed_s == 0 → speedups are None (no ZeroDivisionError / infinity)."""
        result = compute_metrics([], [], [], [], _EMPTY_INTAKE)
        eff = result["efficiency"]
        assert eff["elapsed_s"] == 0.0
        assert eff["speedup_low"] is None
        assert eff["speedup_high"] is None

    def test_speedup_null_with_single_event(self) -> None:
        """A single trace event yields elapsed_s 0 → null speedups."""
        result = compute_metrics([], [], [], [_trace_event(1000.0)], _EMPTY_INTAKE)
        eff = result["efficiency"]
        assert eff["speedup_low"] is None
        assert eff["speedup_high"] is None

    def test_speedup_is_sane_integer_for_real_elapsed(self) -> None:
        """A 60s real run vs 16–40h estimate → speedup ≈ 960×–2400×."""
        events = [_trace_event(1000.0), _trace_event(1060.0)]  # 60s elapsed
        result = compute_metrics([], [], [], events, _EMPTY_INTAKE)
        eff = result["efficiency"]
        assert eff["elapsed_s"] == pytest.approx(60.0, abs=1e-3)
        # speedup_low = round(16*3600/60) = 960 ; speedup_high = round(40*3600/60) = 2400
        assert eff["speedup_low"] == 960
        assert eff["speedup_high"] == 2400
        assert isinstance(eff["speedup_low"], int)
        assert isinstance(eff["speedup_high"], int)
        # Low estimate must never exceed the high estimate.
        assert eff["speedup_low"] <= eff["speedup_high"]

    def test_speedup_suppressed_below_credible_floor(self) -> None:
        """A sub-second run (events 0.1s apart) is below MIN_CREDIBLE_ELAPSED_S →
        speedups None, so the UI never prints an absurd '本次 0s … 576,000×'."""
        events = [_trace_event(1000.0), _trace_event(1000.1)]  # 0.1s elapsed
        eff = compute_metrics([], [], [], events, _EMPTY_INTAKE)["efficiency"]
        assert eff["elapsed_s"] == pytest.approx(0.1, abs=1e-3)
        assert eff["speedup_low"] is None
        assert eff["speedup_high"] is None

    def test_speedup_keeps_decimal_for_slow_run_no_round_up(self) -> None:
        """A run slower than the low human estimate must NOT round up to a
        flattering whole '1×'. 16h+ elapsed → low ratio < 1, kept to 1 decimal."""
        # 20h elapsed: low = 16*3600/72000 = 0.8×, high = 40*3600/72000 = 2.0×
        events = [_trace_event(0.0), _trace_event(72000.0)]
        eff = compute_metrics([], [], [], events, _EMPTY_INTAKE)["efficiency"]
        assert eff["speedup_low"] == 0.8  # not rounded up to 1
        assert eff["speedup_high"] == 2.0

    def test_sub_one_ratio_is_floored_not_rounded_up(self) -> None:
        """A run only slightly slower than the human-low estimate must show <1×,
        never a parity-claiming 1.0× (round(0.96,1) would lie). 16.67h elapsed →
        low = 16*3600/60000 = 0.96 → floored to 0.9×."""
        events = [_trace_event(0.0), _trace_event(60000.0)]
        eff = compute_metrics([], [], [], events, _EMPTY_INTAKE)["efficiency"]
        assert eff["speedup_low"] == 0.9  # floored from 0.96, NOT rounded to 1.0
        assert eff["speedup_low"] < 1.0


# ---------------------------------------------------------------------------
# Layer 2 — Endpoint tests (real DB + HTTP via TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "metrics_test.db"))
    d.init_schema()
    return d


@pytest.fixture()
def run_id(db: Database) -> str:
    return db.create_run(
        category="CRM",
        competitors=["Acme", "BetaCo"],
        goal="compare pricing",
    )


@pytest.fixture()
def source_id(db: Database, run_id: str) -> str:
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
            "raw_text": "Acme charges $10/mo.",
            "meta_json": "{}",
        }
    )
    return sid


@pytest.fixture()
def client(db: Database) -> TestClient:
    return TestClient(create_app(db=db, run_executor=None))


class TestGetMetricsEndpoint:
    def test_404_on_missing_run(self, client: TestClient) -> None:
        resp = client.get("/runs/nonexistent_run_xyz/metrics")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"

    def test_200_on_existing_run(self, client: TestClient, run_id: str) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        assert resp.status_code == 200

    def test_all_expected_keys_present(self, client: TestClient, run_id: str) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        data = resp.json()
        expected_keys = {
            "coverage",
            "citation_rate",
            "strong_rate",
            "human_correction_rate",
            "efficiency",
            "accuracy_caveat",
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_efficiency_sub_keys_present(self, client: TestClient, run_id: str) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        eff = resp.json()["efficiency"]
        assert set(eff.keys()) >= {
            "elapsed_s",
            "source_count",
            "llm_calls",
            "total_tokens",
            "human_baseline_hours_low",
            "human_baseline_hours_high",
            "speedup_low",
            "speedup_high",
        }

    def test_empty_run_has_null_speedup(self, client: TestClient, run_id: str) -> None:
        """A run with <2 trace events has elapsed_s 0 → null speedups over HTTP."""
        resp = client.get(f"/runs/{run_id}/metrics")
        eff = resp.json()["efficiency"]
        assert eff["speedup_low"] is None
        assert eff["speedup_high"] is None

    def test_all_zeros_on_empty_run(self, client: TestClient, run_id: str) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        data = resp.json()
        assert data["coverage"] == 0.0
        assert data["citation_rate"] == 0.0
        assert data["strong_rate"] == 0.0
        assert data["human_correction_rate"] == 0.0

    def test_coverage_reflects_passed_claims(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        """One passed claim on pricing_model → coverage = 1/5."""
        db.append_claim(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Acme pro is $10/mo.",
                "value_json": "{}",
                "evidence_json": json.dumps([source_id]),
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )
        resp = client.get(f"/runs/{run_id}/metrics")
        data = resp.json()
        assert data["coverage"] == round(1 / len(FIELD_SCHEMAS), 4)
        assert data["citation_rate"] == 1.0
        assert data["strong_rate"] == 1.0

    def test_human_correction_rate_nonzero_after_correct(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        """After human correction, human_correction_rate must be > 0."""
        cid = str(uuid.uuid4())
        # Insert original claim
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Acme pro is $10/mo.",
                "value_json": "{}",
                "evidence_json": json.dumps([source_id]),
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": "pass",
                "version": 1,
                "produced_by": "analyst",
            }
        )
        # Insert human correction (version 2)
        db.append_claim(
            {
                "id": cid,
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Acme pro is $12/mo (corrected).",
                "value_json": "{}",
                "evidence_json": json.dumps([source_id]),
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": "pass",
                "version": 2,
                "produced_by": "human:correction",
            }
        )
        resp = client.get(f"/runs/{run_id}/metrics")
        data = resp.json()
        # 1 distinct claim, latest version is human:correction → rate = 1.0
        assert data["human_correction_rate"] == 1.0

    def test_source_count_in_efficiency(
        self,
        db: Database,
        client: TestClient,
        run_id: str,
        source_id: str,
    ) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        assert resp.json()["efficiency"]["source_count"] == 1

    def test_accuracy_caveat_string_returned(
        self, client: TestClient, run_id: str
    ) -> None:
        resp = client.get(f"/runs/{run_id}/metrics")
        assert resp.json()["accuracy_caveat"] == ACCURACY_CAVEAT
