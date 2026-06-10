"""Live analyze-node wiring tests (FIX 1 + FIX 2).

FIX 1: the evidence text handed to the analyst must carry each source's id so a
real model can cite it in ``evidence_ref``; otherwise ``filter_evidence_refs``
drops every ref (the ids never appear in the text the model saw) and every claim
collapses to weak/empty.

FIX 2: the live analyze node calls ``analyze_fn`` once per task, so the budget
must grow by the number of invocations, not by a flat +1.
"""

import uuid

from mingjing.db import Database
from mingjing.graph import GraphDeps
from mingjing.graph_nodes import make_analyze_node


def _seed_source(db: Database, run_id: str, *, field: str, competitor: str, text: str) -> str:
    sid = str(uuid.uuid4())
    db.append_source(
        {
            "id": sid,
            "run_id": run_id,
            "url": "https://example.com/p",
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


def _state(db: Database, run_id: str, tasks, sources):
    return {
        "run_id": run_id,
        "db": db,
        "tasks": tasks,
        "sources": sources,
        "budget_calls": 0,
    }


def test_source_ids_present_in_evidence_and_survive_filter(tmp_path) -> None:
    """A model that echoes back the ids it saw keeps them after filtering."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=["Acme"], goal="g")
    sid = _seed_source(db, run_id, field="pricing", competitor="Acme", text="Pro is $10/mo.")

    seen: dict[str, str] = {}

    def fake_analyze(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        seen["evidence_text"] = evidence_text
        seen["source_ids"] = source_ids
        # A real model can only cite ids it actually saw in the evidence text.
        cited = [i for i in source_ids if i in evidence_text]
        from mingjing.agents.analyst import filter_evidence_refs

        payload = {
            "statement": "Pro is $10/mo.",
            "claim_type": "fact",
            "value": {"price": 10},
            "evidence_ref": cited,
        }
        return filter_evidence_refs(payload, source_ids)

    deps = GraphDeps(db=db, cache=None, settings=None, collect_fn=lambda *a, **k: [], analyze_fn=fake_analyze)
    node = make_analyze_node(deps)
    tasks = [{"field": "pricing", "competitor": "Acme"}]
    sources = [{"source_id": sid, "field": "pricing", "competitor": "Acme"}]

    out = node(_state(db, run_id, tasks, sources))

    assert sid in seen["evidence_text"], "source id must appear in evidence text"
    claim = out["claims"][0]
    ref_ids = [e["source_id"] for e in claim["evidence"] if e["relevance"] == "supports"]
    assert sid in ref_ids, "the cited id must survive filter_evidence_refs"


def test_budget_grows_by_number_of_analyze_invocations(tmp_path) -> None:
    """N tasks invoking analyze_fn must raise budget_calls by N (not +1)."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=["Acme", "BetaCo", "Gamma"], goal="g")

    tasks = []
    sources = []
    for comp in ("Acme", "BetaCo", "Gamma"):
        sid = _seed_source(db, run_id, field="pricing", competitor=comp, text="x")
        tasks.append({"field": "pricing", "competitor": comp})
        sources.append({"source_id": sid, "field": "pricing", "competitor": comp})

    calls = {"n": 0}

    def fake_analyze(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        calls["n"] += 1
        return {"statement": "s", "claim_type": "fact", "value": {}, "evidence_ref": []}

    deps = GraphDeps(db=db, cache=None, settings=None, collect_fn=lambda *a, **k: [], analyze_fn=fake_analyze)
    node = make_analyze_node(deps)

    out = node(_state(db, run_id, tasks, sources))

    assert calls["n"] == 3
    assert out["budget_calls"] == 3
