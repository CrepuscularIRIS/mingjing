"""Offline tests for the post-write synthesis node (Task 6, M4 backend).

The synthesis node runs AFTER ``write`` over the QA-passed claim ledger, drives
<=3 schema LLM calls, projects the merged payload, and persists it to the
append-only ``syntheses`` table. Synthesis is NON-FATAL: any exception logs a
trace event and returns without raising, so the run still reaches a terminal
state and the frontend falls back to the deterministic ledger.

These tests stub ``call_llm`` (no network, no live LLM):
- a returning stub -> a ``syntheses`` row is persisted and the run terminates.
- a RAISING stub -> the exception does NOT propagate; the run still terminates
  and no ``syntheses`` row is written (the ledger is the fallback).
"""

from typing import Any

from mingjing import synthesis as synthesis_mod
from mingjing.db import Database


def _seed_passed_claim(db: Database, run_id: str, claim_id: str = "c1") -> None:
    db.append_claim(
        {
            "id": claim_id,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing_model",
            "claim_type": "fact",
            "statement": "Pro tier costs $10 per month",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "strong",
            "status": "pass",
            "version": 1,
            "produced_by": "analyst",
        }
    )


def test_run_synthesis_persists_row(tmp_path, monkeypatch):
    """A returning stub -> run_synthesis projects + persists a syntheses row."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    _seed_passed_claim(db, rid)

    def fake_call_llm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"bluf": {"text": "Acme leads on price", "claim_ids": ["c1"]}}

    monkeypatch.setattr(synthesis_mod, "call_llm", fake_call_llm)
    synthesis_mod.run_synthesis(db, rid, settings=None)

    out = db.get_synthesis(rid)
    assert out is not None
    assert "referenced_claim_ids" in out
    assert "c1" in out["referenced_claim_ids"]


def test_run_synthesis_no_passed_claims_is_noop(tmp_path):
    """No passing claims -> return early, no syntheses row (gap empty state)."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    synthesis_mod.run_synthesis(db, rid, settings=None)
    assert db.get_synthesis(rid) is None


def test_run_synthesis_non_fatal_on_raise(tmp_path, monkeypatch):
    """A RAISING stub must NOT propagate; run_synthesis swallows + logs."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    _seed_passed_claim(db, rid)

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("MiniMax JSON truncated")

    monkeypatch.setattr(synthesis_mod, "call_llm", boom)
    # Must not raise.
    synthesis_mod.run_synthesis(db, rid, settings=None)
    # No syntheses row (the ledger is the fallback).
    assert db.get_synthesis(rid) is None


def _drive_full_run(db: Database, run_id: str, tmp_path) -> dict:
    """Drive a full offline run to a PASS (reusing the smoke-gate fixtures so the
    weak->strong loop reaches strong/pass and claims are promoted)."""
    from test_loop_smoke import (
        PAGE_A_TEXT,
        PAGE_A_URL,
        PAGE_B_TEXT,
        PAGE_B_URL,
        _fake_analyze_fn,
        _fake_collect_fn,
    )

    from mingjing.collector.cache import Cache
    from mingjing.collector.fetch import FetchResult
    from mingjing.graph import GraphDeps, build_graph

    with Cache(str(tmp_path / "cache.db")) as cache:
        cache.put(FetchResult(text=PAGE_A_TEXT, url=PAGE_A_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=PAGE_B_TEXT, url=PAGE_B_URL, source_mode="LIVE"))
        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=None,
            collect_fn=_fake_collect_fn,
            analyze_fn=_fake_analyze_fn,
        )
        graph = build_graph(deps=deps)
        return graph.invoke(
            {
                "run_id": run_id,
                "db": db,
                "intake": {
                    "category": "cat",
                    "competitors": ["Acme"],
                    "goal": "g",
                    "fields": ["pricing_model"],
                },
            }
        )


def test_synthesis_node_runs_after_write_and_is_non_fatal(tmp_path, monkeypatch):
    """The graph reaches a terminal state with synthesis wired write -> synthesis
    -> END, even when the synthesis LLM stub RAISES (non-fatal)."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=["Acme"], goal="g")

    # Make the synthesis LLM call RAISE — must be swallowed (non-fatal).
    def boom(*args, **kwargs):
        raise RuntimeError("MiniMax JSON truncated")

    monkeypatch.setattr(synthesis_mod, "call_llm", boom)

    final = _drive_full_run(db, run_id, tmp_path)

    # The run still produced a report (write ran) and reached the synthesis phase.
    assert final.get("report")
    assert final.get("phase") == "synthesis"
    # The raising synthesis stub did not propagate; no syntheses row persisted.
    assert db.get_synthesis(run_id) is None


def test_synthesis_node_persists_row_with_stubbed_llm(tmp_path, monkeypatch):
    """With a returning synthesis stub, a full passing run persists a syntheses row."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=["Acme"], goal="g")

    def fake_call_llm(db, run_id, *, agent, messages, schema, settings, untrusted_content=None):
        # Untrusted content must NOT be set — claims are trusted.
        assert untrusted_content is None
        latest = db.latest_claims_for_run(run_id)
        cid = latest[0]["id"] if latest else "c1"
        return {"bluf": {"text": "Acme leads on price", "claim_ids": [cid]}}

    monkeypatch.setattr(synthesis_mod, "call_llm", fake_call_llm)

    _drive_full_run(db, run_id, tmp_path)

    out = db.get_synthesis(run_id)
    assert out is not None
    assert "referenced_claim_ids" in out
