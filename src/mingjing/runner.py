"""Production run executor: wire ``POST /runs`` to the live LangGraph loop.

The FastAPI factory accepts a ``run_executor`` callable ``(run_id: str) -> None``
that it launches in a daemon thread on ``POST /runs``. This module builds that
callable for the *production* app via :func:`make_run_executor`.

The executor:
  1. resolves ``Settings`` (lazily, if not injected),
  2. reads the run row via ``db.get_run`` (the SAME ``Database`` the API polls),
  3. builds the intake dict (category, competitors, goal, all FIELD_SCHEMAS),
  4. optionally pre-warms the LIVE cache for every (competitor × field) page,
  5. constructs :class:`mingjing.graph.GraphDeps` (real ``collect_fn`` /
     ``analyze_fn`` defaults unless fakes are injected for tests),
  6. invokes the compiled graph, and
  7. records the terminal run status (``complete`` / ``partial`` / ``error``).

Test injection: ``collect_fn`` / ``analyze_fn`` / ``prewarm=False`` let the
offline suite drive the whole flow with deterministic fakes and no network.
Production passes none, so the real collector/analyst run and prewarm warms the
live store.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
from collections.abc import Callable
from typing import Any

from .db import Database
from .schemas import active_field_schemas, use_domain
from .survey import design_survey
from .survey_fixture import fixture_for
from .survey_seed import survey_seed

_log = logging.getLogger(__name__)


def make_run_executor(
    get_db: Callable[[], Database],
    *,
    settings: Any = None,
    collect_fn: Callable[..., list[dict[str, Any]]] | None = None,
    analyze_fn: Callable[..., dict[str, Any]] | None = None,
    discover_fn: Callable[..., Any] | None = None,
    prewarm: bool = True,
) -> Callable[[str], None]:
    """Build the production run executor bound to a shared ``Database``.

    Args:
        get_db: A zero-arg callable returning the SAME :class:`Database` the API
            reads from, so the frontend's polling sees the executor's writes.
            (Do NOT open a second connection to the same file.)
        settings: Optional :class:`mingjing.config.Settings`. When ``None`` it is
            loaded lazily inside the executor via ``Settings.load()``.
        collect_fn: Optional collect callable. When ``None`` the real default in
            :class:`~mingjing.graph.GraphDeps` is used. Inject a fake in tests.
        analyze_fn: Optional analyze callable. When ``None`` the real default in
            :class:`~mingjing.graph.GraphDeps` is used. Inject a fake in tests.
        discover_fn: Optional Discovery-Mode callable
            ``(category, *, market_scope, goal, seed_competitors, max_competitors)
            -> DiscoveryResult``. Used only when a run is created with an EMPTY
            competitor list (Discovery Mode). When ``None`` a real bounded
            discovery over :func:`mingjing.collector.search.search` is used.
            Inject a deterministic fake in tests.
        prewarm: When ``True`` (production), pre-warm the LIVE cache before the
            run. Tests pass ``False`` to skip the network-touching warm-up.

    Returns:
        An executor ``run(run_id: str) -> None`` suitable for the FastAPI
        ``run_executor`` slot. It re-raises on failure (after marking the run
        ``error``) so the api thread's ``_run_with_logging`` records it.
    """

    def run(run_id: str) -> None:
        """Drive the live graph for ``run_id`` end-to-end and record its status."""
        # 1. Resolve settings and the shared DB.
        active_settings = settings
        if active_settings is None:
            from .config import Settings

            active_settings = Settings.load()
        db = get_db()

        # 2. Read the run row; bail cleanly if it vanished.
        run_row = db.get_run(run_id)
        if run_row is None:
            _log.warning("run_executor: run_id=%s not found; nothing to do", run_id)
            return

        # Apply the run's domain (if any) for the WHOLE run body so the active
        # field schema set — read at step 3 below and by every downstream
        # analyst/QA consumer — reflects this run's domain. ``use_domain`` is
        # token-based, so it resets cleanly on exit even when the executor is
        # called directly in tests. No domain -> nullcontext -> env default.
        domain = run_row.get("domain")
        domain_ctx = use_domain(domain) if domain else contextlib.nullcontext()
        with domain_ctx:
            # 3. Build the intake from the run row + the active field schema set.
            # Snapshot once so intake and pre-warm see the SAME field set.
            competitors = run_row.get("competitors") or []

            # Discovery Mode: a run created with NO competitors triggers a single
            # bounded discovery pre-step (category -> candidate products -> top N)
            # before the unchanged pipeline runs. Directed Mode (competitors set)
            # skips this entirely. Best-effort: discovery failure never aborts.
            if not competitors:
                competitors = _discover_competitors_best_effort(
                    db, run_id, run_row, discover_fn=discover_fn,
                )

            fields = list(active_field_schemas())
            intake = {
                "category": run_row.get("category"),
                "competitors": competitors,
                "goal": run_row.get("goal"),
                "fields": fields,
            }

            survey_entries = _seed_survey_lane_best_effort(
                db, run_id, competitors, run_row.get("goal") or ""
            )

            # Imports are local so ``import mingjing.runner`` stays light and
            # side-effect-free at module import.
            from .collector.cache import Cache
            from .graph import GraphDeps, build_graph, make_default_collect_fn

            # 4. Open the cache and (best-effort) pre-warm the LIVE store.
            with Cache(active_settings.cache_db_path) as cache:
                if prewarm:
                    _prewarm_best_effort(
                        competitors, fields, cache=cache,
                        settings=active_settings,
                    )

                # 5. Construct deps.
                # When no collect_fn override is provided, build the settings-aware
                # deep-collect closure so production runs use the full pipeline
                # (multi-engine search, dedup+rank, query expansion, firecrawl upgrade,
                # fetch budget cap).  When a test passes collect_fn, use it unchanged.
                #
                # Per-run depth: read the run's depth field and produce a run-scoped
                # settings copy so the collector sees the right tier knobs regardless
                # of the app-level MINGJING_DEPTH env var.  dataclasses.replace is
                # safe on frozen dataclasses — it returns a new instance.

                deps_kwargs: dict[str, Any] = {
                    "db": db,
                    "cache": cache,
                    "settings": active_settings,
                }
                if collect_fn is not None:
                    deps_kwargs["collect_fn"] = collect_fn
                else:
                    run_settings = _settings_for_run(active_settings, run_row)
                    deps_kwargs["collect_fn"] = make_default_collect_fn(run_settings)
                    deps_kwargs["settings"] = run_settings
                if analyze_fn is not None:
                    deps_kwargs["analyze_fn"] = analyze_fn
                deps = GraphDeps(**deps_kwargs)

                # 6. Invoke the compiled graph.
                graph = build_graph(deps=deps)
                try:
                    final = graph.invoke(
                        {
                            "run_id": run_id,
                            "db": db,
                            "intake": intake,
                            "sources": survey_entries,  # seed: additive RunState.sources
                        }
                    )
                except Exception as exc:
                    # 7a. Mark error, emit a TERMINAL run_error trace event, and
                    # re-raise so the api thread logs the trace. The terminal
                    # event lets the frontend render a final error state instead
                    # of spinning forever. We pass a concise message only (the
                    # exception type), never the full traceback, to avoid leaking
                    # sensitive data into the persisted trace.
                    db.set_run_status(run_id, "error")
                    from .trace_events import emit_run_error

                    emit_run_error(
                        db,
                        run_id,
                        message=f"Run failed: {type(exc).__name__}",
                    )
                    _log.exception(
                        "run_executor: graph.invoke failed for run_id=%s", run_id
                    )
                    raise

            # 7b. A reject verdict at the terminal write means the degraded path.
            is_partial = (
                isinstance(final, dict) and final.get("verdict", "pass") != "pass"
            )
            db.set_run_status(run_id, "partial" if is_partial else "complete")
            _log.info(
                "run_executor: run_id=%s finished status=%s",
                run_id,
                "partial" if is_partial else "complete",
            )

    return run


def _settings_for_run(active_settings: Any, run_row: dict[str, Any]) -> Any:
    """Return a settings copy with ``depth`` overridden from the run row.

    This is the only place per-run depth is applied; extracting it as a pure
    helper makes the depth-plumbing path unit-testable without a graph run.

    Args:
        active_settings: The app-level :class:`~mingjing.config.Settings`
            (frozen dataclass).
        run_row: The run row dict as returned by :meth:`~mingjing.db.Database.get_run`.
            Its ``"depth"`` key (if non-empty) overrides the app-level value.

    Returns:
        A new ``Settings`` instance identical to ``active_settings`` except
        ``depth`` is set to the run's depth (or the app-level default when the
        run row carries no depth).
    """
    run_depth = run_row.get("depth") or active_settings.depth
    return dataclasses.replace(active_settings, depth=run_depth)


def _default_discover(
    category: str,
    *,
    market_scope: str | None,
    goal: str | None,
    seed_competitors: tuple[str, ...],
    max_competitors: int,
) -> Any:
    """Production Discovery-Mode callable: bounded discovery over live search.

    Wraps :func:`mingjing.collector.search.search` (small top-k per query) and
    delegates to :func:`mingjing.discovery.discover_competitors`. Local imports
    keep ``import mingjing.runner`` light and side-effect-free.
    """
    from .collector.search import search
    from .discovery import discover_competitors

    def search_fn(query: str) -> list[dict[str, Any]]:
        return search(query, max_results=6)

    return discover_competitors(
        category,
        search_fn=search_fn,
        market_scope=market_scope,
        goal=goal,
        seed_competitors=seed_competitors,
        max_competitors=max_competitors,
    )


def _discover_competitors_best_effort(
    db: Database,
    run_id: str,
    run_row: dict[str, Any],
    *,
    discover_fn: Callable[..., Any] | None,
) -> list[str]:
    """Run the bounded discovery pre-step and persist the discovered competitors.

    Emits ``discovery_started`` then ``competitors_discovered`` (or
    ``discovery_empty``) trace events the frontend already polls, and persists the
    selected competitors to the run row so the report header / run list reflect
    them. Best-effort: any failure is logged and yields the seed competitors (or
    an empty list), so the run proceeds honestly rather than crashing — mirrors
    ``_seed_survey_lane_best_effort`` / ``_prewarm_best_effort``.

    Returns:
        The discovered (or seed) competitor list; ``[]`` when discovery found
        nothing and no seeds were supplied (the run then proceeds with no
        competitors and terminates honestly empty/partial).
    """
    category = run_row.get("category") or ""
    market_scope = run_row.get("market_scope")
    goal = run_row.get("goal") or ""
    seed_competitors = tuple(run_row.get("seed_competitors") or [])
    max_competitors = int(run_row.get("max_competitors") or 4)
    fn = discover_fn or _default_discover

    db.insert_trace_event(
        {
            "run_id": run_id,
            "agent": "collector",
            "node": "discover",
            "event_type": "discovery_started",
            "payload_json": json.dumps(
                {"category": category, "market_scope": market_scope},
                ensure_ascii=False,
            ),
        }
    )
    try:
        result = fn(
            category,
            market_scope=market_scope,
            goal=goal,
            seed_competitors=seed_competitors,
            max_competitors=max_competitors,
        )
        selected = list(getattr(result, "selected", []) or [])
        payload = (
            result.as_payload()
            if hasattr(result, "as_payload")
            else {"selected": selected, "candidates": [], "queries": []}
        )
    except Exception:  # noqa: BLE001 — discovery is best-effort; never abort the run
        _log.warning(
            "run_executor: discovery failed (best-effort); continuing", exc_info=True
        )
        selected = list(seed_competitors)
        payload = {"selected": selected, "candidates": [], "queries": []}

    event_type = "competitors_discovered" if selected else "discovery_empty"
    db.insert_trace_event(
        {
            "run_id": run_id,
            "agent": "collector",
            "node": "discover",
            "event_type": event_type,
            "payload_json": json.dumps(payload, ensure_ascii=False),
        }
    )
    if selected:
        db.update_run_competitors(run_id, selected)
    return selected


def _seed_survey_lane_best_effort(
    db: Database, run_id: str, competitors: list[str], goal: str,
) -> list[dict[str, Any]]:
    """Design the 问卷 card + seed survey/interview source rows for the run.

    Best-effort: a fixture/design glitch is logged (exc_info) and must never abort
    an otherwise-valid run — mirrors ``_prewarm_best_effort``. Survey/interview
    evidence is additive (``RunState.sources``) plus a ``survey_designed`` trace
    card; neither is essential to a web-only run.
    """
    entries: list[dict[str, Any]] = []
    try:
        primary = competitors[0] if competitors else ""
        design = design_survey(primary, goal)
        db.insert_trace_event(
            {
                "run_id": run_id,
                "agent": "collector",
                "node": "collect",
                "event_type": "survey_designed",
                "payload_json": json.dumps(design, ensure_ascii=False),
            }
        )
        for comp in competitors:
            entries += survey_seed(db, run_id, comp, fixture_for(comp))
    except Exception:  # noqa: BLE001 — additive enrichment must never abort the run
        _log.warning(
            "run_executor: survey lane failed (best-effort); continuing", exc_info=True
        )
    return entries


def _prewarm_best_effort(
    competitors: list[str],
    fields: list[str],
    *,
    cache: Any,
    settings: Any,
) -> None:
    """Pre-warm the LIVE cache; never let a warm-up failure abort the run.

    Uses a thin live fetch (read-only-cache fallback) for each (competitor ×
    field) page. Any exception is logged and swallowed so the graph run proceeds
    regardless of warm-up success.
    """
    try:
        from .collector.fetch import fetch_with_fallback
        from .prewarm import prewarm_all

        timeout = getattr(settings, "fetch_timeout_s", 8.0)
        mode = getattr(settings, "mode", "live_first")

        def fetch_fn(url: str) -> Any:
            return fetch_with_fallback(url, cache, timeout=timeout, mode=mode)

        result = prewarm_all(
            competitors,
            fields,
            cache=cache,
            fetch_fn=fetch_fn,
            settings=settings,
        )
        _log.info(
            "run_executor: prewarm warmed=%d errors=%d",
            len(result.get("warmed", [])),
            len(result.get("errors", [])),
        )
    except Exception:  # noqa: BLE001 — best-effort; warm-up must never abort the run
        _log.warning("run_executor: prewarm failed (best-effort); continuing", exc_info=True)
