"""A run for the fixture competitor produces a survey-backed claim that passes the
SAME QA gate (value grounded in the survey source row's raw_text), and the report
claim's source is typed survey with a survey: locator. A non-fixture competitor
seeds zero survey sources but still emits survey_designed.

Deterministic: a survey-aware fake analyze_fn cites the run-scoped survey source
id (the id surfaced to it in source_ids), matched by its stable locator suffix.
"""
import pytest

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.runner import make_run_executor


def _settings_for(tmp_path) -> Settings:
    """Offline Settings with temp paths for survey-lane integration tests.

    Similar to tests/test_runner.py but differs: min_source_chars=100 here
    (vs 0 in test_runner.py) so QA grounding checks are exercised.
    """
    return Settings(
        minimax_base_url="https://example.invalid/v1",
        minimax_api_key="",
        minimax_model="test-model",
        mode="live_first",
        rate_limiting_enabled=True,
        db_path=str(tmp_path / "run.db"),
        cache_db_path=str(tmp_path / "cache.db"),
        per_field_source_cap=3,
        min_source_chars=100,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth="quick",
        deep_collect_workers=8,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
    )


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return _settings_for(tmp_path)


_EMPTY_CLAIM = {"statement": "", "claim_type": "fact", "value": {}, "evidence_ref": []}


def _empty_analyst(*a, **k):
    """Always return an empty claim (no field matches)."""
    return _EMPTY_CLAIM


def _fake_survey_analyst(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
    """Cite the seeded survey source for pricing_model; value is a substring of its raw_text.

    The seeded id is run-scoped (``{run_id}-survey-SV-1-pricing_model``); match it
    by its stable locator suffix and cite the actual surfaced id(s).
    """
    survey_ids = [s for s in source_ids if "survey-SV-1-pricing_model" in s]
    if field == "pricing_model" and survey_ids:
        return {
            "statement": "Surveyed users report Pro at $10/mo.",
            "claim_type": "fact",
            "value": {"tiers": ["Pro plan at $10/mo"]},   # substring of the fixture text
            "evidence_ref": survey_ids,
        }
    return _EMPTY_CLAIM


def _no_web(query, *, cache, source_cap, mode="live_first"):
    return []


def test_fixture_run_survey_only_claim_is_grounded_but_withheld(tmp_path, settings):
    """The survey lane works end-to-end, but simulated data cannot buy admission.

    New contract (option a, 诚实降档): fixture-seeded survey rows are
    SIMULATED — they are ingested, citable, and verbatim-groundable (the lane
    is demonstrably real), yet they contribute ZERO to the evidence tier. A
    claim whose ONLY support is the simulated survey therefore scores weak and
    is honestly withheld, never admitted. Before the SIMULATED split this very
    scenario produced a passing claim — that was the fixture minting
    credibility, which is exactly what we removed.
    """
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="compare note apps")
    execu = make_run_executor(
        lambda: db, settings=settings,
        collect_fn=_no_web, analyze_fn=_fake_survey_analyst, prewarm=False,
    )
    execu(run_id)

    # the seeded survey source exists, typed survey, and is marked SIMULATED
    src = db.get_source(f"{run_id}-survey-SV-1-pricing_model")
    assert src is not None and src["source_type"] == "survey"
    assert src["source_mode"] == "SIMULATED"

    # the lane DID produce a claim citing the survey source (ingestion +
    # grounding work) — but it must remain a draft, never status=pass
    latest = {c["id"]: c for c in db.latest_claims_for_run(run_id)}
    pricing = [c for c in latest.values() if c["schema_field"] == "pricing_model"]
    assert pricing, "the analyst did propose a survey-cited pricing claim"
    assert all(c["status"] != "pass" for c in pricing), (
        "a claim supported ONLY by simulated survey data must not be admitted"
    )

    # survey_designed trace event emitted (the design card's data)
    designed = [e for e in db.trace_events_for_run(run_id)
                if e["event_type"] == "survey_designed"]
    assert designed


def test_non_fixture_competitor_seeds_no_survey_but_emits_design(tmp_path, settings):
    db = Database(str(tmp_path / "run2.db"))
    db.init_schema()
    run_id = db.create_run(category="x", competitors=["Acme Unknown Co"], goal="g")
    execu = make_run_executor(
        lambda: db, settings=settings,
        collect_fn=_no_web, analyze_fn=_empty_analyst, prewarm=False,
    )
    execu(run_id)
    survey_sources = [s for s in db.sources_for_run(run_id) if s["source_type"] in ("survey", "interview")]
    assert survey_sources == []           # honest absence — no synthesized evidence
    assert [e for e in db.trace_events_for_run(run_id) if e["event_type"] == "survey_designed"]


def test_survey_lane_failure_does_not_abort_run(tmp_path, settings, monkeypatch):
    """A survey-lane glitch (e.g. malformed fixture) must not kill an otherwise-valid run."""
    import mingjing.runner as runner_mod
    db = Database(str(tmp_path / "run3.db"))
    db.init_schema()
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")

    def _boom(*a, **k):
        raise ValueError("malformed fixture")

    monkeypatch.setattr(runner_mod, "survey_seed", _boom)
    execu = make_run_executor(
        lambda: db, settings=settings,
        collect_fn=_no_web, analyze_fn=_fake_survey_analyst, prewarm=False,
    )
    execu(run_id)  # must NOT raise
    status = db.get_run(run_id)["status"]
    assert status in ("complete", "partial")  # run finished, not crashed/error


# ---------------------------------------------------------------------------
# Task 7 guard tests — LOCK the Task 3–4 invariants (TEST-ONLY, no prod change)
# ---------------------------------------------------------------------------


def _grounding_claimset(source_id: str, source_type: str, url: str) -> dict:
    """A single fact claim citing one source, whose REQUIRED `tiers` leaf carries a
    value that is NOT a substring of the source raw_text. Shaped exactly like the
    web-source gate-parity fixture in tests/test_qa_rules.py — only source_type/url
    vary, so qa_check runs the SAME generic value-grounding path for both."""
    return {
        "claims": [
            {
                "id": "C1",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "competitor": "Notion",
                "value": {"tiers": ["Fabricated Enterprise Tier"]},  # absent from source
                "evidence": [
                    {"source_id": source_id, "snippet": "the Pro plan at $10/mo", "relevance": "supports"},
                ],
            }
        ],
        "sources": {
            source_id: {
                "raw_text": "Most respondents report the Pro plan at $10/mo.",
                "source_type": source_type,
                "url": url,
            }
        },
        "coverage": {"required_fields": [], "covered_fields": []},
    }


def test_survey_value_not_in_text_trips_value_unsupported(tmp_path):
    """Gate-parity: a survey claim whose value isn't in the survey raw_text is
    rejected by VALUE_UNSUPPORTED exactly like a web claim (no special-casing).

    Feeds qa_check the SAME claim twice — once with a survey source, once with a
    web (official) source — and asserts BOTH trip VALUE_UNSUPPORTED. Identical
    behavior proves the survey source goes through the generic value-grounding
    path with no survey-specific exemption in the gate.
    """
    from mingjing.qa.rules import qa_check
    from mingjing.schemas import IssueCode

    survey_codes = {
        i.code for i in qa_check(
            _grounding_claimset("survey-SV-1-pricing_model", "survey", "survey:SV-1/pricing_model")
        )
    }
    web_codes = {
        i.code for i in qa_check(
            _grounding_claimset("web-1", "official", "https://notion.so/pricing")
        )
    }
    assert IssueCode.VALUE_UNSUPPORTED in survey_codes  # survey is NOT special-cased
    assert IssueCode.VALUE_UNSUPPORTED in web_codes      # web trips the same gate
    assert survey_codes == web_codes                     # byte-for-byte identical verdict


def test_survey_source_raw_text_is_groundable_not_chunk(tmp_path):
    """Mechanism guard: the seeded survey source row's raw_text is the scrubbed
    answer text (catches a future chunk-vs-raw_text regression where raw_text
    would hold a chunk id / blank instead of the groundable answer)."""
    from mingjing.db import Database
    from mingjing.survey_fixture import fixture_for
    from mingjing.survey_seed import survey_seed

    db = Database(str(tmp_path / "g.db"))
    db.init_schema()
    run_id = db.create_run(category="n", competitors=["Notion"], goal="g")
    survey_seed(db, run_id, "Notion", fixture_for("Notion"))

    row = db.get_source(f"{run_id}-survey-SV-1-pricing_model")
    assert row is not None
    assert row["raw_text"] and "Pro plan at $10/mo" in row["raw_text"]
