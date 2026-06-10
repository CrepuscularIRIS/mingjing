"""Tests for the write_partial non-silent withheld-claims disclosure (Task 9).

A ``write_partial`` (a run that terminates with ``reject`` at the round cap or
out of budget) must NOT be silent: flagged/rejected claims correctly STAY
``draft`` (withheld from the report), but the report must also ENUMERATE which
claims were withheld and why. ``build_withheld_disclosure`` is the pure reader
that produces that enumeration from the ledger + qc_reports.
"""
from typing import Any

from mingjing import synthesis as synthesis_mod
from mingjing.db import Database
from mingjing.synthesis import build_withheld_disclosure


def _seed_run_with_flagged_claim(
    db: Database, *, claim_id: str = "c1", round_idx: int = 2
) -> str:
    """Seed a run with one draft claim flagged by the LAST QA round."""
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
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
            "evidence_strength": "weak",
            "status": "draft",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    db.append_qc_report(
        {
            "id": "qc1",
            "run_id": run_id,
            "claim_id": claim_id,
            "round": round_idx,
            "verdict": "reject",
            "issues_json": '["VALUE_UNSUPPORTED", "WEAK_EVIDENCE"]',
        }
    )
    return run_id


def test_partial_run_discloses_withheld_claims_with_reasons(tmp_path):
    """A write_partial must NOT be silent: enumerate withheld claims + issue codes."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    run_id = _seed_run_with_flagged_claim(db, round_idx=2)

    disclosure = build_withheld_disclosure(run_id, db)

    assert disclosure  # non-empty
    item = disclosure[0]
    assert item["claim_id"] == "c1"
    assert "issue_codes" in item and item["issue_codes"]
    assert "VALUE_UNSUPPORTED" in item["issue_codes"]
    assert item["round"] == 2


def test_disclosure_empty_when_no_flagged_claims(tmp_path):
    """A clean run (no flagged claims) yields an empty disclosure list."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    assert build_withheld_disclosure(run_id, db) == []


def test_disclosure_excludes_passed_claims(tmp_path):
    """A claim promoted to status='pass' is NOT withheld even if flagged earlier."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    # v1 draft + v2 promoted to pass
    for version, status in ((1, "draft"), (2, "pass")):
        db.append_claim(
            {
                "id": "c1",
                "run_id": run_id,
                "competitor": "Acme",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Pro tier costs $10 per month",
                "value_json": "{}",
                "evidence_json": "[]",
                "based_on_json": "[]",
                "evidence_strength": "strong",
                "status": status,
                "version": version,
                "produced_by": "analyst",
            }
        )
    # An early-round flag that the final round cleared (no issues last round).
    db.append_qc_report(
        {
            "id": "qc1",
            "run_id": run_id,
            "claim_id": "c1",
            "round": 1,
            "verdict": "reject",
            "issues_json": '["WEAK_EVIDENCE"]',
        }
    )
    assert build_withheld_disclosure(run_id, db) == []


def test_disclosure_wired_into_partial_synthesis(tmp_path, monkeypatch):
    """run_synthesis surfaces the withheld disclosure for a partial run."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    # A passed claim so synthesis is non-empty, plus a flagged draft claim.
    db.append_claim(
        {
            "id": "c1",
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
    _seed_run_with_flagged_claim_for(db, run_id, claim_id="c2", round_idx=2)

    def fake_call_llm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"bluf": {"text": "Acme leads on price", "claim_ids": ["c1"]}}

    monkeypatch.setattr(synthesis_mod, "call_llm", fake_call_llm)
    synthesis_mod.run_synthesis(db, run_id, settings=None)

    out = db.get_synthesis(run_id)
    assert out is not None
    assert "withheld" in out
    assert any(w["claim_id"] == "c2" for w in out["withheld"])


def test_total_reject_early_exit_still_discloses_withheld(tmp_path, monkeypatch):
    """The previously-SILENT path: a run with ZERO passed claims still discloses.

    run_synthesis takes the ``if not passed: return`` early-exit (no LLM call),
    but must persist a ``{"withheld": [...]}`` row so even a total-reject run is
    auditable rather than silent."""
    db = Database(str(tmp_path / "m.db"))
    db.init_schema()
    run_id = _seed_run_with_flagged_claim(db, claim_id="c1", round_idx=2)  # only a draft claim

    def boom_call_llm(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("LLM must not be called on the total-reject early-exit")

    monkeypatch.setattr(synthesis_mod, "call_llm", boom_call_llm)
    synthesis_mod.run_synthesis(db, run_id, settings=None)

    out = db.get_synthesis(run_id)
    assert out is not None
    assert any(w["claim_id"] == "c1" for w in out["withheld"])
    # Early-exit means no LLM-projected report sections were produced.
    assert "bluf" not in out


def _seed_run_with_flagged_claim_for(
    db: Database, run_id: str, *, claim_id: str, round_idx: int
) -> None:
    db.append_claim(
        {
            "id": claim_id,
            "run_id": run_id,
            "competitor": "Acme",
            "schema_field": "positioning",
            "claim_type": "fact",
            "statement": "unsupported claim",
            "value_json": "{}",
            "evidence_json": "[]",
            "based_on_json": "[]",
            "evidence_strength": "weak",
            "status": "draft",
            "version": 1,
            "produced_by": "analyst",
        }
    )
    db.append_qc_report(
        {
            "id": f"qc-{claim_id}",
            "run_id": run_id,
            "claim_id": claim_id,
            "round": round_idx,
            "verdict": "reject",
            "issues_json": '["VALUE_UNSUPPORTED"]',
        }
    )
