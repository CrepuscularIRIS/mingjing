"""Integration test: cache_first mode completes the full graph on cached evidence.

Demo-safety guarantee: when ``MINGJING_MODE=cache_first`` and every live fetch
raises (network / LLM unavailable at showtime), a run still drives all the way
to ``phase == "write"`` by serving evidence exclusively from the read-only cache
(``source_mode == "CACHED"``).

No real network or LLM is touched:
- ``mingjing.collector.fetch._live_fetch`` is monkeypatched to raise
  ``TimeoutError("offline")`` — proving the fallback, not live delivery.
- ``mingjing.collector.search.search`` is monkeypatched to return two
  fixture hits so ``collector.collect`` has URLs to look up.
- ``deps.collect_fn`` wraps ``collector.collect`` with
  ``fetch_robots=lambda domain: ""`` (allow-all, no network).
- ``deps.analyze_fn`` is deterministic — no LLM call.
- The ``Cache`` is pre-seeded with ``FetchResult``s whose text contains
  the claim value tokens, so the VALUE_UNSUPPORTED gate does not trip.

The second unit-level test (``cache_first`` hit without live) is already
covered in ``test_fetch_fallback.py::test_cache_first_reads_cache_before_live``
and is therefore not repeated here.
"""

import pytest

from mingjing.agents import collector as collector_agent
from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

COMPETITOR = "Acme"
FIELD = "pricing_model"

# Verbatim in BOTH fixture texts so snippet / VALUE_UNSUPPORTED gates pass.
STATEMENT = "Pro tier $10 per month"

OFFICIAL_URL = "https://acme.example.com/pricing"
# "Pro $10/month" must appear verbatim so the VALUE_UNSUPPORTED gate does not trip.
OFFICIAL_TEXT = (
    f"Official Acme pricing: {STATEMENT}, billed monthly. Pro $10/month for teams."
)

CORROBORATE_URL = "https://techreviews.net/acme-pricing"
CORROBORATE_TEXT = (
    f"Third-party review: {STATEMENT} — Pro $10/month, annual and monthly billing available."
)

# Two fixture search hits — URLs must match the pre-seeded cache entries.
_FIXTURE_HITS = [
    {"url": OFFICIAL_URL, "title": "Acme official pricing", "snippet": STATEMENT},
    {"url": CORROBORATE_URL, "title": "TechReviews Acme", "snippet": STATEMENT},
]


# ---------------------------------------------------------------------------
# Injected callables
# ---------------------------------------------------------------------------


def _make_collect_fn(cache: Cache) -> object:
    """Return a collect wrapper that uses the real ``collector.collect`` but:

    - passes ``fetch_robots=lambda domain: ""`` (no network),
    - relies on the monkeypatched ``_live_fetch`` raising so
      ``fetch_with_fallback`` falls back to the pre-seeded cache.
    """

    def collect_fn(query: str, *, cache: Cache, source_cap: int, mode: str = "live_first"):  # type: ignore[override]
        return collector_agent.collect(
            query,
            cache,
            source_cap=source_cap,
            mode=mode,
            fetch_robots=lambda domain: "",  # allow-all, no network
        )

    return collect_fn


def _fake_analyze_fn(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Deterministic analyst: corroborate with all supplied sources.

    Round 0 (cap=1, one source): returns empty ``evidence_ref`` so the claim
    scores weak and QA triggers a revision.
    Round 1 (cap=2, two sources): cites both so the claim scores strong.
    The statement is a verbatim substring of both fixture texts.
    """
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {
            "tiers": ["Pro $10/month"],
            "free_tier": False,
            "currency": "USD",
            "billing_period": "monthly",
        },
        "evidence_ref": evidence_ref,
    }


# ---------------------------------------------------------------------------
# Settings stub — the collect node reads ``deps.settings.mode`` only.
# ---------------------------------------------------------------------------


class _CacheFirstSettings:
    """Minimal settings stub exposing the single attribute the collect node reads."""

    mode: str = "cache_first"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_cache_first_completes_with_all_live_failing(monkeypatch, tmp_path) -> None:
    """cache_first + all-live-raises drives the graph to phase==write on cached evidence."""

    # Force every live fetch to fail — this is the scenario we're proving works.
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    # Replace the search function where collector.collect imports it so it
    # receives the fixture URLs without touching the network.
    monkeypatch.setattr(
        "mingjing.agents.collector._search_fn",
        lambda query, max_results=5: _FIXTURE_HITS[:max_results],
    )

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(
        category="saas", competitors=[COMPETITOR], goal="pricing research"
    )

    with Cache(str(tmp_path / "cache.db")) as cache:
        # Pre-seed cache with CACHED-tagged results containing the value tokens.
        cache.put(FetchResult(text=OFFICIAL_TEXT, url=OFFICIAL_URL, source_mode="CACHED"))
        cache.put(
            FetchResult(text=CORROBORATE_TEXT, url=CORROBORATE_URL, source_mode="CACHED")
        )

        settings = _CacheFirstSettings()
        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=settings,
            collect_fn=_make_collect_fn(cache),
            analyze_fn=_fake_analyze_fn,
        )
        graph = build_graph(deps=deps)

        final = graph.invoke(
            {
                "run_id": run_id,
                "db": db,
                "intake": {
                    "category": "saas",
                    "competitors": [COMPETITOR],
                    "goal": "pricing research",
                    "fields": [FIELD],
                },
            }
        )

    # 1. The graph reaches the write phase (the live graph then runs the
    #    post-write synthesis node: write -> synthesis -> END).
    assert final["phase"] in ("write", "synthesis"), f"got {final['phase']!r}"

    # 2. At least one persisted source has source_mode == "CACHED".
    all_sources = db._conn.execute(
        "SELECT source_mode FROM sources WHERE run_id = ?", (run_id,)
    ).fetchall()
    assert all_sources, "no sources persisted"
    modes = {row[0] for row in all_sources}
    assert "CACHED" in modes, f"expected at least one CACHED source; got modes={modes}"

    # 3. All persisted sources are CACHED (live was forced to fail).
    assert modes == {"CACHED"}, (
        f"all sources should be CACHED when live is forced offline; got modes={modes}"
    )

    # 4. QA verdict is "pass" (not partial) — the loop completed honestly on cached evidence.
    assert final.get("verdict") == "pass", (
        f"expected verdict=pass, got {final.get('verdict')!r}"
    )

    # 5. The run produced a non-empty report.
    assert final.get("report"), "report body must not be empty"

    # 6. Every claim cited in the final report is backed by a persisted CACHED source.
    import json

    latest = db.latest_claims_for_run(run_id)
    for claim in latest:
        if claim.get("status") != "pass":
            continue
        evidence = json.loads(claim.get("evidence_json") or "[]")
        for ev in evidence:
            src = db.get_source(ev["source_id"])
            assert src is not None, f"source {ev['source_id']} not found in DB"
            assert src.get("source_mode") == "CACHED", (
                f"source {ev['source_id']} has source_mode={src.get('source_mode')!r},"
                " expected CACHED"
            )
