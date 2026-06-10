"""Offline tests for the production run executor (Task: API->graph wiring).

These tests drive :func:`mingjing.runner.make_run_executor` end-to-end with NO
network and NO live LLM by:
- injecting deterministic fake ``collect_fn`` / ``analyze_fn`` (the same shape as
  ``tests/test_loop_smoke.py``),
- disabling prewarm (``prewarm=False``) so no live fetch is attempted,
- sharing ONE ``Database`` instance via ``get_db=lambda: db`` so the executor's
  writes are visible to the same DB an API would poll.
"""

import json

import pytest

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.config import Settings
from mingjing.db import Database
from mingjing.runner import make_run_executor

COMPETITOR = "Acme"
STATEMENT = "Pro tier costs $10 per month"
PAGE_A_URL = "https://reviews.example.net/acme"
PAGE_B_URL = "https://acme.example.com/pricing"
PAGE_A_TEXT = f"Reviewers report: {STATEMENT}, billed annually."
PAGE_B_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly."

FIXTURE_SOURCES = [
    {
        "url": PAGE_A_URL,
        "title": "Acme review",
        "snippet": STATEMENT,
        "fetched": True,
        "source_id": "fix-A",
        "source_mode": "CACHED",
        "text": PAGE_A_TEXT,
        "content_hash": "hashA",
        "fetched_at": 1.0,
    },
    {
        "url": PAGE_B_URL,
        "title": "Acme pricing",
        "snippet": STATEMENT,
        "fetched": True,
        "source_id": "fix-B",
        "source_mode": "CACHED",
        "text": PAGE_B_TEXT,
        "content_hash": "hashB",
        "fetched_at": 2.0,
    },
]


def _fake_collect_fn(query, *, cache, source_cap, mode="live_first"):
    """Return the first ``source_cap`` fixture sources (a real additional fetch)."""
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_fn(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Corroborate only when >=2 distinct sources exist (weak->strong driver)."""
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {"tiers": ["Pro $10/mo"]},
        "evidence_ref": evidence_ref,
    }


def _settings_for(tmp_path) -> Settings:
    """Build a Settings whose cache_db_path lives under ``tmp_path``."""
    return Settings(
        minimax_base_url="https://example.invalid/v1",
        minimax_api_key="",
        minimax_model="test-model",
        mode="live_first",
        rate_limiting_enabled=True,
        db_path=str(tmp_path / "run.db"),
        cache_db_path=str(tmp_path / "cache.db"),
        per_field_source_cap=3,
        min_source_chars=0,
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
def seeded(tmp_path):
    """A schema-initialised DB with one run; cache seeded with two fixture pages."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")
    settings = _settings_for(tmp_path)
    # Seed the LIVE cache so the fake collect_fn's cache fallback is real.
    with Cache(settings.cache_db_path) as cache:
        cache.put(FetchResult(text=PAGE_A_TEXT, url=PAGE_A_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=PAGE_B_TEXT, url=PAGE_B_URL, source_mode="LIVE"))
    return db, run_id, settings


@pytest.mark.slow
def test_executor_drives_graph_to_complete(seeded) -> None:
    """The executor runs the graph, persists claims+trace, and sets status."""
    db, run_id, settings = seeded

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=_fake_collect_fn,
        analyze_fn=_fake_analyze_fn,
        prewarm=False,
    )
    executor(run_id)

    # 1. The run now has at least one latest claim.
    latest = db.latest_claims_for_run(run_id)
    assert latest, "executor should have produced at least one claim"

    # 2. A claim cites real, persisted sources (weak->strong reached strong).
    final_claim = latest[0]
    evidence = json.loads(final_claim["evidence_json"])
    assert evidence, "final claim must cite evidence"
    for ev in evidence:
        assert db.get_source(ev["source_id"]) is not None

    # 3. The trace includes a terminal run_complete / run_partial event.
    events = db.trace_events_for_run(run_id)
    event_types = {e["event_type"] for e in events}
    assert event_types & {"run_complete", "run_partial"}, (
        f"expected a terminal run event; got {event_types}"
    )

    # 4. The run status was recorded as complete or partial.
    status = db.get_run(run_id)["status"]
    assert status in ("complete", "partial")


@pytest.mark.slow
def test_executor_analyze_raise_skips_field_not_crashes(seeded) -> None:
    """A raising analyze_fn is caught per-field; the run completes normally.

    Fix 1 changed the contract: exceptions from ``analyze_fn`` are caught inside
    the analyze node, logged as ``claim_skipped`` trace events, and the loop
    continues.  The run therefore reaches ``write`` and ends with status
    ``complete`` or ``partial`` — NOT ``error``.
    """
    db, run_id, settings = seeded

    def exploding_analyze_fn(*args, **kwargs):
        raise RuntimeError("synthetic analyze failure")

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=_fake_collect_fn,
        analyze_fn=exploding_analyze_fn,
        prewarm=False,
    )

    # Must NOT raise — the exception is absorbed per-field by the analyze node.
    executor(run_id)

    run_status = db.get_run(run_id)["status"]
    assert run_status in ("complete", "partial"), (
        f"expected complete/partial after per-field catch; got {run_status!r}"
    )
    events = db.trace_events_for_run(run_id)
    skipped = [e for e in events if e["event_type"] == "claim_skipped"]
    assert skipped, "expected claim_skipped trace event(s) for each raised field"


def test_executor_marks_error_when_graph_invoke_raises(tmp_path, monkeypatch) -> None:
    """Non-analyze failures in graph.invoke mark the run 'error' and re-raise.

    Patches ``mingjing.graph.build_graph`` (the symbol imported inside the run
    closure) to return a fake graph whose ``.invoke`` raises ``RuntimeError``.
    Verifies the executor re-raises AND the DB status is set to ``"error"``.
    """
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")
    settings = _settings_for(tmp_path)

    class _BoomGraph:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("mingjing.graph.build_graph", lambda **kw: _BoomGraph())

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=_fake_collect_fn,
        analyze_fn=_fake_analyze_fn,
        prewarm=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        executor(run_id)

    assert db.get_run(run_id)["status"] == "error"

    # A hard failure must emit a TERMINAL run_error trace event so the frontend
    # can render a final error state instead of polling/spinning forever.
    events = db.trace_events_for_run(run_id)
    error_events = [e for e in events if e["event_type"] == "run_error"]
    assert len(error_events) == 1, (
        f"expected exactly one run_error event, got {len(error_events)}"
    )
    payload = json.loads(error_events[0]["payload_json"])
    # Concise message only — must name the exception type, never leak the
    # raw traceback / message body ("boom") that could carry sensitive data.
    assert payload["message"] == "Run failed: RuntimeError"
    assert "boom" not in error_events[0]["payload_json"]


def test_executor_uses_run_domain_schema(tmp_path) -> None:
    """A run with ``domain='ai_agent'`` makes that domain's schema active.

    Probe seam: ``collect_fn`` is invoked per (competitor x field) DURING the run
    body, so capturing ``active_field_schemas()`` there proves the run's domain is
    applied for the whole body (analyst + QA read the same ContextVar). The
    ai_agent schema includes ``autonomy_level``, which the default domain lacks.
    """
    from mingjing.schemas import active_field_schemas

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(
        category="cat", competitors=[COMPETITOR], goal="g", domain="ai_agent"
    )
    settings = _settings_for(tmp_path)

    seen: dict[str, set[str]] = {}

    def probing_collect_fn(query, *, cache, source_cap, mode="live_first"):
        seen["fields"] = set(active_field_schemas().keys())
        return []  # no sources -> fast partial, but the probe already fired

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=probing_collect_fn,
        analyze_fn=_fake_analyze_fn,
        prewarm=False,
    )
    executor(run_id)

    assert "fields" in seen, "collect_fn should have been called during the run"
    assert "autonomy_level" in seen["fields"], (
        "ai_agent schema must be active during the run body"
    )
    # The ContextVar resets cleanly after the run (default has no autonomy_level).
    assert "autonomy_level" not in active_field_schemas()


def test_executor_no_domain_uses_default_schema(tmp_path) -> None:
    """Control: a run with NO domain leaves the default schema active (no switch)."""
    from mingjing.schemas import active_field_schemas

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")
    settings = _settings_for(tmp_path)

    seen: dict[str, set[str]] = {}

    def probing_collect_fn(query, *, cache, source_cap, mode="live_first"):
        seen["fields"] = set(active_field_schemas().keys())
        return []

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=probing_collect_fn,
        analyze_fn=_fake_analyze_fn,
        prewarm=False,
    )
    executor(run_id)

    assert "fields" in seen, "collect_fn should have been called during the run"
    assert "autonomy_level" not in seen["fields"], (
        "no-domain run must keep the default schema (no ai_agent fields)"
    )


def test_executor_missing_run_is_noop(tmp_path) -> None:
    """An unknown run_id is logged and returns without raising."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    settings = _settings_for(tmp_path)

    executor = make_run_executor(
        get_db=lambda: db,
        settings=settings,
        collect_fn=_fake_collect_fn,
        analyze_fn=_fake_analyze_fn,
        prewarm=False,
    )
    # Should not raise even though the run does not exist.
    executor("does-not-exist")
