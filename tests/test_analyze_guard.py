"""The analyze node must survive a defective analyst payload (C1).

The live LLM path can yield ``None`` or a non-dict / empty dict. Building a claim
from such a payload would call ``.get`` on a non-dict (``AttributeError``,
halting the run) or persist a zero-evidence row that bypasses Pydantic and
reaches QA. The guard logs + traces a skipped field and continues, so the graph
still reaches ``write`` and simply produces no claim for that field.
"""

import pytest

from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph

COMPETITOR = "Acme"
FIELD = "pricing_model"


def _fake_collect_fn(query, *, cache, source_cap, mode="live_first"):
    """One real, persistable source so the analyze node reaches ``analyze_fn``."""
    return [
        {
            "url": "https://acme.example.com/pricing",
            "title": "Acme pricing",
            "fetched": True,
            "source_mode": "CACHED",
            "text": "Official Acme pricing: Pro tier costs $10 per month.",
            "content_hash": "h",
            "fetched_at": 1.0,
        }
    ]


def _run_with_analyze_fn(tmp_path, analyze_fn):
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")
    deps = GraphDeps(
        db=db,
        cache=None,
        settings=None,
        collect_fn=_fake_collect_fn,
        analyze_fn=analyze_fn,
    )
    graph = build_graph(deps=deps)
    final = graph.invoke(
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
    return db, run_id, final


@pytest.mark.parametrize("bad_payload", [None, {}])
def test_bad_analyst_payload_skips_claim_and_reaches_write(tmp_path, bad_payload) -> None:
    def analyze_fn(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        return bad_payload

    db, run_id, final = _run_with_analyze_fn(tmp_path, analyze_fn)

    # The run did not raise and reached the writer (the live graph then runs the
    # non-fatal post-write synthesis node: write -> synthesis -> END).
    assert final["phase"] in ("write", "synthesis")
    # No claim was persisted for the field (no zero-evidence row reached the DB).
    assert db.claims_for_run(run_id) == []
    # A trace event records the skipped field for observability.
    events = db.trace_events_for_run(run_id)
    assert any(e["event_type"] == "claim_skipped" for e in events)


# ---------------------------------------------------------------------------
# Fix — analyze_fn that RAISES must not crash the run (C2)
# ---------------------------------------------------------------------------

import uuid  # noqa: E402  (needed for the multi-field helper below)

from mingjing.graph_nodes import make_analyze_node  # noqa: E402


def _seed_source(db, run_id, *, field, competitor, text="evidence"):
    sid = str(uuid.uuid4())
    db.append_source(
        {
            "id": sid,
            "run_id": run_id,
            "url": "https://example.com",
            "title": "t",
            "source_type": "web",
            "source_mode": "LIVE",
            "fetched_at": 1.0,
            "content_hash": "h",
            "raw_text": text,
            "meta_json": "{}",
        }
    )
    return sid


def test_analyze_node_skips_field_when_analyze_fn_raises(tmp_path) -> None:
    """analyze_fn that raises ValueError must not crash the node.

    Scenario: two fields — one raises, one returns a valid payload.
    Expected: node returns normally with phase=="analyze", no claim for the
    raising field, one claim for the good field, and a claim_skipped trace
    event carrying a reason that names the exception type.
    """
    from mingjing.db import Database
    from mingjing.graph import GraphDeps

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")

    field_bad = "pricing_model"
    field_good = "support_tier"

    sid_bad = _seed_source(db, run_id, field=field_bad, competitor=COMPETITOR, text="bad evidence")
    sid_good = _seed_source(db, run_id, field=field_good, competitor=COMPETITOR, text="good ev")

    def analyze_fn(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        if field == field_bad:
            raise ValueError("boom — simulated JSON truncation")
        return {"statement": "Good tier: Pro.", "claim_type": "fact", "value": {}, "evidence_ref": []}

    deps = GraphDeps(
        db=db,
        cache=None,
        settings=None,
        collect_fn=lambda *a, **k: [],
        analyze_fn=analyze_fn,
    )
    node = make_analyze_node(deps)
    tasks = [
        {"field": field_bad, "competitor": COMPETITOR},
        {"field": field_good, "competitor": COMPETITOR},
    ]
    sources = [
        {"source_id": sid_bad, "field": field_bad, "competitor": COMPETITOR},
        {"source_id": sid_good, "field": field_good, "competitor": COMPETITOR},
    ]
    state = {
        "run_id": run_id,
        "db": db,
        "tasks": tasks,
        "sources": sources,
        "budget_calls": 0,
        "intake": {"fields": [field_bad, field_good]},
    }

    # Must NOT raise — the node catches the exception internally.
    out = node(state)

    assert out["phase"] == "analyze"

    # No claim for the raising field.
    all_claims = db.claims_for_run(run_id)
    bad_claims = [c for c in all_claims if c["schema_field"] == field_bad]
    good_claims = [c for c in all_claims if c["schema_field"] == field_good]
    assert bad_claims == [], "must not persist a claim for the field that raised"
    assert len(good_claims) == 1, "the good field must still produce a claim"

    # A claim_skipped trace event must be emitted with the exc-type in reason.
    import json as _json
    events = db.trace_events_for_run(run_id)
    skipped = [e for e in events if e["event_type"] == "claim_skipped"]
    assert skipped, "expected at least one claim_skipped event"
    reasons = [
        _json.loads(e.get("payload_json", "{}")).get("reason", "")
        for e in skipped
    ]
    assert any("analyst_call_raised" in r for r in reasons), (
        f"expected reason containing 'analyst_call_raised', got: {reasons}"
    )
