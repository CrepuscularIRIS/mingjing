"""Wall-clock timing harness for the MingJing demo pipeline.

Measures the elapsed time of a full prewarm + one end-to-end graph run and
asserts the result is within the 6-minute (360 s) demo budget.

OFFLINE mode (default, safe for CI):
    Uses the same deterministic fake fetch/analyze callables as the offline
    smoke test — no network, no live LLM, no API key needed.  Completes well
    under the 6-minute budget and prints:

        NOTE: offline harness — the REAL <=6min gate must be measured live on
              the demo machine with the MiniMax key + network.

LIVE mode (``MINGJING_TIMING_LIVE=1``):
    Switches to real fetch/LLM calls (not fully wired in this task — marked
    with TODO).  If set without a ``MINIMAX_API_KEY`` value, exits with a
    clear message.

Usage:
    uv run python scripts/demo_timing.py            # offline
    MINGJING_TIMING_LIVE=1 uv run python scripts/demo_timing.py  # live (needs key)
"""

import os
import sys
import tempfile
import time

BUDGET_SECONDS = 360.0  # 6 minutes


# ---------------------------------------------------------------------------
# Offline fixtures (mirrors test_loop_smoke.py / test_pricing_path.py)
# ---------------------------------------------------------------------------

COMPETITOR = "Acme"
FIELDS = ["pricing_model"]  # narrow slice for timing harness

STATEMENT = "Pro tier $10 per month"
OFFICIAL_URL = "https://acme.example.com/pricing"
OFFICIAL_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly."
CORROBORATE_URL = "https://techreviews.net/acme-pricing"
CORROBORATE_TEXT = f"Third-party review confirms: {STATEMENT}, monthly and annual billing."

FIXTURE_SOURCES = [
    {
        "url": OFFICIAL_URL,
        "title": "Acme official pricing",
        "text": OFFICIAL_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "timing-official",
        "content_hash": "hash_official",
        "fetched_at": 1.0,
    },
    {
        "url": CORROBORATE_URL,
        "title": "TechReviews Acme pricing",
        "text": CORROBORATE_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "timing-corroborate",
        "content_hash": "hash_corroborate",
        "fetched_at": 2.0,
    },
]


def _fake_collect_fn(query, *, cache, source_cap, mode="live_first"):
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_fn(db, run_id, *, field, competitor, evidence_text, source_ids, settings=None):
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        # "Pro tier" is verbatim in OFFICIAL_TEXT/CORROBORATE_TEXT so the
        # VALUE_UNSUPPORTED gate (value leaves must appear in cited sources) passes.
        "value": {"tiers": ["Pro tier"], "free_tier": False},
        "evidence_ref": evidence_ref,
    }


# ---------------------------------------------------------------------------
# Offline run
# ---------------------------------------------------------------------------


def _run_offline(tmp_dir: str) -> None:
    """Execute offline prewarm + graph run in ``tmp_dir`` and print timing."""
    from mingjing.collector.cache import Cache
    from mingjing.collector.fetch import FetchResult
    from mingjing.db import Database
    from mingjing.graph import GraphDeps, build_graph
    from mingjing.prewarm import prewarm_all

    print("=" * 60)
    print("MingJing Demo Timing Harness  [OFFLINE MODE]")
    print("=" * 60)
    print(
        "\nNOTE: offline harness — the REAL <=6min gate must be measured live\n"
        "      on the demo machine with the MiniMax key + network.\n"
    )

    db = Database(os.path.join(tmp_dir, "run.db"))
    db.init_schema()

    # t0 is set before the Cache context manager so that Cache.__exit__
    # (WAL checkpoint / close) is deliberately included in the elapsed time —
    # matching the wall-clock budget seen by a real demo operator.
    t0 = time.monotonic()
    with Cache(os.path.join(tmp_dir, "cache.db")) as cache:
        # --- Seed cache ---
        cache.put(FetchResult(text=OFFICIAL_TEXT, url=OFFICIAL_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=CORROBORATE_TEXT, url=CORROBORATE_URL, source_mode="LIVE"))

        # --- Phase 1: prewarm ---
        t_prewarm_start = time.monotonic()

        def fake_fetch(url: str) -> FetchResult:
            existing = cache.get(url)
            if existing is not None:
                return existing
            raise LookupError(f"no fixture for {url}")

        prewarm_result = prewarm_all(
            [COMPETITOR],
            FIELDS,
            cache=cache,
            fetch_fn=fake_fetch,
            max_workers=4,
            url_for=lambda comp, fld: OFFICIAL_URL,  # map to fixture URL
        )
        t_prewarm_end = time.monotonic()
        print(
            f"  Prewarm: {t_prewarm_end - t_prewarm_start:.3f}s  "
            f"(warmed={len(prewarm_result['warmed'])}, "
            f"errors={len(prewarm_result['errors'])})"
        )

        # --- Phase 2: end-to-end graph run ---
        run_id = db.create_run(
            category="saas", competitors=[COMPETITOR], goal="pricing demo"
        )

        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=None,
            collect_fn=_fake_collect_fn,
            analyze_fn=_fake_analyze_fn,
        )
        graph = build_graph(deps=deps)

        t_graph_start = time.monotonic()
        final = graph.invoke(
            {
                "run_id": run_id,
                "db": db,
                "intake": {
                    "category": "saas",
                    "competitors": [COMPETITOR],
                    "goal": "pricing demo",
                    "fields": FIELDS,
                },
            }
        )
        t_graph_end = time.monotonic()
        print(
            f"  Graph run: {t_graph_end - t_graph_start:.3f}s  "
            f"(phase={final['phase']}, verdict={final.get('verdict')}, "
            f"revision_round={final.get('revision_round')})"
        )

    elapsed = time.monotonic() - t0
    under_budget = elapsed < BUDGET_SECONDS

    print()
    print(f"  Total elapsed: {elapsed:.3f}s  (budget: {BUDGET_SECONDS:.0f}s)")
    if under_budget:
        print(f"  BUDGET OK  [{elapsed:.1f}s < {BUDGET_SECONDS:.0f}s]")
    else:
        print(f"  BUDGET EXCEEDED  [{elapsed:.1f}s >= {BUDGET_SECONDS:.0f}s]")
    print()

    if not under_budget:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------


def _run_live() -> None:  # pragma: no cover
    """Live timing run — requires MINIMAX_API_KEY + network.

    Uses real MiniMax LLM calls and real web search/fetch (SearXNG or
    DuckDuckGo fallback).  Measures prewarm + end-to-end graph wall-clock
    against the 6-minute demo budget.

    To run::

        MINGJING_TIMING_LIVE=1 MINIMAX_API_KEY=<key> \\
            uv run python scripts/demo_timing.py

    Optionally set::

        MINGJING_SEARXNG_URL=http://localhost:8080   # avoids DDG throttling
        MINGJING_TIMING_COMPETITOR=Notion            # defaults to "Notion"
    """
    # --- Key guard (must be first) ---
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print(
            "ERROR: MINGJING_TIMING_LIVE=1 is set but MINIMAX_API_KEY is empty.\n"
            "  Export a valid key before running in live mode:\n"
            "  export MINIMAX_API_KEY=your-key-here\n"
        )
        sys.exit(1)

    # Local imports keep the module fast at import time (mirrors runner.py style).
    from mingjing.collector.cache import Cache
    from mingjing.config import Settings
    from mingjing.db import Database
    from mingjing.graph import GraphDeps, build_graph
    from mingjing.runner import _prewarm_best_effort
    from mingjing.schemas import FIELD_SCHEMAS

    competitor = os.environ.get("MINGJING_TIMING_COMPETITOR", "Notion")
    fields = list(FIELD_SCHEMAS)

    print("=" * 60)
    print("MingJing Demo Timing Harness  [LIVE MODE]")
    print(f"  Competitor : {competitor}")
    print(f"  Fields     : {fields}")
    print("  LLM        : real MiniMax + web (search→fetch)")
    print("=" * 60)
    print()

    # --- SearXNG advisory ---
    searxng_url = os.environ.get("MINGJING_SEARXNG_URL", "").strip()
    if not searxng_url:
        print(
            "NOTE: MINGJING_SEARXNG_URL is not set — discovery will fall back to\n"
            "      DuckDuckGo, which is likely throttled and will slow the run.\n"
            "      Recommend: export MINGJING_SEARXNG_URL=http://localhost:8080\n"
        )

    with tempfile.TemporaryDirectory(prefix="mingjing_timing_live_") as tmp_dir:
        # Point Settings at temp files so we don't pollute the production DB.
        os.environ["MINGJING_DB"] = os.path.join(tmp_dir, "run.db")
        os.environ["MINGJING_CACHE_DB"] = os.path.join(tmp_dir, "cache.db")

        settings = Settings.load()

        # Sanity-check the loaded settings.
        if not settings.minimax_base_url.endswith("/v1"):
            print(
                f"WARNING: settings.minimax_base_url={settings.minimax_base_url!r} "
                "does not end with '/v1' — the MiniMax client may fail."
            )

        # t0 BEFORE opening the Cache (mirrors _run_offline).
        t0 = time.monotonic()
        with Cache(settings.cache_db_path) as cache:
            # --- Phase 1: prewarm (best-effort) ---
            t_prewarm_start = time.monotonic()
            prewarm_warmed: list[str] = []
            prewarm_errors: list[str] = []
            try:
                result = _prewarm_best_effort(
                    [competitor],
                    fields,
                    cache=cache,
                    settings=settings,
                )
                prewarm_warmed = result.get("warmed", []) if isinstance(result, dict) else []
                prewarm_errors = result.get("errors", []) if isinstance(result, dict) else []
            except Exception as exc:  # noqa: BLE001
                print(f"  Prewarm skipped (exception): {exc}")
            t_prewarm_end = time.monotonic()
            print(
                f"  Prewarm: {t_prewarm_end - t_prewarm_start:.3f}s  "
                f"(warmed={len(prewarm_warmed)}, errors={len(prewarm_errors)})"
            )

            # --- Phase 2: end-to-end graph run ---
            db = Database(settings.db_path)
            db.init_schema()
            run_id = db.create_run(
                category="saas",
                competitors=[competitor],
                goal="competitive analysis timing",
            )

            intake = {
                "category": "saas",
                "competitors": [competitor],
                "goal": "competitive analysis timing",
                "fields": fields,
            }

            deps = GraphDeps(db=db, cache=cache, settings=settings)
            graph = build_graph(deps=deps)

            t_graph_start = time.monotonic()
            try:
                final = graph.invoke({"run_id": run_id, "db": db, "intake": intake})
            except Exception as exc:
                t_graph_end = time.monotonic()
                print(
                    f"  Graph run FAILED after {t_graph_end - t_graph_start:.3f}s: {exc}"
                )
                sys.exit(1)
            t_graph_end = time.monotonic()
            print(
                f"  Graph run: {t_graph_end - t_graph_start:.3f}s  "
                f"(phase={final['phase']}, verdict={final.get('verdict')}, "
                f"revision_round={final.get('revision_round')})"
            )

            # Count passing claims — a live run with zero passes is suspicious.
            all_claims = db.latest_claims_for_run(run_id)
            passed_count = sum(1 for c in all_claims if c.get("status") == "pass")
            print(
                f"  Claims: {len(all_claims)} total, {passed_count} passed"
            )

        elapsed = time.monotonic() - t0
        under_budget = elapsed < BUDGET_SECONDS

        print()
        print(f"  Total elapsed: {elapsed:.3f}s  (budget: {BUDGET_SECONDS:.0f}s)")
        if under_budget:
            print(f"  BUDGET OK  [{elapsed:.1f}s < {BUDGET_SECONDS:.0f}s]")
        else:
            print(f"  BUDGET EXCEEDED  [{elapsed:.1f}s >= {BUDGET_SECONDS:.0f}s]")
        print()

        if not under_budget:
            sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run offline or live harness depending on ``MINGJING_TIMING_LIVE``."""
    live = os.environ.get("MINGJING_TIMING_LIVE", "").strip() == "1"
    if live:
        _run_live()
    else:
        with tempfile.TemporaryDirectory(prefix="mingjing_timing_") as tmp_dir:
            _run_offline(tmp_dir)


if __name__ == "__main__":
    main()
