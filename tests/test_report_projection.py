"""Graph -> API report-projection bridge regression (status promotion).

This is the regression test for the demo-breaking bug where a real loop run left
every claim ``status="draft"`` (the graph never promoted QA-accepted claims), so
the report API's ``status == "pass"`` filter skipped everything and
``GET /runs/{id}/report`` returned empty sections.

The existing API tests SEED ``status="pass"`` claims directly; the loop/smoke
tests assert only the writer's in-memory projection or ``latest_claims_for_run``.
Neither drives a FULL graph run and then feeds the persisted rows to the REAL
report projection — exactly the seam the bug slipped through. These tests do.

Offline + deterministic: fake ``collect_fn`` / ``analyze_fn`` (same shape as
``tests/test_loop_smoke.py`` / ``tests/test_runner.py``), no network, no LLM.
"""

import pytest

from mingjing import api
from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph

COMPETITOR = "Acme"
FIELD = "pricing_model"
FIELD_B = "target_market"

STATEMENT = "Pro tier costs $10 per month"
PAGE_A_URL = "https://reviews.example.net/acme"
PAGE_B_URL = "https://acme.example.com/pricing"
PAGE_A_TEXT = f"Reviewers report: {STATEMENT}, billed annually."
PAGE_B_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly. Pro $10/mo plan available."

FIXTURE_SOURCES = [
    {
        "url": PAGE_A_URL,
        "title": "Acme review",
        "snippet": STATEMENT,
        "fetched": True,
        "source_id": "fix-A",
        "source_mode": "CACHED",
        "text": PAGE_A_TEXT,
        "content_hash": "hashA",
        "fetched_at": 1.0,
    },
    {
        "url": PAGE_B_URL,
        "title": "Acme pricing",
        "snippet": STATEMENT,
        "fetched": True,
        "source_id": "fix-B",
        "source_mode": "CACHED",
        "text": PAGE_B_TEXT,
        "content_hash": "hashB",
        "fetched_at": 2.0,
    },
]


def _fake_collect_fn(query, *, cache, source_cap, mode="live_first"):
    """Return the first ``source_cap`` fixture sources (a real additional fetch)."""
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_strong_when_two_sources(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Corroborate only when >=2 distinct sources exist (weak->strong driver)."""
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {"tiers": ["Pro $10/mo"]},
        "evidence_ref": evidence_ref,
    }


def _seed(tmp_path) -> tuple[Database, str, Cache]:
    """Open a schema'd DB + a cache seeded with the two fixture pages."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    cache = Cache(str(tmp_path / "cache.db"))
    cache.put(FetchResult(text=PAGE_A_TEXT, url=PAGE_A_URL, source_mode="LIVE"))
    cache.put(FetchResult(text=PAGE_B_TEXT, url=PAGE_B_URL, source_mode="LIVE"))
    return db, "", cache


def _invoke(db: Database, cache: Cache, analyze_fn, fields: list[str]) -> str:
    """Drive a full injected loop to completion; return the run_id."""
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")
    deps = GraphDeps(
        db=db,
        cache=cache,
        settings=None,
        collect_fn=_fake_collect_fn,
        analyze_fn=analyze_fn,
    )
    graph = build_graph(deps=deps)
    graph.invoke(
        {
            "run_id": run_id,
            "db": db,
            "intake": {
                "category": "cat",
                "competitors": [COMPETITOR],
                "goal": "g",
                "fields": fields,
            },
        }
    )
    return run_id


@pytest.mark.slow
def test_full_run_promotes_claims_and_report_is_nonempty(tmp_path) -> None:
    """A completed loop persists status=pass claims; the REAL report is non-empty.

    This is the graph -> API bridge the bug slipped through: drive the full
    graph, then feed the persisted latest rows to ``_build_report_sections``.
    Without the write_node promotion the claims stay ``draft`` and the report is
    empty.
    """
    db, _, cache = _seed(tmp_path)
    with cache:
        run_id = _invoke(db, cache, _fake_analyze_strong_when_two_sources, [FIELD])

    # 1. The projected latest claim is status=pass (NOT draft).
    latest = db.latest_claims_for_run(run_id)
    assert latest, "expected at least one latest claim"
    assert all(c["status"] == "pass" for c in latest), (
        f"all latest claims must be promoted to pass, got "
        f"{[(c['schema_field'], c['status']) for c in latest]}"
    )

    # 2. The REAL report projection returns non-empty sections + a strength tally.
    report = api._build_report_sections(db.latest_claims_for_run(run_id))
    assert report["sections"], "report sections must be non-empty after a real run"
    all_claim_ids = {
        c["id"] for section in report["sections"] for c in section["claims"]
    }
    assert {c["id"] for c in latest} <= all_claim_ids, (
        "every passed claim must appear in the report sections"
    )
    tally = report["strength_tally"]
    assert sum(tally.values()) == len(latest), (
        f"strength_tally must count every passed claim, got {tally}"
    )
    assert tally["strong"] >= 1, f"the weak->strong claim should land strong: {tally}"

    # 3. The weak->strong append-only history is still visible (latest is strong).
    all_versions = sorted(db.claims_for_run(run_id), key=lambda c: c["version"])
    strengths = [c["evidence_strength"] for c in all_versions]
    assert strengths[-1] == "strong", f"final strength must be strong, got {strengths}"
    rank = {"weak": 0, "moderate": 1, "strong": 2}
    assert any(rank[s] < rank["strong"] for s in strengths[:-1]), (
        f"an earlier version must be weaker than the final strong claim, got {strengths}"
    )


@pytest.mark.slow
def test_partial_run_only_unflagged_claims_are_pass(tmp_path) -> None:
    """On a partial (reject-to-cap) run only un-flagged claims become status=pass.

    Two fields: one reaches strong (un-flagged), one stays weak forever (flagged
    each round). The loop exhausts the revision cap and terminates with verdict
    ``reject``. The strong claim is promoted to ``pass`` and surfaces in the
    report; the perpetually-weak claim stays ``draft`` and is excluded.
    """

    def _mixed_analyze(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
        # FIELD reaches strong with >=2 sources; FIELD_B never corroborates.
        if field == FIELD:
            return _fake_analyze_strong_when_two_sources(
                db, run_id, field=field, competitor=competitor,
                evidence_text=evidence_text, source_ids=source_ids, settings=settings,
            )
        return {
            "statement": STATEMENT,
            "claim_type": "fact",
            "value": {"segment": ["SMB"]},
            "evidence_ref": [],  # never corroborated -> weak forever -> flagged
        }

    db, _, cache = _seed(tmp_path)
    with cache:
        run_id = _invoke(db, cache, _mixed_analyze, [FIELD, FIELD_B])

    latest = db.latest_claims_for_run(run_id)
    by_field = {c["schema_field"]: c for c in latest}
    assert set(by_field) == {FIELD, FIELD_B}, f"expected both fields, got {by_field.keys()}"

    # The strong, un-flagged claim is promoted to pass.
    assert by_field[FIELD]["status"] == "pass", "the un-flagged strong claim must be pass"
    # The perpetually-weak, flagged claim stays draft (honest behavior).
    assert by_field[FIELD_B]["status"] == "draft", "the flagged weak claim must stay draft"

    # The report includes only the passed field, and excludes the flagged one.
    report = api._build_report_sections(db.latest_claims_for_run(run_id))
    report_fields = {section["schema_field"] for section in report["sections"]}
    assert FIELD in report_fields, "the passed field must appear in the report"
    assert FIELD_B not in report_fields, "the flagged field must be excluded from the report"
    assert sum(report["strength_tally"].values()) == 1, (
        f"only the single passed claim should be tallied, got {report['strength_tally']}"
    )
