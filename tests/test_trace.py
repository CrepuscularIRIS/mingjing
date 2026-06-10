import os

from mingjing.db import Database
from mingjing.trace import log_event, log_llm


def _fresh_db(tmp_path) -> tuple[Database, str]:
    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    rid = db.create_run(category="notes", competitors=["A"], goal="g")
    return db, rid


def test_log_event_writes_one_row(tmp_path):
    db, rid = _fresh_db(tmp_path)
    log_event(db, rid, agent="collector", node="collect", event_type="fetch_done",
              payload={"url": "http://x"})
    rows = db.trace_events_for_run(rid)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "fetch_done"
    assert rows[0]["agent"] == "collector"


def test_log_llm_writes_one_row_with_tokens(tmp_path):
    db, rid = _fresh_db(tmp_path)
    log_llm(
        db,
        rid,
        agent="analyst",
        model="abab6.5s-chat",
        messages=[{"role": "user", "content": "hi"}],
        output_text="ok",
        usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    )
    rows = db.llm_calls_for_run(rid)
    assert len(rows) == 1
    assert rows[0]["output_text"] == "ok"
    assert rows[0]["total_tokens"] == 4


def test_api_key_redacted_from_payloads(tmp_path):
    db, rid = _fresh_db(tmp_path)
    secret = "sk-super-secret-minimax-value"
    os.environ["MINIMAX_API_KEY"] = secret

    log_event(db, rid, agent="collector", node="collect", event_type="call",
              payload={"auth": f"Bearer {secret}", "note": "ok"})
    log_llm(
        db,
        rid,
        agent="analyst",
        model="m",
        messages=[{"role": "system", "content": f"key={secret}"}],
        output_text=f"leaked {secret}",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    )

    ev = db.trace_events_for_run(rid)[0]
    call = db.llm_calls_for_run(rid)[0]
    assert secret not in ev["payload_json"]
    assert secret not in call["prompt_json"]
    assert secret not in (call["output_text"] or "")
