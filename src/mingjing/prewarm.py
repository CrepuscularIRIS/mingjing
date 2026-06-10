"""Demo-start pre-warm: populate the LIVE cache store for all competitors × fields.

At demo start, call :func:`prewarm_all` to batch-fetch every (competitor × field)
page into the Cache so the first live graph run hits ``CACHED`` entries rather
than a cold network. Concurrency is bounded by ``max_workers`` via a
:class:`~concurrent.futures.ThreadPoolExecutor`; an optional ``min_interval_s``
gate space-out request STARTS to respect any polite crawl constraint.

Design discipline:
- A ``fetch_fn`` exception for one URL is captured in ``errors`` and never aborts
  the whole storm — partial warm-up is better than no warm-up.
- The module has NO dependency on ``graph.py`` (it closes over a cache and a
  callable), keeping the import graph clean.
- All shared state (``_in_flight`` counter, ``_last_start`` gate) is protected by
  threading locks — safe against concurrent ThreadPoolExecutor workers.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .collector.fetch import FetchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Default URL template: ``{competitor}_{field}`` slug — deliberately offline-safe
# for the test harness.  Real demo wires a proper URL resolver via ``fetch_fn``.
_DEFAULT_URL_TEMPLATE = "https://{competitor}.example.com/{field}"


def _default_url_for(competitor: str, field: str) -> str:
    """Produce a placeholder URL for a (competitor, field) pair.

    This default is intentionally unresolvable so accidental calls without an
    injected ``fetch_fn`` fail fast rather than hitting random hosts.
    """
    slug = competitor.lower().replace(" ", "-")
    return _DEFAULT_URL_TEMPLATE.format(competitor=slug, field=field)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prewarm_all(
    competitors: list[str],
    fields: list[str],
    *,
    cache: Any,
    fetch_fn: Callable[[str], FetchResult] | None = None,
    analyze_fn: Callable[..., Any] | None = None,
    db: Any = None,
    max_workers: int = 4,
    min_interval_s: float = 0.0,
    settings: Any = None,
    url_for: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Pre-fetch every (competitor × field) page into ``cache``.

    Builds a work list of ``(competitor, field, url)`` triples from the
    cross-product of ``competitors`` × ``fields``, then fans them out over a
    bounded :class:`~concurrent.futures.ThreadPoolExecutor`.  Each successful
    fetch is written to ``cache.put``; each exception is captured in
    ``result["errors"]`` and never aborts the whole storm.

    Args:
        competitors: List of competitor name tokens (e.g. ``["Acme", "Beta"]``).
        fields: List of field names (e.g. ``["pricing_model", "feature_tree"]``).
        cache: A :class:`mingjing.collector.cache.Cache` instance (the LIVE store
            written to).  Must expose ``put(FetchResult)``.
        fetch_fn: Callable ``(url: str) -> FetchResult``.  Defaults to a real
            ``requests``-backed fetch via
            :func:`mingjing.collector.fetch._live_fetch`.  Inject a fake for
            offline/test paths.
        analyze_fn: Optional callable to pre-warm the analyst (e.g. prime an LLM
            context).  Signature: ``(text: str, competitor: str, field: str) ->
            Any``.  When ``None``, fetch-only warm is performed.
        db: Optional :class:`mingjing.db.Database`; passed through to
            ``analyze_fn`` when provided.
        max_workers: Maximum number of concurrent in-flight fetch threads.
        min_interval_s: Minimum seconds between request STARTS.  ``0.0``
            (default) disables the gate.
        settings: Optional :class:`mingjing.config.Settings`; unused by
            ``prewarm_all`` itself but forwarded to ``analyze_fn`` when provided.
        url_for: Optional ``(competitor, field) -> str`` resolver.  Defaults to
            :func:`_default_url_for`.  Inject a real URL map for the live demo.

    Returns:
        A dict with three keys:

        - ``"warmed"`` — list of ``(competitor, field, url, source_mode)`` tuples
          for every successfully fetched URL.
        - ``"errors"`` — list of ``{"competitor", "field", "url", "error"}``
          dicts for every failed fetch.
        - ``"_peak_in_flight"`` — int; the maximum number of worker threads that
          were simultaneously in-flight during this call (test observability).
    """
    if fetch_fn is None:
        from .collector.fetch import _live_fetch

        def fetch_fn(url: str) -> FetchResult:  # type: ignore[misc]
            timeout = getattr(settings, "fetch_timeout_s", 8.0) if settings else 8.0
            return _live_fetch(url, timeout)

    _url_for = url_for or _default_url_for

    # Build the full (competitor × field) work list.
    work: list[tuple[str, str, str]] = [
        (comp, fld, _url_for(comp, fld))
        for comp in competitors
        for fld in fields
    ]

    # --- rate-gate state (shared across workers) ----------------------------
    _gate_lock = threading.Lock()
    # Initialise to `now - min_interval_s` so the very first worker never waits.
    _last_start: list[float] = [time.monotonic() - min_interval_s]

    def _wait_for_gate() -> None:
        """Block until the minimum inter-request interval has elapsed.

        The lock is held only long enough to read the previous start time and
        *claim* the next slot — the actual sleep happens outside the lock so
        multiple workers can sleep concurrently rather than queuing up
        single-file behind the lock.
        """
        if min_interval_s <= 0.0:
            return
        with _gate_lock:
            now = time.monotonic()
            wait = max(0.0, min_interval_s - (now - _last_start[0]))
            _last_start[0] = now + wait  # claim the next slot before releasing
        if wait:
            time.sleep(wait)

    # --- concurrency counter (for test observability) ----------------------
    _concurrency_lock = threading.Lock()
    _in_flight: list[int] = [0]
    _peak_in_flight: list[int] = [0]

    def _fetch_one(competitor: str, field: str, url: str) -> dict[str, Any]:
        """Fetch a single URL, record in cache, return a status dict."""
        _wait_for_gate()

        with _concurrency_lock:
            _in_flight[0] += 1
            if _in_flight[0] > _peak_in_flight[0]:
                _peak_in_flight[0] = _in_flight[0]

        try:
            result = fetch_fn(url)
            cache.put(result)

            if analyze_fn is not None:
                try:
                    analyze_fn(result.text, competitor, field, db=db, settings=settings)
                except Exception as _exc:  # noqa: BLE001
                    logger.warning(
                        "analyze_fn warm failed for %s/%s: %s",
                        competitor, field, _exc,
                    )  # best-effort: don't re-raise

            return {
                "ok": True,
                "competitor": competitor,
                "field": field,
                "url": url,
                "source_mode": result.source_mode,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "competitor": competitor,
                "field": field,
                "url": url,
                "error": str(exc),
            }
        finally:
            with _concurrency_lock:
                _in_flight[0] -= 1

    warmed: list[tuple[str, str, str, str]] = []
    errors: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_one, comp, fld, url): (comp, fld, url)
            for comp, fld, url in work
        }
        for fut in as_completed(futures):
            status = fut.result()
            if status["ok"]:
                warmed.append(
                    (
                        status["competitor"],
                        status["field"],
                        status["url"],
                        status["source_mode"],
                    )
                )
            else:
                errors.append(
                    {
                        "competitor": status["competitor"],
                        "field": status["field"],
                        "url": status["url"],
                        "error": status["error"],
                    }
                )

    return {
        "warmed": warmed,
        "errors": errors,
        "_peak_in_flight": _peak_in_flight[0],  # exposed for test observability
    }
