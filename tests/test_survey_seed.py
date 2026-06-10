import pytest

from mingjing.db import Database
from mingjing.survey_fixture import fixture_for
from mingjing.survey_seed import survey_seed


def _db(tmp_path) -> Database:
    d = Database(str(tmp_path / "s.db"))
    d.init_schema()
    return d


def test_survey_seed_appends_source_rows_and_returns_entries(tmp_path):
    db = _db(tmp_path)
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    entries = survey_seed(db, run_id, "Notion", fixture_for("Notion"))
    assert entries
    for e in entries:
        assert set(e) == {"source_id", "field", "competitor"}
        assert e["competitor"] == "Notion"
    pricing = next(e for e in entries if e["field"] == "pricing_model")
    row = db.get_source(pricing["source_id"])
    assert row is not None
    assert row["source_type"] == "survey"
    assert row["source_mode"] == "SIMULATED"
    assert "Pro plan at $10/mo" in row["raw_text"]
    assert row["url"] == "survey:SV-1/pricing_model"
    persona = next(e for e in entries if e["field"] == "user_persona")
    assert db.get_source(persona["source_id"])["source_type"] == "interview"


def test_survey_seed_ids_are_run_scoped(tmp_path):
    """The source id is run-scoped (the run id is part of it) so repeated runs
    never collide on the ``sources`` primary key; the locator (url) stays the
    stable, human-readable ``survey:SV-1/<field>``."""
    db = _db(tmp_path)
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    entries = survey_seed(db, run_id, "Notion", fixture_for("Notion"))
    ids = {e["source_id"] for e in entries}
    assert f"{run_id}-survey-SV-1-pricing_model" in ids
    pricing = next(e for e in entries if e["field"] == "pricing_model")
    assert db.get_source(pricing["source_id"])["url"] == "survey:SV-1/pricing_model"


def test_survey_seed_distinct_runs_do_not_collide(tmp_path):
    """Seeding the SAME competitor in two different runs must succeed for BOTH
    (ids are run-scoped) — a regression guard for the PRIMARY KEY collision that
    a stable cross-run id caused (the second INSERT raised UNIQUE-constraint)."""
    db = _db(tmp_path)
    run_a = db.create_run(category="notes", competitors=["Notion"], goal="g")
    run_b = db.create_run(category="notes", competitors=["Notion"], goal="g")
    entries_a = survey_seed(db, run_a, "Notion", fixture_for("Notion"))
    entries_b = survey_seed(db, run_b, "Notion", fixture_for("Notion"))  # must not raise
    ids_a = {e["source_id"] for e in entries_a}
    ids_b = {e["source_id"] for e in entries_b}
    assert ids_a.isdisjoint(ids_b)  # no shared ids across runs
    # both runs' rows persist, each owned by its own run
    for e in entries_a:
        assert db.get_source(e["source_id"])["run_id"] == run_a
    for e in entries_b:
        assert db.get_source(e["source_id"])["run_id"] == run_b


def test_survey_seed_none_fixture_returns_empty(tmp_path):
    db = _db(tmp_path)
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    assert survey_seed(db, run_id, "Acme", None) == []


def test_survey_seed_rejects_fixture_missing_id(tmp_path):
    db = _db(tmp_path)
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    bad = {"survey": {"fields": {"pricing_model": "Pro plan at $10/mo"}}}  # no survey_id
    with pytest.raises(ValueError, match="survey_id"):
        survey_seed(db, run_id, "Notion", bad)
