"""Offline unit tests for the deterministic Scope & Methodology projection (M4).

``build_scope_methodology`` is a PURE projection (no LLM, no DB, no network): it
takes already-fetched ledger data (run row, source rows, withheld disclosure,
credibility panel, trace events) and builds the report's "范围与方法" section.

Coverage:
- directed mode (run.competitors supplied, no discovery events)
- discovery mode (a ``competitors_discovered`` trace event present)
- source_stats: total, by source_mode, by source_type, independent domains
- SIMULATED disclosure sentence appears iff a SIMULATED source exists
- excluded: withheld count + de-duped issue codes + uncovered fields
- empty run (0 sources, 0 claims) does not crash
- report endpoint integration: GET /runs/{id}/report carries scope_methodology
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database
from mingjing.schemas import IssueCode
from mingjing.scope import build_scope_methodology

# ---------------------------------------------------------------------------
# Fixtures: synthetic ledger inputs (no DB needed for the pure-projection tests)
# ---------------------------------------------------------------------------


def _src(
    sid: str,
    *,
    url: str | None,
    source_mode: str,
    source_type: str,
) -> dict:
    """A minimal source row dict as ``sources_for_run`` would return."""
    return {
        "id": sid,
        "url": url,
        "source_mode": source_mode,
        "source_type": source_type,
    }


def _directed_run() -> dict:
    return {
        "id": "run-directed",
        "category": "CRM",
        "competitors": ["Acme", "BetaCo"],
        "goal": "compare pricing",
        "status": "complete",
    }


def _discovery_run() -> dict:
    # Discovery runs start with empty competitors + a category; the discover
    # pre-step persists the selected competitors back onto the run row.
    return {
        "id": "run-discovery",
        "category": "项目管理 SaaS",
        "competitors": ["Notion", "Linear"],
        "goal": "find the leaders",
        "status": "complete",
    }


_DISCOVERY_EVENTS = [
    {"event_type": "discovery_started", "payload_json": "{}"},
    {
        "event_type": "competitors_discovered",
        "payload_json": json.dumps({"selected": ["Notion", "Linear"]}),
    },
]


def _credibility(
    *,
    proposed: int,
    admitted: int,
    withheld: int,
    covered: list[str],
    uncovered: list[str],
) -> dict:
    return {
        "proposed_claims": proposed,
        "admitted_claims": admitted,
        "withheld_claims": withheld,
        "covered_fields": covered,
        "uncovered_fields": uncovered,
    }


# ---------------------------------------------------------------------------
# A) Mode detection
# ---------------------------------------------------------------------------


class TestModeDetection:
    def test_directed_mode_when_no_discovery_events(self) -> None:
        out = build_scope_methodology(
            run=_directed_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        assert out["mode"] == "directed"

    def test_discovery_mode_when_competitors_discovered_event(self) -> None:
        out = build_scope_methodology(
            run=_discovery_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=_DISCOVERY_EVENTS,
        )
        assert out["mode"] == "discovery"

    def test_directed_competitors_carry_user_specified_reason(self) -> None:
        out = build_scope_methodology(
            run=_directed_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        names = [c["name"] for c in out["competitors"]]
        assert names == ["Acme", "BetaCo"]
        # Directed inclusion reason mentions user specification.
        assert all("用户指定" in c["reason"] for c in out["competitors"])

    def test_discovery_competitors_carry_discovery_reason(self) -> None:
        out = build_scope_methodology(
            run=_discovery_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=_DISCOVERY_EVENTS,
        )
        assert [c["name"] for c in out["competitors"]] == ["Notion", "Linear"]
        assert all("发现" in c["reason"] for c in out["competitors"])


# ---------------------------------------------------------------------------
# B) Source statistics
# ---------------------------------------------------------------------------


class TestSourceStats:
    def test_total_and_mode_and_type_distribution(self) -> None:
        sources = [
            _src("s1", url="https://acme.com/a", source_mode="LIVE", source_type="official"),
            _src("s2", url="https://blog.acme.com/b", source_mode="CACHED", source_type="web"),
            _src("s3", url="https://betaco.io/c", source_mode="LIVE", source_type="review"),
            _src("s4", url="https://news.example.org/d", source_mode="INGESTED", source_type="web"),
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=sources,
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        stats = out["source_stats"]
        assert stats["total"] == 4
        assert stats["by_source_mode"] == {"LIVE": 2, "CACHED": 1, "INGESTED": 1}
        assert stats["by_source_type"] == {"official": 1, "web": 2, "review": 1}

    def test_independent_domains_dedupes_subdomains(self) -> None:
        # acme.com and blog.acme.com collapse to ONE registrable domain.
        sources = [
            _src("s1", url="https://acme.com/a", source_mode="LIVE", source_type="official"),
            _src("s2", url="https://blog.acme.com/b", source_mode="CACHED", source_type="web"),
            _src("s3", url="https://betaco.io/c", source_mode="LIVE", source_type="review"),
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=sources,
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        # acme.com (x2) + betaco.io = 2 independent registrable domains.
        assert out["source_stats"]["independent_domains"] == 2

    def test_simulated_excluded_from_independent_domains(self) -> None:
        # A SIMULATED source must not inflate the independent-domain count.
        sources = [
            _src("s1", url="https://acme.com/a", source_mode="LIVE", source_type="official"),
            _src(
                "sim",
                url="survey:demo/r1",
                source_mode="SIMULATED",
                source_type="survey",
            ),
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=sources,
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        # Only acme.com counts; the SIMULATED row is excluded from credibility.
        assert out["source_stats"]["independent_domains"] == 1
        # But the SIMULATED row IS counted in the raw total + mode distribution.
        assert out["source_stats"]["total"] == 2
        assert out["source_stats"]["by_source_mode"]["SIMULATED"] == 1


# ---------------------------------------------------------------------------
# C) SIMULATED disclosure sentence
# ---------------------------------------------------------------------------


class TestSimulatedDisclosure:
    def test_disclosure_present_when_simulated_source_exists(self) -> None:
        sources = [
            _src(
                "sim",
                url="survey:demo/r1",
                source_mode="SIMULATED",
                source_type="survey",
            ),
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=sources,
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        disclosures = out["excluded"]["disclosures"]
        assert any("模拟问卷" in d for d in disclosures)
        assert any("不参与可信度" in d for d in disclosures)

    def test_no_disclosure_when_no_simulated_source(self) -> None:
        sources = [
            _src("s1", url="https://acme.com/a", source_mode="LIVE", source_type="official"),
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=sources,
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        assert all("模拟问卷" not in d for d in out["excluded"]["disclosures"])


# ---------------------------------------------------------------------------
# D) Excluded: withheld claims + issue codes + uncovered fields
# ---------------------------------------------------------------------------


class TestExcluded:
    def test_withheld_count_and_deduped_issue_codes(self) -> None:
        withheld = [
            {"claim_id": "c1", "issue_codes": ["VALUE_UNSUPPORTED", "WEAK_EVIDENCE"], "round": 2},
            {"claim_id": "c2", "issue_codes": ["VALUE_UNSUPPORTED"], "round": 2},
            {"claim_id": "c3", "issue_codes": ["SCHEMA_GAP"], "round": 1},
        ]
        out = build_scope_methodology(
            run=_directed_run(),
            sources=[],
            withheld=withheld,
            credibility=_credibility(
                proposed=10, admitted=7, withheld=3, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        excluded = out["excluded"]
        assert excluded["withheld_count"] == 3
        # De-duped, stable (sorted) order.
        assert excluded["issue_codes"] == sorted(
            {"VALUE_UNSUPPORTED", "WEAK_EVIDENCE", "SCHEMA_GAP"}
        )

    def test_uncovered_fields_passed_through(self) -> None:
        out = build_scope_methodology(
            run=_directed_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=5,
                admitted=5,
                withheld=0,
                covered=["pricing_model", "user_sentiment"],
                uncovered=["swot", "feature_tree"],
            ),
            trace_events=[],
        )
        assert out["excluded"]["uncovered_fields"] == ["swot", "feature_tree"]


# ---------------------------------------------------------------------------
# E) Method sentences (honest, deterministic) — rule count from IssueCode
# ---------------------------------------------------------------------------


class TestMethod:
    def test_method_carries_rule_count_from_issuecode(self) -> None:
        out = build_scope_methodology(
            run=_directed_run(),
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        assert out["method"]["rule_count"] == len(IssueCode)
        # The honest method statements are present and non-empty.
        assert isinstance(out["method"]["statements"], list)
        assert out["method"]["statements"]
        joined = " ".join(out["method"]["statements"])
        # Key honesty anchors.
        assert "逐字" in joined
        assert "LLM" in joined


# ---------------------------------------------------------------------------
# F) Empty run robustness
# ---------------------------------------------------------------------------


class TestEmptyRun:
    def test_empty_run_does_not_crash(self) -> None:
        out = build_scope_methodology(
            run={
                "id": "empty",
                "category": "",
                "competitors": [],
                "goal": "",
                "status": "error",
            },
            sources=[],
            withheld=[],
            credibility=_credibility(
                proposed=0, admitted=0, withheld=0, covered=[], uncovered=[]
            ),
            trace_events=[],
        )
        assert out["mode"] == "directed"
        assert out["competitors"] == []
        assert out["source_stats"]["total"] == 0
        assert out["source_stats"]["independent_domains"] == 0
        assert out["excluded"]["withheld_count"] == 0
        assert out["excluded"]["issue_codes"] == []

    def test_none_run_degrades_gracefully(self) -> None:
        out = build_scope_methodology(
            run=None,
            sources=[],
            withheld=[],
            credibility={},
            trace_events=[],
        )
        assert out["mode"] == "directed"
        assert out["competitors"] == []
        assert out["source_stats"]["total"] == 0


# ---------------------------------------------------------------------------
# G) /report endpoint integration (TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(str(tmp_path / "test.db"))
    d.init_schema()
    return d


def _seed_run(db: Database) -> str:
    run_id = db.create_run(
        category="CRM", competitors=["Acme", "BetaCo"], goal="compare pricing"
    )
    sid = str(uuid.uuid4())
    db.append_source(
        {
            "id": sid,
            "run_id": run_id,
            "url": "https://acme.com/pricing",
            "title": "Acme pricing",
            "source_type": "official",
            "source_mode": "LIVE",
            "fetched_at": time.time(),
            "content_hash": "h1",
            "raw_text": "Acme charges $10/mo for the starter plan.",
            "meta_json": "{}",
        }
    )
    db.append_claim(
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing_model",
            "claim_type": "fact",
            "statement": "Acme starter plan costs $10/mo.",
            "value_json": json.dumps({"amount": 10}),
            "evidence_json": json.dumps([sid]),
            "based_on_json": json.dumps([]),
            "evidence_strength": "strong",
            "status": "pass",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    return run_id


class TestReportIntegration:
    def test_report_carries_scope_methodology(self, db: Database) -> None:
        run_id = _seed_run(db)
        client = TestClient(create_app(db=db, run_executor=None))
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert "scope_methodology" in body
        sm = body["scope_methodology"]
        # Shape assertions.
        assert sm["mode"] == "directed"
        assert [c["name"] for c in sm["competitors"]] == ["Acme", "BetaCo"]
        assert sm["source_stats"]["total"] == 1
        assert sm["source_stats"]["by_source_mode"] == {"LIVE": 1}
        assert sm["source_stats"]["independent_domains"] == 1
        assert sm["method"]["rule_count"] == len(IssueCode)
        # Legacy keys remain.
        assert "sections" in body
        assert "strength_tally" in body

    def test_report_scope_methodology_empty_run(self, db: Database) -> None:
        run_id = db.create_run(category="X", competitors=["Solo"], goal="g")
        client = TestClient(create_app(db=db, run_executor=None))
        resp = client.get(f"/runs/{run_id}/report")
        assert resp.status_code == 200
        sm = resp.json()["scope_methodology"]
        assert sm["source_stats"]["total"] == 0
        assert sm["excluded"]["withheld_count"] == 0
