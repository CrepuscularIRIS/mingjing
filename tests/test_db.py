import json

import pytest

from mingjing.db import Database


def test_wal_and_append_only(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    db.init_schema()
    rid = db.create_run(category="notes", competitors=["A", "B"], goal="pricing")
    db.append_claim(
        {
            "id": "C1",
            "run_id": rid,
            "competitor": "A",
            "schema_field": "pricing_model",
            "claim_type": "fact",
            "statement": "x",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "weak",
            "status": "draft",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    rows = db.claims_for_run(rid)
    assert len(rows) == 1 and rows[0]["status"] == "draft"
    assert db.pragma("journal_mode").lower() == "wal"


def test_based_on_round_trip(tmp_path):
    from mingjing.db import Database
    db = Database(f"{tmp_path}/m.db")
    db.init_schema()
    rid = db.create_run(category="x", competitors=["Acme"], goal="g")
    db.append_claim({"id": "s1", "run_id": rid, "competitor": "Acme", "schema_field": "swot",
                     "claim_type": "inference", "statement": "Acme is squeezed on price",
                     "value_json": "{}", "evidence_json": "[]", "based_on_json": '["c1","c2"]',
                     "evidence_strength": "moderate", "status": "pass", "version": 1, "produced_by": "synthesis"})
    rows = db.latest_claims_for_run(rid)
    s = [r for r in rows if r["id"] == "s1"][0]
    import json
    assert json.loads(s["based_on_json"]) == ["c1", "c2"]


class TestGetRunAndStatus:
    """Unit tests for Database.get_run and Database.set_run_status."""

    @pytest.fixture()
    def db(self, tmp_path):
        d = Database(str(tmp_path / "runs.db"))
        d.init_schema()
        return d

    def test_get_run_round_trip(self, db):
        """get_run returns the run row with competitors decoded to a list."""
        rid = db.create_run(
            category="CRM", competitors=["Acme", "BetaCo"], goal="compare pricing"
        )
        run = db.get_run(rid)
        assert run is not None
        assert run["id"] == rid
        assert run["category"] == "CRM"
        assert run["competitors"] == ["Acme", "BetaCo"]
        assert run["goal"] == "compare pricing"
        assert run["status"] == "running"
        assert isinstance(run["created_at"], float)

    def test_get_run_unknown_returns_none(self, db):
        """get_run returns None for a run_id that does not exist."""
        assert db.get_run("does-not-exist") is None

    def test_set_run_status_updates_status(self, db):
        """set_run_status mutates only the status column."""
        rid = db.create_run(category="cat", competitors=["X"], goal="g")
        assert db.get_run(rid)["status"] == "running"
        db.set_run_status(rid, "complete")
        run = db.get_run(rid)
        assert run["status"] == "complete"
        # Other columns are untouched.
        assert run["competitors"] == ["X"]
        assert run["goal"] == "g"


class TestClaimVersions:
    """Unit tests for Database.claim_versions (targeted parameterized query)."""

    @pytest.fixture()
    def db(self, tmp_path):
        d = Database(str(tmp_path / "cv.db"))
        d.init_schema()
        return d

    @pytest.fixture()
    def run_id(self, db):
        return db.create_run(category="CRM", competitors=["Acme"], goal="pricing")

    def _claim_row(self, claim_id: str, run_id: str, version: int, strength: str) -> dict:
        return {
            "id": claim_id,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing",
            "claim_type": "fact",
            "statement": f"Statement v{version}.",
            "value_json": "{}",
            "evidence_json": json.dumps([f"src{version}"]),
            "based_on_json": "[]",
            "evidence_strength": strength,
            "status": "pass",
            "version": version,
            "produced_by": "analyst",
        }

    def test_returns_all_versions_ordered_asc(self, db, run_id):
        """claim_versions returns all rows for the claim, oldest first."""
        cid = "claim-aaa"
        db.append_claim(self._claim_row(cid, run_id, version=1, strength="weak"))
        db.append_claim(self._claim_row(cid, run_id, version=2, strength="strong"))

        rows = db.claim_versions(run_id, cid)
        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[0]["evidence_strength"] == "weak"
        assert rows[1]["version"] == 2
        assert rows[1]["evidence_strength"] == "strong"

    def test_returns_empty_for_unknown_claim(self, db, run_id):
        """claim_versions returns [] for a claim_id that does not exist."""
        rows = db.claim_versions(run_id, "nonexistent-claim")
        assert rows == []

    def test_returns_empty_for_unknown_run(self, db, run_id):
        """claim_versions returns [] when the run_id does not match."""
        cid = "claim-bbb"
        db.append_claim(self._claim_row(cid, run_id, version=1, strength="weak"))

        rows = db.claim_versions("wrong-run-id", cid)
        assert rows == []

    def test_does_not_return_other_claims(self, db, run_id):
        """claim_versions only returns rows for the requested claim_id."""
        cid_a = "claim-ccc"
        cid_b = "claim-ddd"
        db.append_claim(self._claim_row(cid_a, run_id, version=1, strength="weak"))
        db.append_claim(self._claim_row(cid_b, run_id, version=1, strength="strong"))

        rows = db.claim_versions(run_id, cid_a)
        assert len(rows) == 1
        assert rows[0]["id"] == cid_a

    def test_single_version_claim(self, db, run_id):
        """claim_versions works correctly when a claim has exactly one version."""
        cid = "claim-eee"
        db.append_claim(self._claim_row(cid, run_id, version=1, strength="moderate"))

        rows = db.claim_versions(run_id, cid)
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["evidence_strength"] == "moderate"


class TestListRuns:
    """Unit tests for Database.list_runs (recent runs + passed_claims count)."""

    @pytest.fixture()
    def db(self, tmp_path) -> Database:
        d = Database(str(tmp_path / "lr.db"))
        d.init_schema()
        return d

    @staticmethod
    def _claim(cid, run_id, *, status, version=1):
        return {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing",
            "claim_type": "fact",
            "statement": "s",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "strong",
            "status": status,
            "version": version,
            "produced_by": "analyst",
        }

    def test_empty_db_returns_empty_list(self, db):
        assert db.list_runs() == []

    def test_returns_runs_newest_first(self, db):
        first = db.create_run(category="A", competitors=["X"], goal="g")
        second = db.create_run(category="B", competitors=["Y", "Z"], goal="g")
        runs = db.list_runs()
        assert [r["run_id"] for r in runs] == [second, first]

    def test_competitors_decoded_to_list(self, db):
        rid = db.create_run(category="A", competitors=["X", "Y"], goal="g")
        runs = db.list_runs()
        assert runs[0]["run_id"] == rid
        assert runs[0]["competitors"] == ["X", "Y"]

    def test_passed_claims_counts_latest_pass_only(self, db):
        rid = db.create_run(category="A", competitors=["X"], goal="g")
        db.append_claim(self._claim("c1", rid, status="pass"))
        db.append_claim(self._claim("c2", rid, status="fail"))
        # c3 starts fail then is superseded by a pass version → counts once.
        db.append_claim(self._claim("c3", rid, status="fail", version=1))
        db.append_claim(self._claim("c3", rid, status="pass", version=2))
        runs = db.list_runs()
        assert runs[0]["passed_claims"] == 2

    def test_respects_limit(self, db):
        for _ in range(5):
            db.create_run(category="A", competitors=["X"], goal="g")
        assert len(db.list_runs(limit=3)) == 3


class TestDeleteRun:
    """Unit tests for Database.delete_run (purge run + all child rows)."""

    @pytest.fixture()
    def db(self, tmp_path) -> Database:
        d = Database(str(tmp_path / "del.db"))
        d.init_schema()
        return d

    @staticmethod
    def _claim(cid, run_id):
        return {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing",
            "claim_type": "fact",
            "statement": "s",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "strong",
            "status": "pass",
            "version": 1,
            "produced_by": "analyst",
        }

    def test_deletes_run_and_all_child_rows(self, db):
        rid = db.create_run(category="A", competitors=["X"], goal="g")
        db.append_claim(self._claim("c1", rid))
        db.append_source({"id": "src1", "run_id": rid, "url": "http://x"})
        db.append_evidence_chunk(
            {"id": "ev1", "run_id": rid, "source_id": "src1", "text": "chunk"}
        )
        db.append_qc_report(
            {"id": "qc1", "run_id": rid, "claim_id": "c1", "verdict": "pass"}
        )
        db.append_revision_task(
            {"id": "rt1", "run_id": rid, "claim_id": "c1", "assignee": "collector"}
        )
        db.insert_trace_event({"run_id": rid, "event_type": "intake_done"})
        db.insert_llm_call({"run_id": rid, "model": "fake"})
        db.append_synthesis(rid, {"referenced_claim_ids": ["c1"], "brief": "b"})

        assert db.run_exists(rid) is True

        db.delete_run(rid)

        assert db.run_exists(rid) is False
        assert db.get_run(rid) is None
        assert db.claims_for_run(rid) == []
        assert db.sources_for_run(rid) == []
        assert db.trace_events_for_run(rid) == []
        assert db.llm_calls_for_run(rid) == []
        assert db.get_synthesis(rid) is None
        # Child tables with no dedicated reader: assert via raw query.
        for table in ("evidence_chunks", "qc_reports", "revision_tasks"):
            cur = db._conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE run_id = ?", (rid,)
            )
            assert cur.fetchone()["n"] == 0

    def test_does_not_touch_other_runs(self, db):
        keep = db.create_run(category="A", competitors=["X"], goal="g")
        drop = db.create_run(category="B", competitors=["Y"], goal="g")
        db.append_claim(self._claim("k1", keep))
        db.append_claim(self._claim("d1", drop))
        db.append_source({"id": "ksrc", "run_id": keep, "url": "http://k"})

        db.delete_run(drop)

        assert db.run_exists(keep) is True
        assert [c["id"] for c in db.claims_for_run(keep)] == ["k1"]
        assert [s["id"] for s in db.sources_for_run(keep)] == ["ksrc"]
        assert db.run_exists(drop) is False
        assert db.claims_for_run(drop) == []

    def test_delete_unknown_run_is_noop(self, db):
        # No rows, no error.
        db.delete_run("does-not-exist")


class TestReapStaleRunning:
    """Unit tests for Database.reap_stale_running (orphaned-running reaper)."""

    @pytest.fixture()
    def db(self, tmp_path) -> Database:
        d = Database(str(tmp_path / "reap.db"))
        d.init_schema()
        return d

    def _age_run(self, db, run_id, age_s):
        """Backdate a run's created_at by age_s seconds (test-only helper)."""
        import time as _time

        with db._conn:
            db._conn.execute(
                "UPDATE runs SET created_at = ? WHERE id = ?",
                (_time.time() - age_s, run_id),
            )

    def test_reaps_only_old_running_runs(self, db):
        old_running = db.create_run(category="A", competitors=["X"], goal="g")
        fresh_running = db.create_run(category="A", competitors=["X"], goal="g")
        old_complete = db.create_run(category="A", competitors=["X"], goal="g")
        db.set_run_status(old_complete, "complete")

        self._age_run(db, old_running, age_s=7200)  # 2h old
        self._age_run(db, old_complete, age_s=7200)  # old but not running

        reaped = db.reap_stale_running(older_than_s=3600)  # 1h threshold

        assert reaped == [old_running]
        assert db.get_run(old_running)["status"] == "error"
        # Fresh running run is untouched.
        assert db.get_run(fresh_running)["status"] == "running"
        # Already-complete run is untouched.
        assert db.get_run(old_complete)["status"] == "complete"

    def test_returns_empty_when_none_stale(self, db):
        rid = db.create_run(category="A", competitors=["X"], goal="g")
        assert db.reap_stale_running(older_than_s=3600) == []
        assert db.get_run(rid)["status"] == "running"


# ---------------------------------------------------------------------------
# RC5: run_id indexes + idempotent init_schema
# ---------------------------------------------------------------------------


class TestRunIdIndexes:
    """init_schema creates the run_id indexes and stays idempotent (RC5 Fix 3)."""

    _EXPECTED_INDEXES = {
        "idx_claims_run_id",
        "idx_claims_run_id_id",
        "idx_sources_run_id",
        "idx_evidence_chunks_run_id",
        "idx_qc_reports_run_id",
        "idx_revision_tasks_run_id",
        "idx_trace_events_run_id_id",
        "idx_llm_calls_run_id",
        "idx_syntheses_run_id",
    }

    def test_indexes_exist_after_init(self, tmp_path):
        db = Database(str(tmp_path / "idx.db"))
        db.init_schema()
        with db._conn:
            rows = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        names = {r["name"] for r in rows}
        assert self._EXPECTED_INDEXES <= names

    def test_init_schema_is_idempotent(self, tmp_path):
        db = Database(str(tmp_path / "idx2.db"))
        db.init_schema()
        # Second call must not raise (IF NOT EXISTS on tables AND indexes).
        db.init_schema()
        rid = db.create_run(category="A", competitors=["X"], goal="g")
        assert db.get_run(rid)["status"] == "running"


# ---------------------------------------------------------------------------
# RC5: atomic superseding-claim version increment
# ---------------------------------------------------------------------------


class TestAppendSupersedingClaim:
    """append_superseding_claim is an atomic read-modify-write (RC6).

    The fresh latest row is read, the caller's DELTA overlaid, version derived,
    and the new row inserted — all inside ONE _WRITE_LOCK. This guarantees both
    monotonic versions (RC5) AND that a concurrent correction builds on the prior
    correction's committed CONTENT, not a stale snapshot (RC6 lost-update fix).
    """

    def _base_claim(self, run_id, cid="C1", version=1, status="draft", statement="x"):
        return {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "pricing_model",
            "claim_type": "fact",
            "statement": statement,
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "weak",
            "status": status,
            "version": version,
            "produced_by": "analyst",
        }

    def test_two_corrections_produce_monotonic_versions(self, tmp_path):
        db = Database(str(tmp_path / "sup.db"))
        db.init_schema()
        rid = db.create_run(category="x", competitors=["Acme"], goal="g")
        db.append_claim(self._base_claim(rid, version=1))

        v2 = db.append_superseding_claim(rid, "C1", {"status": "pass"})
        v3 = db.append_superseding_claim(rid, "C1", {"status": "rejected"})

        assert v2 == 2
        assert v3 == 3  # NOT another "2" — derived from current MAX each time

        versions = [r["version"] for r in db.claim_versions(rid, "C1")]
        assert versions == [1, 2, 3]

    def test_supersede_reads_fresh_latest_no_lost_update(self, tmp_path):
        """RC6 regression: a later correction builds on the prior one's CONTENT.

        v1 has statement "orig". Correction A edits the statement to "EDITED-A".
        Correction B (accept) supplies NO statement — it must inherit "EDITED-A"
        from the FRESH latest (v2), not regress to the stale v1 "orig". A stale
        read-modify-write (the old bug) would clobber A's edit.
        """
        db = Database(str(tmp_path / "lost.db"))
        db.init_schema()
        rid = db.create_run(category="x", competitors=["Acme"], goal="g")
        db.append_claim(self._base_claim(rid, version=1, statement="orig"))

        v2 = db.append_superseding_claim(
            rid,
            "C1",
            {"statement": "EDITED-A", "status": "pass", "produced_by": "human:correction"},
        )
        v3 = db.append_superseding_claim(
            rid, "C1", {"status": "pass", "produced_by": "human:correction"}
        )

        assert (v2, v3) == (2, 3)
        rows = {r["version"]: r for r in db.claim_versions(rid, "C1")}
        assert rows[2]["statement"] == "EDITED-A"
        # The load-bearing assertion: B inherited A's fresh content.
        assert rows[3]["statement"] == "EDITED-A"

    def test_supersede_without_prior_claim_raises(self, tmp_path):
        db = Database(str(tmp_path / "sup2.db"))
        db.init_schema()
        rid = db.create_run(category="x", competitors=["Acme"], goal="g")
        with pytest.raises(KeyError):
            db.append_superseding_claim(rid, "missing", {"status": "pass"})
