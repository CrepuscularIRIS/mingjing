"""Concurrency stress test for Database shared-connection safety.

Verifies that concurrent reads and writes on a single Database instance do NOT
raise sqlite3.InterfaceError or sqlite3.ProgrammingError ("recursive use of
cursors" / "object used in wrong thread"). The test surfaces the race introduced
by read methods that call self._conn.execute without holding _WRITE_LOCK.

RED (pre-fix): this test FAILS — the unprotected reads collide with writes.
GREEN (post-fix): all read methods hold _WRITE_LOCK; the test passes.
"""

import sqlite3
import threading
import time
import uuid

from mingjing.db import Database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(run_id: str, idx: int) -> dict:
    return {
        "id": f"{run_id}-src-{idx}-{uuid.uuid4().hex[:6]}",
        "run_id": run_id,
        "url": f"https://example.com/{idx}",
        "title": f"Source {idx}",
        "source_type": "web",
        "source_mode": "LIVE",
        "fetched_at": time.time(),
        "content_hash": uuid.uuid4().hex,
        "raw_text": "test content " * 10,
        "meta_json": "{}",
    }


def _make_claim(run_id: str, claim_id: str, version: int = 1) -> dict:
    return {
        "id": claim_id,
        "run_id": run_id,
        "competitor": "A",
        "schema_field": "pricing_model",
        "claim_type": "factual",
        "statement": f"claim v{version}",
        "value_json": "{}",
        "evidence_json": "[]",
        "based_on_json": "[]",
        "evidence_strength": "moderate",
        "status": "pass",
        "version": version,
        "produced_by": "analyst",
    }


def _make_trace(run_id: str, idx: int) -> dict:
    return {
        "run_id": run_id,
        "agent": "test-agent",
        "node": "test-node",
        "event_type": "test",
        "payload_json": f'{{"i": {idx}}}',
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_concurrent_reads_and_writes_no_interface_error(tmp_path):
    """Stress test: 8 threads (4 writers + 4 readers) run 200 iterations each.

    Any sqlite3 race-signature error collected from any thread causes an
    assertion failure.
    """
    db_path = str(tmp_path / "concurrency_test.db")
    db = Database(db_path)
    db.init_schema()

    # Seed: one run, a few initial sources/trace events so readers have data.
    run_id = db.create_run(
        category="tech",
        competitors=["A", "B"],
        goal="test concurrency",
        domain=None,
        depth="quick",
    )
    for i in range(5):
        db.append_source(_make_source(run_id, i))
        db.insert_trace_event(_make_trace(run_id, i))

    # Seed a claim and a fixed source so claim_versions / get_source return data.
    seeded_claim_id = uuid.uuid4().hex
    db.append_claim(_make_claim(run_id, seeded_claim_id, version=1))
    seeded_source = _make_source(run_id, 9999)
    db.append_source(seeded_source)
    seeded_source_id = seeded_source["id"]

    errors: list[Exception] = []
    ITERATIONS = 200
    barrier = threading.Barrier(8)

    def writer_fn(thread_idx: int) -> None:
        barrier.wait()  # all threads start simultaneously
        for i in range(ITERATIONS):
            try:
                db.append_source(_make_source(run_id, 1000 * thread_idx + i))
                db.insert_trace_event(_make_trace(run_id, 1000 * thread_idx + i))
            except (sqlite3.InterfaceError, sqlite3.ProgrammingError, sqlite3.DatabaseError) as exc:
                errors.append(exc)

    def reader_fn() -> None:
        barrier.wait()
        for _ in range(ITERATIONS):
            try:
                db.trace_events_for_run(run_id)
                db.sources_for_run(run_id)
                db.llm_calls_for_run(run_id)
                db.get_run(run_id)
                db.run_exists(run_id)
                db.list_runs()
                db.claims_for_run(run_id)
                db.latest_claims_for_run(run_id)
                db.last_round_issues_for_run(run_id)
                db.get_synthesis(run_id)
                db.pragma("journal_mode")
                db.claim_versions(run_id, seeded_claim_id)
                db.get_source(seeded_source_id)
            except (sqlite3.InterfaceError, sqlite3.ProgrammingError, sqlite3.DatabaseError) as exc:
                errors.append(exc)

    threads = [threading.Thread(target=writer_fn, args=(i,)) for i in range(4)]
    threads += [threading.Thread(target=reader_fn) for _ in range(4)]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    # Surface the first error with a helpful message.
    if errors:
        raise AssertionError(
            f"{len(errors)} thread error(s) detected. First: {type(errors[0]).__name__}: {errors[0]}"
        )
