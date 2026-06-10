"""Collector agent — thin orchestration over the existing collector modules.

Pipeline: ``search`` -> ``robots.is_allowed`` -> ``fetch.fetch_with_fallback``
-> evidence chunks. This is the network-touching agent; it is wired from the
already-unit-tested primitives and is exercised live in the demo runs (not unit
tested here — see :mod:`tests.test_writer_projection` for the import check).

Deep-collect extension (Task 6):
When ``engines`` is provided, the deep pipeline runs instead:
  1. Query expansion (if ``expand`` callable given).
  2. Parallel multi-engine search via :func:`~mingjing.collector.search.parallel_search`.
  3. Dedup + quality rank via :func:`~mingjing.collector.dedupe.dedupe_and_rank`.
  4. Fetch with robots gate (same as legacy path), respecting ``top_k or source_cap``
     fetch cap per call.  A budget counter is managed by the closure in
     :func:`~mingjing.graph.make_default_collect_fn`.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from typing import Any

from ..collector import robots
from ..collector.dedupe import dedupe_and_rank
from ..collector.fetch import FetchResult, fetch_with_fallback
from ..collector.search import parallel_search
from ..collector.search import search as _search_fn

logger = logging.getLogger(__name__)

# Cap robots.txt redirect hops, mirroring fetch._MAX_REDIRECTS.
_MAX_ROBOTS_REDIRECTS = 5
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _default_fetch_robots(domain: str) -> str:
    """Fetch a domain's ``robots.txt`` body (live), SSRF-guarded.

    Redirects are followed MANUALLY (``allow_redirects=False``) and every hop is
    re-validated with :func:`is_safe_url`, mirroring :func:`fetch._live_fetch`.
    Otherwise a safe-looking public host could ``3xx`` the robots fetch to a
    private/loopback/metadata target and the guard — which only saw the initial
    URL — would be bypassed.

    A blocked URL/redirect (or too many redirects) RAISES, so
    :func:`robots._load_parser` records it in the short-TTL *failure* cache
    (fail-open briefly, re-attempt later) rather than parsing and PERMANENTLY
    caching an empty body as a successful allow-all policy. A genuine ``4xx`` /
    empty robots returns ``""`` (no robots = allow), which is a real success and
    is correctly cached.
    """
    from urllib.parse import urljoin

    import requests

    from ..collector.fetch import is_safe_url

    current = f"{domain}/robots.txt"
    for _ in range(_MAX_ROBOTS_REDIRECTS + 1):
        if not is_safe_url(current):
            raise ValueError(f"Blocked unsafe robots URL (SSRF guard): {current}")
        resp = requests.get(current, timeout=5, allow_redirects=False)
        if getattr(resp, "is_redirect", False) or resp.status_code in _REDIRECT_STATUSES:
            location = resp.headers.get("Location")
            if not location:
                break
            current = urljoin(current, location)  # re-validated at loop top
            continue
        break
    else:
        raise ValueError(
            f"Too many robots redirects (SSRF guard) starting at {domain}"
        )
    return resp.text if resp.status_code < 400 else ""


def collect(
    query: str,
    cache: Any,
    *,
    max_results: int = 5,
    source_cap: int = 3,
    timeout: float = 8.0,
    mode: str = "live_first",
    fetch_robots: Callable[[str], str] | None = None,
    # Deep-collect params (Task 6) — all default to legacy-compatible values.
    engines: dict[str, Callable[[str], list[dict[str, Any]]]] | None = None,
    top_k: int | None = None,
    workers: int = 1,
    firecrawl: Callable[[str], FetchResult | None] | None = None,
    min_chars: int = 0,
    competitor: str = "",
    expand: Callable[[str], list[str]] | None = None,
    include_snippets: bool = False,
) -> list[dict[str, Any]]:
    """Collect evidence for ``query`` into source/evidence-chunk dicts.

    For each search hit: gate on robots.txt (disallowed -> recorded as
    ``skipped_robots``, never fetched), then fetch with a cache fallback. The
    fetched text becomes one evidence chunk carrying its provenance.

    Args:
        query: Search query.
        cache: Read-only cache passed through to :func:`fetch_with_fallback`.
        max_results: Search breadth (legacy path only).
        source_cap: Max number of fetched sources to keep (per-field cap).
        timeout: Per-fetch timeout in seconds.
        mode: ``"live_first"`` or ``"cache_first"``.
        fetch_robots: Robots-body fetcher (injectable for tests).
        engines: When provided (non-empty), activates the DEEP pipeline:
            a mapping of engine-name → ``(query) -> list[preview]`` callables,
            already bound to their API keys by the caller.  ``None`` (default)
            preserves the legacy single-query path byte-for-byte.
        top_k: Maximum results after dedup+rank (deep path).  Defaults to
            ``source_cap`` when ``None``.
        workers: Worker count for :func:`parallel_search` (deep path).
        firecrawl: Optional Firecrawl-bound fetch callable forwarded to
            :func:`fetch_with_fallback` (deep path).
        min_chars: Minimum characters threshold for Firecrawl upgrade (deep
            path); forwarded to :func:`fetch_with_fallback`.
        competitor: Competitor name for dedup authority scoring (deep path).
        expand: Optional bound callable ``(base_query) -> list[str]`` for query
            expansion (deep path).  When ``None``, ``[query]`` is used as-is.

    Returns:
        A list of ``{"url", "title", "snippet", "fetched", ...}`` dicts. Skipped
        (robots-disallowed) hits are included with ``"fetched": False``.
    """
    fetch_robots = fetch_robots or _default_fetch_robots

    # ------------------------------------------------------------------
    # Legacy path: engines=None (or empty) → existing single-query flow.
    # MUST remain byte-identical to the pre-Task-6 implementation.
    # ------------------------------------------------------------------
    if not engines:
        hits = _search_fn(query, max_results=max_results)
        collected: list[dict[str, Any]] = []

        for hit in hits:
            if len([c for c in collected if c.get("fetched")]) >= source_cap:
                break
            url = hit.get("url", "")
            if not url:
                continue
            if not robots.is_allowed(url, fetch_robots):
                logger.info("skipped_robots: %s", url)
                collected.append({**hit, "fetched": False, "reason": "skipped_robots"})
                continue
            try:
                result: FetchResult = fetch_with_fallback(
                    url, cache=cache, timeout=timeout, mode=mode
                )
            except LookupError:
                collected.append({**hit, "fetched": False, "reason": "fetch_failed"})
                continue
            collected.append(
                {
                    **hit,
                    "fetched": True,
                    "source_id": str(uuid.uuid4()),
                    "source_mode": result.source_mode,
                    "text": result.text,
                    "content_hash": result.content_hash,
                    "fetched_at": result.fetched_at,
                }
            )
        return collected

    # ------------------------------------------------------------------
    # Deep pipeline: engines provided.
    #
    # Two DISTINCT caps, decoupled so breadth doesn't cost fetch budget:
    #   - candidate_k: how many ranked candidates to consider (cheap; the snippet
    #     pool). Driven by top_k (the depth-tier candidate pool).
    #   - fetch_cap:   how many EXPENSIVE full-page fetches to perform this call.
    #     Driven by source_cap (the graph's round-aware 1+revision_round budget).
    # When include_snippets is on, ranked candidates beyond fetch_cap still become
    # evidence via their search snippet (no fetch) — large breadth, tiny cost.
    # ------------------------------------------------------------------
    candidate_k = top_k if top_k is not None else source_cap
    fetch_cap = source_cap if source_cap is not None else candidate_k

    # 1. Query expansion (best-effort — expand is a pre-bound callable).
    try:
        queries: list[str] = expand(query) if callable(expand) else [query]
        if not queries:
            queries = [query]
    except Exception:
        logger.warning("collect: query expansion failed; falling back to base query", exc_info=True)
        queries = [query]

    # 2. Parallel multi-engine search.
    previews = parallel_search(queries, engines, workers=workers)

    # 3. Dedup + quality rank (candidate pool sized by candidate_k).
    ranked = dedupe_and_rank(
        previews,
        top_k=candidate_k,
        per_domain_cap=2,
        competitor=competitor,
        query=query,
    )

    # 4. Robots-gate + fetch the top `fetch_cap`; snippet-evidence the rest.
    #
    # The cap bounds fetch ATTEMPTS (success OR failure), not just successes —
    # each attempt is a real network cost that the closure charges to the run
    # fetch budget. Counting only successes would let a run of failed fetches
    # attempt (and bill) far more than fetch_cap before the budget catches up.
    # A robots-disallowed candidate is skipped without a fetch, so it does NOT
    # consume an attempt (mirrors the budget, which never counts skipped_robots).
    collected_deep: list[dict[str, Any]] = []
    fetch_attempts = 0
    for hit in ranked:
        url = hit.get("url", "")
        if not url:
            continue

        if fetch_attempts < fetch_cap:
            # Within the fetch budget → attempt a real full-page fetch.
            if not robots.is_allowed(url, fetch_robots):
                logger.info("skipped_robots: %s", url)
                collected_deep.append({**hit, "fetched": False, "reason": "skipped_robots"})
                continue
            fetch_attempts += 1  # count BEFORE the call: a failed fetch still costs
            try:
                result = fetch_with_fallback(
                    url,
                    cache,
                    timeout=timeout,
                    mode=mode,
                    firecrawl=firecrawl,
                    min_chars=min_chars,
                )
            except LookupError:
                collected_deep.append({**hit, "fetched": False, "reason": "fetch_failed"})
                continue
            collected_deep.append(
                {
                    **hit,
                    "fetched": True,
                    "source_id": str(uuid.uuid4()),
                    "source_mode": result.source_mode,
                    "text": result.text,
                    "content_hash": result.content_hash,
                    "fetched_at": result.fetched_at,
                }
            )
            continue

        # Beyond the fetch budget → snippet-as-evidence (no fetch). The search
        # snippet IS the evidence text; raw_text == snippet means the QA
        # HALLUCINATED_SNIPPET substring check is self-consistent.
        snippet = (hit.get("snippet") or "").strip()
        if include_snippets and snippet:
            collected_deep.append(
                {
                    **hit,
                    "fetched": True,
                    "from_snippet": True,
                    "source_id": str(uuid.uuid4()),
                    "source_mode": "SNIPPET",
                    "text": snippet,
                    "content_hash": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                    "fetched_at": None,
                }
            )
    return collected_deep
