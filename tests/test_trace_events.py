"""Trace-event enrichment tests (offline, deterministic).

Drives the full LangGraph loop via injected GraphDeps — no network, no LLM —
and asserts that the rich lifecycle events emitted by the graph nodes land in
the ``trace_events`` table with the correct ordering, payloads, and types.

Two scenarios:
1. ``test_trace_events_weak_to_strong``: the standard weak→strong loop.
   Round-0 QA rejects (WEAK_EVIDENCE) → ``qa_fail`` lands with claim_id +
   reason.  The revise node emits ``revise_start``.  Round-1 QA passes →
   ``qa_pass`` lands.  Write emits ``run_complete``.

2. ``test_trace_events_partial_run``: an analyst that always returns an empty
   evidence_ref keeps claims weak forever.  The loop terminates at the round
   cap and emits ``run_partial`` (never ``run_complete``).

Both scenarios also assert:
- ``collect_start`` / ``collect_done`` / ``analyze_start`` / ``analyze_done``
  are present.
- Every payload is JSON-serializable.
- No payload contains an api-key-like string (sk-/Bearer token pattern).
"""

import json
import re
import uuid

import pytest

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph

# ---------------------------------------------------------------------------
# Fixture pages (mirrors test_loop_smoke.py)
# ---------------------------------------------------------------------------

COMPETITOR = "Acme"
FIELD = "pricing_model"
STATEMENT = "Pro tier costs $10 per month"
PAGE_A_URL = "https://reviews.example.net/acme"
PAGE_B_URL = "https://acme.example.com/pricing"
PAGE_A_TEXT = f"Reviewers report: {STATEMENT}, billed annually."
PAGE_B_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly. Pro $10/mo plan available."

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

_API_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9]{8,}|Bearer [A-Za-z0-9]{8,}")


def _fake_collect_fn(query, *, cache, source_cap, mode="live_first"):
    """Return the first ``source_cap`` fixture sources."""
    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_strong_when_two_sources(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Corroborate only when >=2 distinct sources are present (mirrors loop smoke)."""
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {"tiers": ["Pro $10/mo"]},
        "evidence_ref": evidence_ref,
    }


def _fake_analyze_always_weak(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Never cite evidence → claim always scores weak → QA always rejects."""
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {"tiers": ["Pro $10/mo"]},
        "evidence_ref": [],  # empty → no supporting sources → weak strength
    }


def _ledger_ids(messages: list[dict]) -> list[str]:
    """Extract the claim ids the synthesis ledger asked the model to cite.

    The synthesis prompt embeds a LEDGER block of ``id | field | ...`` lines; we
    pull the leading id token off each so a fake LLM can return a genuinely
    claim-backed (and therefore non-empty) brief.
    """
    ids: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if "LEDGER" not in content:
            continue
        for line in content.splitlines():
            if " | " in line:
                ids.append(line.split(" | ", 1)[0].strip())
    return ids


def _fake_synthesis_llm(db, run_id, *, agent, messages, schema=None, settings=None):
    """Return a real cited brief so ``run_synthesis`` persists a non-empty payload.

    Cites the actual passed claim ids parsed from the ledger so
    ``project_synthesis`` keeps the sentences (its invariant: claim_ids ⊆ passed).
    Only the first builder (SWOT + comparison) returns content — that is enough
    for ``brief_sentence_count`` to be > 0.
    """
    ids = _ledger_ids(messages)
    if not ids:
        return {}
    sentence = {"text": f"{COMPETITOR} pricing is competitive.", "claim_ids": ids}
    return {
        "swot": {
            "strengths": [sentence],
            "weaknesses": [],
            "opportunities": [],
            "threats": [],
        },
        "comparison": [sentence],
    }


def _run_graph(
    tmp_path,
    analyze_fn,
    *,
    monkeypatch=None,
) -> tuple[Database, str]:
    """Spin up a fresh DB + Cache, build the graph, and invoke it.

    Returns ``(db, run_id)`` so callers can query the trace_events table. When
    ``monkeypatch`` is provided, the synthesis LLM is stubbed (offline runs have
    no API key) so ``run_synthesis`` produces a real brief and the node emits
    ``synthesis_done`` rather than the honest-empty ``synthesis_empty``.
    """
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")

    if monkeypatch is not None:
        monkeypatch.setattr("mingjing.synthesis.call_llm", _fake_synthesis_llm)

    with Cache(str(tmp_path / "cache.db")) as cache:
        cache.put(FetchResult(text=PAGE_A_TEXT, url=PAGE_A_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=PAGE_B_TEXT, url=PAGE_B_URL, source_mode="LIVE"))

        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=None,
            collect_fn=_fake_collect_fn,
            analyze_fn=analyze_fn,
        )
        graph = build_graph(deps=deps)
        graph.invoke(
            {
                "run_id": run_id,
                "db": db,
                "intake": {
                    "category": "cat",
                    "competitors": [COMPETITOR],
                    "goal": "g",
                    "fields": [FIELD],
                },
            }
        )

    return db, run_id


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------


def _events_of_type(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if e["event_type"] == event_type]


def _payload(event: dict) -> dict:
    raw = event.get("payload_json", "{}")
    return json.loads(raw) if isinstance(raw, str) else {}


def _assert_all_payloads_serializable(events: list[dict]) -> None:
    for ev in events:
        raw = ev.get("payload_json", "{}")
        # Must be a valid JSON string already (the DB stores serialized payload).
        parsed = json.loads(raw)
        # Re-serializing must not raise.
        json.dumps(parsed)


def _assert_no_api_keys(events: list[dict]) -> None:
    for ev in events:
        raw = ev.get("payload_json", "{}")
        assert not _API_KEY_PATTERN.search(raw), (
            f"Potential API key found in payload: {raw!r}"
        )


# ---------------------------------------------------------------------------
# Test 1: weak → strong loop
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_trace_events_weak_to_strong(tmp_path, monkeypatch) -> None:
    """Full weak→strong run emits the expected lifecycle events in order."""
    db, run_id = _run_graph(
        tmp_path, _fake_analyze_strong_when_two_sources, monkeypatch=monkeypatch
    )
    events = db.trace_events_for_run(run_id)
    types = [e["event_type"] for e in events]

    # Basic lifecycle events must all appear.
    assert "collect_start" in types, "collect_start missing"
    assert "collect_done" in types, "collect_done missing"
    assert "analyze_start" in types, "analyze_start missing"
    assert "analyze_done" in types, "analyze_done missing"

    # Round-0 QA must have produced at least one qa_fail.
    qa_fails = _events_of_type(events, "qa_fail")
    assert qa_fails, "expected at least one qa_fail event"

    # The first qa_fail must carry a claim_id and a non-empty reason.
    first_fail = qa_fails[0]
    fp = _payload(first_fail)
    assert fp.get("claim_id"), f"qa_fail payload missing claim_id: {fp}"
    assert fp.get("reason"), f"qa_fail payload missing reason: {fp}"

    # revise_start must follow the first qa_fail in event order.
    revise_starts = _events_of_type(events, "revise_start")
    assert revise_starts, "expected at least one revise_start event"
    first_revise_idx = types.index("revise_start")
    first_fail_idx = types.index("qa_fail")
    assert first_fail_idx < first_revise_idx, (
        f"revise_start (idx={first_revise_idx}) must come after qa_fail (idx={first_fail_idx})"
    )

    # Round-1 QA must have passed (qa_pass after revise_start).
    qa_passes = _events_of_type(events, "qa_pass")
    assert qa_passes, "expected at least one qa_pass event"
    last_pass_idx = max(types.index(e["event_type"]) for e in qa_passes)  # type: ignore[attr-defined]
    # Find actual index of each qa_pass in the full list.
    qa_pass_indices = [i for i, e in enumerate(events) if e["event_type"] == "qa_pass"]
    assert qa_pass_indices, "no qa_pass events found"
    last_pass_idx = qa_pass_indices[-1]
    assert last_pass_idx > first_revise_idx, (
        "qa_pass must come after revise_start"
    )

    # run_complete must be the terminal run-level event.
    run_complete = _events_of_type(events, "run_complete")
    assert run_complete, "expected run_complete event"
    assert not _events_of_type(events, "run_partial"), (
        "run_partial must NOT be emitted on a successful weak→strong loop"
    )

    # run_complete must come after qa_pass.
    run_complete_idx = types.index("run_complete")
    assert run_complete_idx > last_pass_idx, "run_complete must come after qa_pass"

    # --- GA10: revise_done / synthesis_start / synthesis_done assertions ---

    # revise_done must be emitted once per completed revision round (round_idx > 0
    # causes the QA node to emit it before re-evaluating the claimset).
    revise_dones = _events_of_type(events, "revise_done")
    assert revise_dones, "expected at least one revise_done event after the revision cycle"

    # Ordering: revise_start must precede revise_done.
    first_revise_done_idx = types.index("revise_done")
    assert first_revise_done_idx > first_revise_idx, (
        f"revise_done (idx={first_revise_done_idx}) must come after "
        f"revise_start (idx={first_revise_idx})"
    )

    # Ordering: revise_done must precede the subsequent qa_pass.
    assert first_revise_done_idx < last_pass_idx, (
        f"revise_done (idx={first_revise_done_idx}) must come before "
        f"qa_pass (idx={last_pass_idx})"
    )

    # revise_done payload carries the round index.
    rd_payload = _payload(revise_dones[0])
    assert "round" in rd_payload, f"revise_done payload missing 'round': {rd_payload}"
    assert isinstance(rd_payload["round"], int), (
        f"revise_done 'round' must be int, got {type(rd_payload['round'])}"
    )
    assert rd_payload["round"] > 0, (
        f"revise_done 'round' must be > 0 (revision index), got {rd_payload['round']}"
    )

    # synthesis_start and synthesis_done must both be emitted (synthesis node runs
    # after write in the live graph and is always wired when deps are provided).
    assert "synthesis_start" in types, (
        "synthesis_start missing — synthesis node did not emit the start event"
    )
    assert "synthesis_done" in types, (
        "synthesis_done missing — synthesis node did not emit the done event"
    )
    # GB3: a real strong run produces a non-empty brief, so synthesis_done (not
    # synthesis_empty) is correct and its payload carries a positive count.
    assert "synthesis_empty" not in types, (
        "synthesis_empty must NOT fire on a strong run that produced a real brief"
    )
    synthesis_done_ev = _events_of_type(events, "synthesis_done")[0]
    assert _payload(synthesis_done_ev).get("sentences", 0) > 0, (
        f"synthesis_done must carry a positive sentences count: "
        f"{_payload(synthesis_done_ev)}"
    )

    # Ordering: synthesis_start → synthesis_done → (end of trace).
    synthesis_start_idx = types.index("synthesis_start")
    synthesis_done_idx = types.index("synthesis_done")
    assert synthesis_start_idx < synthesis_done_idx, (
        f"synthesis_start (idx={synthesis_start_idx}) must precede "
        f"synthesis_done (idx={synthesis_done_idx})"
    )

    # Ordering: run_complete must precede synthesis (synthesis is the very last step).
    assert run_complete_idx < synthesis_start_idx, (
        f"run_complete (idx={run_complete_idx}) must precede "
        f"synthesis_start (idx={synthesis_start_idx})"
    )

    # Payload integrity.
    _assert_all_payloads_serializable(events)
    _assert_no_api_keys(events)


# ---------------------------------------------------------------------------
# Test 2: partial run (analyst always produces weak claims → loop hits cap)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_trace_events_partial_run(tmp_path) -> None:
    """A loop that exhausts the revision cap emits run_partial (not run_complete)."""
    db, run_id = _run_graph(tmp_path, _fake_analyze_always_weak)
    events = db.trace_events_for_run(run_id)
    types = [e["event_type"] for e in events]

    # Must emit run_partial at the end.
    assert "run_partial" in types, "expected run_partial event when loop hits cap"
    # Must NOT emit run_complete on the degraded partial path.
    assert "run_complete" not in types, (
        "run_complete must NOT be emitted on a partial (cap-exhausted) run"
    )
    # Must have qa_fail events from each rejected round.
    assert "qa_fail" in types, "expected qa_fail events on a partial run"
    # Ensure no infinite loop — the graph must have terminated.
    # (The existing route termination guarantees this; we just confirm the test
    # completes and the run_partial fires once.)
    run_partials = _events_of_type(events, "run_partial")
    assert len(run_partials) == 1, f"expected exactly 1 run_partial, got {len(run_partials)}"

    # Payload integrity.
    _assert_all_payloads_serializable(events)
    _assert_no_api_keys(events)


# ---------------------------------------------------------------------------
# Test 2b: empty synthesis path emits synthesis_empty (GB3 — no false positive)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_trace_events_synthesis_empty_on_no_passed_claims(tmp_path) -> None:
    """A run with no passed claims must emit synthesis_empty, NOT synthesis_done.

    The always-weak analyst means QA rejects every claim → nothing is promoted →
    ``run_synthesis`` persists no brief. The synthesis node must label this
    honestly with ``synthesis_empty`` (杜绝假阳性) rather than firing a
    misleading ``synthesis_done``.
    """
    db, run_id = _run_graph(tmp_path, _fake_analyze_always_weak)
    events = db.trace_events_for_run(run_id)
    types = [e["event_type"] for e in events]

    # synthesis genuinely started.
    assert "synthesis_start" in types, "synthesis_start missing"
    # Honest terminal: empty, not done.
    assert "synthesis_empty" in types, (
        "synthesis_empty missing — empty synthesis must be labeled honestly"
    )
    assert "synthesis_done" not in types, (
        "synthesis_done must NOT fire when no brief was produced (false positive)"
    )

    # The empty payload carries sentences:0 so a consumer can read the count.
    empty_events = _events_of_type(events, "synthesis_empty")
    assert _payload(empty_events[0]).get("sentences") == 0, (
        f"synthesis_empty payload should carry sentences:0, got {_payload(empty_events[0])}"
    )

    _assert_all_payloads_serializable(events)
    _assert_no_api_keys(events)


# ---------------------------------------------------------------------------
# Test 3: collect_done payload contains sources_added count
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_collect_done_sources_added(tmp_path) -> None:
    """collect_done payload carries a numeric sources_added field."""
    db, run_id = _run_graph(tmp_path, _fake_analyze_strong_when_two_sources)
    events = db.trace_events_for_run(run_id)
    done_events = _events_of_type(events, "collect_done")
    assert done_events, "expected at least one collect_done event"
    for ev in done_events:
        p = _payload(ev)
        assert "sources_added" in p, f"collect_done payload missing sources_added: {p}"
        assert isinstance(p["sources_added"], int), (
            f"sources_added must be int, got {type(p['sources_added'])}"
        )


# ---------------------------------------------------------------------------
# Test 4: analyze_done payload carries claim_id and evidence_strength
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_analyze_done_payload_fields(tmp_path) -> None:
    """analyze_done payload includes claim_id and evidence_strength."""
    db, run_id = _run_graph(tmp_path, _fake_analyze_strong_when_two_sources)
    events = db.trace_events_for_run(run_id)
    done_events = _events_of_type(events, "analyze_done")
    assert done_events, "expected at least one analyze_done event"
    for ev in done_events:
        p = _payload(ev)
        assert p.get("claim_id"), f"analyze_done missing claim_id: {p}"
        assert p.get("evidence_strength") in ("strong", "moderate", "weak"), (
            f"analyze_done has unexpected evidence_strength: {p}"
        )


# ---------------------------------------------------------------------------
# Test 5: emit_run_error writes a terminal run_error event
# ---------------------------------------------------------------------------


def test_emit_run_error_writes_terminal_event(tmp_path) -> None:
    """emit_run_error persists exactly one run_error event with a concise message."""
    from mingjing.trace_events import emit_run_error

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")

    emit_run_error(db, run_id, message="Run failed: RuntimeError")

    events = db.trace_events_for_run(run_id)
    err = _events_of_type(events, "run_error")
    assert len(err) == 1, f"expected exactly one run_error, got {len(err)}"
    assert _payload(err[0])["message"] == "Run failed: RuntimeError"
    _assert_all_payloads_serializable(events)
    _assert_no_api_keys(events)


def test_emit_run_error_is_noop_without_db_or_run_id() -> None:
    """emit_run_error is a safe no-op when db/run_id are absent (compile/test path)."""
    from mingjing.trace_events import emit_run_error

    # Neither call should raise.
    emit_run_error(None, "rid", message="x")
    emit_run_error(object(), None, message="x")


def test_emit_qa_verdict_mixed_round_emits_pass_for_unflagged_claims(tmp_path):
    """A mixed round (some claims clean, some flagged) emits BOTH event kinds.

    Audit finding: runs with withheld claims never had a single qa_pass event,
    so the trail recorded only rejections — a judge asking "show me one claim's
    affirmative verdict" had nothing to point at. Unflagged claims now get a
    qa_pass even when the run-level verdict is reject; run-level issues
    (claim_id=None, e.g. LOW_COVERAGE) flag nobody.
    """
    from mingjing.trace_events import emit_qa_verdict

    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    run_id = db.create_run(category="c", competitors=["A"], goal="g")
    latest = [{"id": "claim-A"}, {"id": "claim-B"}]
    issues = [
        {"claim_id": "claim-B", "detail": "evidence strength scored weak", "code": "WEAK_EVIDENCE"},
        {"claim_id": None, "detail": "coverage low", "code": "LOW_COVERAGE"},
    ]
    emit_qa_verdict(
        db, run_id, verdict="reject", latest_claims=latest, issues=issues, round_idx=1
    )
    events = db.trace_events_for_run(run_id)
    passes = [e for e in events if e["event_type"] == "qa_pass"]
    fails = [e for e in events if e["event_type"] == "qa_fail"]
    assert len(passes) == 1
    assert json.loads(passes[0]["payload_json"])["claim_ids"] == ["claim-A"]
    assert len(fails) == 2, "one qa_fail per issue, including the run-level one"
