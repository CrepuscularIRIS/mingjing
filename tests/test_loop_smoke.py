"""Offline, deterministic end-to-end smoke gate (Task 15b, Part C).

Drives ``intake -> ... -> write`` with NO network and NO LLM by injecting
:class:`mingjing.graph.GraphDeps` with fake ``collect_fn`` / ``analyze_fn`` and a
``tmp_path`` :class:`mingjing.collector.cache.Cache` seeded with two
distinct-domain fixture pages.

The honest weak->strong mechanism under test: the collect cap grows with the
revision round (``1 + round``), so round 0 fetches a single source (the analyst
cannot corroborate it -> WEAK_EVIDENCE -> reject) and round 1 performs a REAL
additional fetch of a second, distinct-domain official source (-> strong ->
pass). The append-only claim history makes the weak->strong transition visible
across versions.
"""

import json

import pytest

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph

COMPETITOR = "Acme"
FIELD = "pricing_model"

# Two distinct-domain fixture pages. Page A is a third-party review; page B is on
# the competitor's own domain (classified "official" by _infer_source_type). The
# claim statement is a verbatim substring of both raw texts so the
# HALLUCINATED_SNIPPET gate never fires.
STATEMENT = "Pro tier costs $10 per month"
PAGE_A_URL = "https://reviews.example.net/acme"
PAGE_B_URL = "https://acme.example.com/pricing"
PAGE_A_TEXT = f"Reviewers report: {STATEMENT}, billed annually."
PAGE_B_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly. Pro $10/mo plan available."

# Fixed source ids so the fake collector returns stable, distinct sources.
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
    """Return the first ``source_cap`` fixture sources (a real additional fetch).

    Round 0 (cap 1) yields one source; round 1 (cap 2) yields two distinct-domain
    sources. The cache is consulted to prove the seeded fallback is real.
    """
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        # Mirror the real collector: each fetch gets a fresh source_id.
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_fn(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
    """Deterministic analyst: corroborate only when >=2 distinct sources exist.

    With a single collected source the analyst cannot independently corroborate
    the claim, so ``evidence_ref`` is empty (the claim scores weak). With two or
    more sources it cites them all. The statement is a verbatim substring of the
    fixture raw text so the snippet gate passes.
    """
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {"tiers": ["Pro $10/mo"]},
        "evidence_ref": evidence_ref,
    }


@pytest.mark.slow
def test_loop_weak_to_strong_offline(tmp_path) -> None:
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[COMPETITOR], goal="g")

    # The context manager closes the cache on exit so no WAL -wal/-shm sidecars
    # leak past the run.
    with Cache(str(tmp_path / "cache.db")) as cache:
        # Seed the cache with the two distinct-domain fixture pages.
        cache.put(FetchResult(text=PAGE_A_TEXT, url=PAGE_A_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=PAGE_B_TEXT, url=PAGE_B_URL, source_mode="LIVE"))

        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=None,
            collect_fn=_fake_collect_fn,
            analyze_fn=_fake_analyze_fn,
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

    # 1. The run reaches write and produced a non-empty report body. The live
    #    graph now runs a post-write synthesis pass (write -> synthesis -> END),
    #    so the terminal phase is "synthesis"; "write" is accepted for the
    #    compile-only path that has no synthesis node.
    assert final["phase"] in ("write", "synthesis")
    assert final.get("report")

    # 2. The loop performed >=1 revision (round incremented past 0).
    assert final["revision_round"] >= 1

    # 3. >=1 claim is bound to >=1 real, persisted source.
    latest = db.latest_claims_for_run(run_id)
    assert latest, "expected at least one latest claim"
    final_claim = latest[0]

    evidence = json.loads(final_claim["evidence_json"])
    assert evidence, "final claim must cite evidence"
    for ev in evidence:
        assert db.get_source(ev["source_id"]) is not None

    # 4. The append-only weak->strong transition is visible across versions.
    all_claims = sorted(db.claims_for_run(run_id), key=lambda c: c["version"])
    strengths = [c["evidence_strength"] for c in all_claims]
    assert strengths[-1] == "strong", f"final strength must be strong, got {strengths}"
    rank = {"weak": 0, "moderate": 1, "strong": 2}
    assert any(rank[s] < rank["strong"] for s in strengths[:-1]), (
        f"an earlier version must be weaker than the final strong claim, got {strengths}"
    )
    assert len(all_claims) >= 2, "weak->strong requires >=2 append-only versions"

    # 5. The writer's referenced ids are all backed by passed claims.
    passed_ids = {c["id"] for c in latest}
    referenced = {line.split("]")[0].lstrip("[") for line in final["report"].splitlines() if line}
    assert referenced, "report should reference at least one claim"
    assert referenced <= passed_ids
