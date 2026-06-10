"""Collect-node thin-source gate.

Root cause (Feishu live run 2026-06-03): JS-rendered official pages
(feishu.cn, larksuite.com) fetch HTTP 200 but BeautifulSoup extracts only a
~8-char loading shell. Those near-empty pages were persisted as citable
sources, so the analyst grounded pricing/feature claims against them and the QA
gate correctly rejected every claim (``value required sub-fields not found in
cited sources``) — 0 passed claims despite 14 extracted.

The gate drops fetches whose extracted text is below ``min_source_chars`` BEFORE
they become citable, so the analyst grounds against the content-rich
third-party sources (36kr, woshipm) that were collected alongside the shells.
A ``source_skipped`` trace event records each drop (no silent truncation).
"""

import uuid

from mingjing.db import Database
from mingjing.graph import GraphDeps
from mingjing.graph_nodes import make_collect_node


def _run_collect(db: Database, run_id: str, results, *, min_chars: int):
    """Drive the live collect node with a fake collect_fn returning ``results``."""

    class _Settings:
        mode = "live_first"
        min_source_chars = min_chars

    def fake_collect_fn(query, *, cache=None, source_cap=1, mode="live_first"):
        return results

    deps = GraphDeps(db=db, cache=None, settings=_Settings(), collect_fn=fake_collect_fn)
    collect = make_collect_node(deps)
    state = {
        "run_id": run_id,
        "db": db,
        "tasks": [{"competitor": "飞书", "field": "pricing_model", "query": "飞书 定价"}],
        "revision_round": 0,
        "budget_calls": 0,
    }
    return collect(state)


def _result(text: str, url: str):
    return {
        "fetched": True,
        "url": url,
        "text": text,
        "title": "t",
        "source_mode": "LIVE",
        "fetched_at": 1.0,
        "content_hash": uuid.uuid4().hex[:16],
    }


def test_thin_spa_shell_is_not_persisted_but_rich_source_is(tmp_path) -> None:
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="c", competitors=["飞书"], goal="g")

    thin = _result("飞书", "https://www.feishu.cn/?from_site=lark")  # ~6 chars: SPA shell
    rich = _result("飞书企业版定价为每用户每月 30 元，" * 30, "https://www.36kr.com/p/123")

    out = _run_collect(db, run_id, [thin, rich], min_chars=100)

    # Only the rich source is persisted and returned as citable.
    persisted = db.sources_for_run(run_id)
    assert len(out["sources"]) == 1, "thin shell must not be returned as a citable source"
    rich_id = out["sources"][0]["source_id"]
    row = db.get_source(rich_id)
    assert row is not None and "36kr" in (row["url"] or "")
    assert all("feishu.cn/?from_site" not in (s.get("url") or "") for s in persisted)


def test_skipped_thin_source_emits_trace_event(tmp_path) -> None:
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="c", competitors=["飞书"], goal="g")

    thin = _result("飞书", "https://www.feishu.cn/?from_site=lark")
    _run_collect(db, run_id, [thin], min_chars=100)

    events = db.trace_events_for_run(run_id)
    skipped = [e for e in events if e["event_type"] == "source_skipped"]
    assert len(skipped) == 1, "a dropped thin source must be observable, not silent"
    import json

    payload = json.loads(skipped[0]["payload_json"])
    assert payload["reason"] == "content_too_thin"
    assert payload["chars"] < 100
    assert "feishu.cn" in payload.get("url", "")


def test_rich_source_above_threshold_is_kept(tmp_path) -> None:
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="c", competitors=["飞书"], goal="g")

    rich = _result("x" * 250, "https://www.woshipm.com/evaluating/1.html")
    out = _run_collect(db, run_id, [rich], min_chars=100)
    assert len(out["sources"]) == 1


def test_short_snippet_source_bypasses_thin_gate(tmp_path) -> None:
    """Snippet-as-evidence rows (from_snippet) are legitimately short and must be
    persisted even below min_source_chars — the search summary IS the evidence,
    and raw_text == snippet keeps the QA HALLUCINATED_SNIPPET check self-consistent."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="c", competitors=["飞书"], goal="g")

    snip = {
        "fetched": True,
        "from_snippet": True,
        "url": "https://example.com/p",
        "text": "飞书企业版 30 元/月",  # < 100 chars, but a real snippet
        "title": "t",
        "source_mode": "SNIPPET",
        "fetched_at": None,
        "content_hash": "deadbeef",
    }
    out = _run_collect(db, run_id, [snip], min_chars=100)

    assert len(out["sources"]) == 1, "snippet evidence must bypass the thin-source gate"
    row = db.get_source(out["sources"][0]["source_id"])
    assert row is not None
    assert row["source_mode"] == "SNIPPET"
    assert row["raw_text"] == "飞书企业版 30 元/月"  # raw_text == snippet (QA self-consistency)
