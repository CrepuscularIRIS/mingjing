"""Tests for the read-only verbatim re-verification audit (``scripts/audit_verbatim.py``).

These tests construct an in-memory ``Database`` with hand-built claim/source rows
and assert that the audit's deterministic re-check reproduces the QA gate's own
verdict (verbatim snippet hit + required-sub-field value grounding), so the
audit's "pass rate" number cannot drift from the production gate semantics.
"""

import json

import pytest

from mingjing.db import Database
from scripts.audit_verbatim import audit_claim, audit_run


@pytest.fixture()
def db(tmp_path) -> Database:
    """An initialized empty Database on a tmp file (real schema, no network)."""
    database = Database(str(tmp_path / "audit.db"))
    database.init_schema()
    return database


def _seed_source(db: Database, run_id: str, sid: str, raw_text: str) -> None:
    db.append_source(
        {
            "id": sid,
            "run_id": run_id,
            "url": f"https://example-{sid}.com/page",
            "title": sid,
            "source_type": "official",
            "source_mode": "LIVE",
            "raw_text": raw_text,
        }
    )


def _seed_claim(
    db: Database,
    run_id: str,
    cid: str,
    *,
    schema_field: str,
    value: dict,
    evidence: list[dict],
    status: str = "pass",
    version: int = 2,
) -> None:
    db.append_claim(
        {
            "id": cid,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": schema_field,
            "claim_type": "fact",
            "statement": "stmt",
            "value_json": json.dumps(value),
            "evidence_json": json.dumps(evidence),
            "evidence_strength": "moderate",
            "status": status,
            "version": version,
        }
    )


def test_audit_claim_passes_when_snippets_and_value_grounded(db: Database) -> None:
    run_id = "run-pass"
    raw = (
        "Acme offers pricing tiers: Free at $0 per month and Pro at $20 per month. "
        "Currency is USD."
    )
    _seed_source(db, run_id, "S1", raw)
    _seed_claim(
        db,
        run_id,
        "C-ok",
        schema_field="pricing_model",
        value={
            "tiers": [{"name": "Free", "price": "$0 per month"}],
            "free_tier": True,
            "currency": "USD",
        },
        evidence=[
            {"source_id": "S1", "snippet": "Free at $0 per month", "relevance": "supports"}
        ],
    )
    result = audit_claim(db, run_id, "C-ok")
    assert result["overall_pass"] is True
    assert all(s["hit"] for s in result["snippets"])
    assert result["value_supported"] is True


def test_audit_claim_fails_on_hallucinated_snippet(db: Database) -> None:
    run_id = "run-hallu"
    _seed_source(db, run_id, "S1", "Acme has a free plan and a paid plan.")
    _seed_claim(
        db,
        run_id,
        "C-bad",
        schema_field="pricing_model",
        value={"tiers": [{"name": "Free"}], "free_tier": True, "currency": "USD"},
        evidence=[
            {
                "source_id": "S1",
                "snippet": "Acme costs nine hundred dollars per year",
                "relevance": "supports",
            }
        ],
    )
    result = audit_claim(db, run_id, "C-bad")
    assert result["overall_pass"] is False
    assert any(not s["hit"] for s in result["snippets"])


def test_audit_run_counts_admitted_and_withheld(db: Database) -> None:
    run_id = "run-mix"
    _seed_source(db, run_id, "S1", "Acme pricing: Free at $0 per month. Currency USD.")
    # one admitted (status=pass) claim
    _seed_claim(
        db,
        run_id,
        "C-pass",
        schema_field="pricing_model",
        value={
            "tiers": [{"name": "Free", "price": "$0 per month"}],
            "free_tier": True,
            "currency": "USD",
        },
        evidence=[{"source_id": "S1", "snippet": "Free at $0 per month", "relevance": "supports"}],
    )
    # one withheld (status=draft) claim — should NOT be audited as admitted
    _seed_claim(
        db,
        run_id,
        "C-draft",
        schema_field="user_sentiment",
        value={"overall": "high"},
        evidence=[{"source_id": "S1", "snippet": "Free at $0 per month", "relevance": "supports"}],
        status="draft",
    )
    # a qc_report flagging the draft claim in the final round
    db.append_qc_report(
        {
            "id": "Q1",
            "run_id": run_id,
            "claim_id": "C-draft",
            "round": 1,
            "verdict": "reject",
            "issues_json": json.dumps(["VALUE_UNSUPPORTED"]),
        }
    )
    summary = audit_run(db, run_id)
    assert summary["admitted_count"] == 1
    assert summary["checked"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0
    assert summary["withheld_count"] == 1
    assert summary["withheld_codes"].get("VALUE_UNSUPPORTED") == 1


# ---------------------------------------------------------------------------
# Stop-gate regression: the audit's "read-only" claim is ENGINE-enforced.
# ---------------------------------------------------------------------------


def test_read_only_database_rejects_writes(tmp_path) -> None:
    """A read_only Database raises at the SQLite engine on ANY write attempt."""
    import sqlite3

    import pytest

    path = str(tmp_path / "ro.db")
    rw = Database(path)
    rw.init_schema()
    rw.create_run(category="CRM", competitors=["Acme"], goal="g")

    ro = Database(path, read_only=True)
    assert len(ro.list_runs()) == 1  # reads work
    with pytest.raises(sqlite3.OperationalError):
        ro.create_run(category="X", competitors=["B"], goal="g2")


def test_read_only_database_refuses_missing_file(tmp_path) -> None:
    """mode=ro cannot conjure a database file into existence."""
    import sqlite3

    import pytest

    with pytest.raises(sqlite3.OperationalError):
        Database(str(tmp_path / "missing.db"), read_only=True)
