"""Web search with a pluggable provider chain.

Provider chain resolution
-------------------------
The ``provider`` argument (or env ``MINGJING_SEARCH_PROVIDER``, default ``"auto"``)
controls which engines are tried, in order:

- ``"auto"`` — if a SearXNG URL is configured (``searxng_url`` arg or env
  ``MINGJING_SEARXNG_URL``, non-empty) the chain is ``["searxng", "duckduckgo"]``;
  otherwise it falls back to ``["duckduckgo"]`` only (today's behaviour unchanged).
- Explicit value — a single provider name or a comma-separated list, e.g.
  ``"searxng,duckduckgo"`` — used as the exact ordered chain.

Each provider is tried in sequence; the first that returns a non-empty list wins.
All provider failures are non-fatal: they log a warning and return ``[]``, so the
next provider in the chain gets a chance.

SearXNG provider notes
----------------------
Requires a self-hosted SearXNG instance with JSON output enabled in its
``settings.yml``::

    search:
      formats: [html, json]

Quick bring-up::

    docker run -d -p 8080:8080 --name searxng searxng/searxng

Then point ``MINGJING_SEARXNG_URL=http://localhost:8080`` at it.
Omitting that variable keeps the DuckDuckGo-only default.
"""

import concurrent.futures
import logging
import os
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_S = 1.5


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def _duckduckgo_search(query: str, max_results: int) -> list[dict[str, Any]]:
    """Search via DuckDuckGo (keyless).  Never raises."""
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:  # pragma: no cover - alternate package name
        from ddgs import DDGS  # type: ignore

    results: list[dict[str, Any]] = []
    try:
        # Bound the backend: DDG is in every depth tier and parallel_search blocks
        # on executor join, so an un-timed-out DDGS hang would freeze the whole run
        # (matches the other providers' timeout=8).
        with DDGS(timeout=8) as ddgs:
            for hit in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "url": hit.get("href") or hit.get("url", ""),
                        "title": hit.get("title", ""),
                        "snippet": hit.get("body") or hit.get("snippet", ""),
                    }
                )
    except Exception as exc:  # network/backend hiccups must not crash a run
        logger.warning("duckduckgo search failed for %r: %s", query, exc)
        return results
    return results


def _is_valid_searxng_url(url: str) -> bool:
    """Lenient validation for the operator-configured SearXNG endpoint.

    Unlike :func:`mingjing.collector.fetch.is_safe_url` (which is the public-only
    SSRF guard applied to *untrusted, discovered* fetch targets), the SearXNG
    instance URL is TRUSTED operator configuration read from
    ``MINGJING_SEARXNG_URL`` — and a self-hosted SearXNG is *meant* to live on
    ``localhost`` or an internal host. Applying the public-only guard here would
    block the documented loopback deployment, so we only enforce that the URL is
    a well-formed ``http``/``https`` URL with a hostname (rejecting ``file://``,
    ``gopher://`` and malformed input). ``allow_redirects=False`` on the request
    below prevents the response itself from bouncing the call elsewhere.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def _searxng_search(
    query: str,
    max_results: int,
    instance_url: str,
) -> list[dict[str, Any]]:
    """Search via a self-hosted SearXNG instance (keyless).  Never raises."""
    import requests  # lazy import — avoids hard dep at module level

    request_url = f"{instance_url.rstrip('/')}/search"
    if not _is_valid_searxng_url(request_url):
        logger.warning("searxng instance URL is not a valid http(s) URL: %r", request_url)
        return []

    params = {"q": query, "format": "json", "categories": "general"}
    try:
        resp = requests.get(
            request_url, params=params, timeout=8, allow_redirects=False
        )
        if resp.status_code >= 400:
            logger.warning(
                "searxng returned HTTP %s for %r", resp.status_code, query
            )
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("searxng search failed for %r: %s", query, exc)
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", [])[:max_results]:
        results.append(
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("content") or item.get("snippet", ""),
            }
        )
    return results


def _tavily_search(query: str, max_results: int, api_key: str) -> list[dict[str, Any]]:
    """Search via Tavily API (key-required).  Never raises."""
    if not api_key:
        logger.warning("tavily api_key is empty, skipping search for %r", query)
        return []

    import requests  # lazy import — avoids hard dep at module level

    url = "https://api.tavily.com/search"
    payload = {"api_key": api_key, "query": query, "max_results": max_results}
    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code >= 400:
            logger.warning(
                "tavily returned HTTP %s for %r", resp.status_code, query
            )
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("tavily search failed for %r: %s", query, exc)
        return []

    results: list[dict[str, Any]] = []
    raw = data.get("results")
    if not raw:
        return []
    for r in raw[:max_results]:
        results.append(
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
            }
        )
    return results


def _brave_search(query: str, max_results: int, api_key: str) -> list[dict[str, Any]]:
    """Search via Brave Search API (key-required).  Never raises."""
    if not api_key:
        logger.warning("brave api_key is empty, skipping search for %r", query)
        return []

    import requests  # lazy import — avoids hard dep at module level

    url = "https://api.search.brave.com/res/v1/web/search"
    count = min(max_results, 20)  # Brave API caps count at 20
    params = {"q": query, "count": count}
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        if resp.status_code >= 400:
            logger.warning(
                "brave returned HTTP %s for %r", resp.status_code, query
            )
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("brave search failed for %r: %s", query, exc)
        return []

    results: list[dict[str, Any]] = []
    web = data.get("web")
    if not web:
        return []
    for r in web.get("results", []):
        results.append(
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("description", ""),
            }
        )
    return results


def _bocha_search(query: str, max_results: int, api_key: str) -> list[dict[str, Any]]:
    """Search via 博查 Bocha Web Search API (key-required).  Never raises.

    Bocha (``api.bochaai.com``) is a China-reachable AI search API with good
    CN + EN coverage — the recommended primary engine when the demo runs from a
    China network (foreign engines like Tavily/DDG are throttled/blocked there).

    Response shape (Bing-compatible)::

        {"code": 200, "data": {"webPages": {"value": [
            {"name": ..., "url": ..., "snippet": ..., "summary": ...}, ...
        ]}}}

    We prefer ``summary`` (longer, returned when ``summary=true``) over the short
    ``snippet`` for richer evidence; fall back to ``snippet`` when absent.

    Response shape is verified against BochaAI's two official integrations
    (``bocha-search-mcp`` and ``open-webui-Bocha``): the web result list lives at
    ``response["data"]["webPages"]["value"]`` with per-item keys ``name`` /
    ``url`` / ``snippet`` / ``summary``. Navigation below is defensive at this
    untrusted boundary: it also tolerates a missing ``data`` wrapper (``webPages``
    at top level) and non-dict levels, returning ``[]`` rather than raising.
    """
    if not api_key:
        logger.warning("bocha api_key is empty, skipping search for %r", query)
        return []

    import requests  # lazy import — avoids hard dep at module level

    url = "https://api.bochaai.com/v1/web-search"
    payload = {"query": query, "summary": True, "count": min(max_results, 50)}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        if resp.status_code >= 400:
            logger.warning("bocha returned HTTP %s for %r", resp.status_code, query)
            return []
        body = resp.json()
    except Exception as exc:
        logger.warning("bocha search failed for %r: %s", query, exc)
        return []

    # Canonical: body["data"]["webPages"]["value"]. Tolerate a missing "data"
    # wrapper (webPages at top level) and guard every level's type.
    if not isinstance(body, dict):
        return []
    container = body.get("data")
    if not isinstance(container, dict):
        container = body  # no "data" wrapper → look for webPages at top level
    web_pages = container.get("webPages")
    pages = web_pages.get("value") if isinstance(web_pages, dict) else None
    if not isinstance(pages, list) or not pages:
        return []

    results: list[dict[str, Any]] = []
    for r in pages[:max_results]:
        if not isinstance(r, dict):
            continue
        results.append(
            {
                "url": r.get("url") or r.get("displayUrl", ""),
                "title": r.get("name") or r.get("title", ""),
                "snippet": r.get("summary") or r.get("snippet", ""),
            }
        )
    return results


def parallel_search(
    queries: list[str],
    engines: dict[str, Callable[[str], list[dict[str, Any]]]],
    *,
    workers: int = 8,
) -> list[dict[str, Any]]:
    """Run every (query × engine) pair concurrently and merge results.

    Args:
        queries: List of search queries.
        engines: Mapping of engine-name → callable ``(query) -> list[preview]``.
            Each callable is already bound to its key/max_results by the caller
            (keeps this function key-agnostic and offline-testable).
        workers: Maximum ThreadPoolExecutor workers.

    Returns:
        Flat merged list of preview dicts, each tagged with ``"engine": <name>``.
        A failing engine callable is silently dropped (warning logged); it does
        not abort the batch.  Order is not guaranteed; dedup happens downstream.
    """
    if not queries or not engines:
        return []

    pairs = [(q, name, fn) for q in queries for name, fn in engines.items()]

    def _call(query: str, name: str, fn: Callable[[str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        try:
            hits = fn(query)
        except Exception as exc:
            logger.warning("parallel_search: engine %r raised for %r: %s", name, query, exc)
            return []
        tagged: list[dict[str, Any]] = []
        for h in hits:
            item = dict(h)
            item["engine"] = name
            tagged.append(item)
        return tagged

    merged: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_call, q, name, fn): (q, name) for q, name, fn in pairs}
        for fut in concurrent.futures.as_completed(futures):
            try:
                merged.extend(fut.result())
            except Exception as exc:
                q, name = futures[fut]
                logger.warning(
                    "parallel_search: executor exception for engine %r query %r: %s",
                    name, q, exc,
                )

    return merged


# ---------------------------------------------------------------------------
# Public factory for bound-provider callables (used by graph.py)
# ---------------------------------------------------------------------------


def bind_provider(
    name: str,
    *,
    top_k: int,
    tavily_key: str = "",
    brave_key: str = "",
    bocha_key: str = "",
    searxng_url: str = "",
) -> Callable[[str], list[dict[str, Any]]] | None:
    """Return a bound ``(query) -> previews`` callable for engine *name*, or ``None``.

    Binds ``top_k`` and any required credential/URL into the closure so the
    returned callable matches the ``(query: str) -> list[dict]`` contract
    expected by :func:`parallel_search`.

    Returns ``None`` for engines that cannot run:
    - ``"searxng"`` with an empty *searxng_url*
    - any unknown engine name

    Args:
        name: Engine identifier — one of ``"tavily"``, ``"brave"``, ``"bocha"``,
            ``"duckduckgo"``, ``"searxng"``.
        top_k: Maximum results to request from the provider.
        tavily_key: Tavily API key (required for ``"tavily"``).
        brave_key: Brave Search subscription token (required for ``"brave"``).
        bocha_key: 博查 Bocha API key (required for ``"bocha"``).
        searxng_url: Base URL of the SearXNG instance (required for ``"searxng"``).

    Returns:
        A bound callable, or ``None`` if the engine is unavailable.
    """
    if name == "tavily":
        def _tavily(q: str) -> list[dict[str, Any]]:
            return _tavily_search(q, top_k, tavily_key)
        return _tavily
    if name == "brave":
        def _brave(q: str) -> list[dict[str, Any]]:
            return _brave_search(q, top_k, brave_key)
        return _brave
    if name == "bocha":
        def _bocha(q: str) -> list[dict[str, Any]]:
            return _bocha_search(q, top_k, bocha_key)
        return _bocha
    if name == "duckduckgo":
        def _ddg(q: str) -> list[dict[str, Any]]:
            return _duckduckgo_search(q, top_k)
        return _ddg
    if name == "searxng":
        if not searxng_url.strip():
            return None
        def _searxng(q: str) -> list[dict[str, Any]]:
            return _searxng_search(q, top_k, searxng_url)
        return _searxng
    # Unknown engine
    return None


# ---------------------------------------------------------------------------
# Chain resolver + public API
# ---------------------------------------------------------------------------


def _resolve_chain(provider: str | None, searxng_url: str | None) -> list[str]:
    """Return an ordered list of provider names to try."""
    effective = (
        provider
        or os.environ.get("MINGJING_SEARCH_PROVIDER", "auto")
    ).strip().lower()

    if effective != "auto":
        return [p.strip() for p in effective.split(",") if p.strip()]

    # "auto": use SearXNG only when a URL is configured
    resolved_url = searxng_url or os.environ.get("MINGJING_SEARXNG_URL", "")
    if resolved_url.strip():
        return ["searxng", "duckduckgo"]
    return ["duckduckgo"]


def search(
    query: str,
    max_results: int = 5,
    *,
    provider: str | None = None,
    searxng_url: str | None = None,
    retries: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Run a web search using a pluggable provider chain.

    Args:
        query: The search query.
        max_results: Maximum number of results to return.
        provider: Provider name or comma-separated chain, e.g. ``"searxng,duckduckgo"``.
            Defaults to ``MINGJING_SEARCH_PROVIDER`` env var (default ``"auto"``).
        searxng_url: Base URL of the SearXNG instance.
            Defaults to ``MINGJING_SEARXNG_URL`` env var (default ``"http://localhost:8080"``).
        retries: Number of extra attempts per provider on empty result (>= 0).
            Defaults to ``MINGJING_SEARCH_RETRIES`` env var (default ``2``).
        sleep_fn: Callable used to sleep between retry attempts.  Inject a no-op
            in tests to avoid real delays.

    Returns:
        A list of ``{"url", "title", "snippet"}`` dicts (possibly empty — search
        failures are non-fatal and never raise).
    """
    chain = _resolve_chain(provider, searxng_url)
    effective_searxng_url = (
        searxng_url
        or os.environ.get("MINGJING_SEARXNG_URL", "http://localhost:8080")
    )

    # Resolve retries: param > env > default 2; clamp to >= 0.
    if retries is None:
        try:
            retries = int(os.environ.get("MINGJING_SEARCH_RETRIES", "2"))
        except ValueError:
            retries = 2
    retries = max(0, retries)

    for name in chain:
        # tavily/brave are deep-collect engines consumed via parallel_search (bound
        # callables), not this legacy single-query chain — intentionally not dispatched here.
        if name not in ("searxng", "duckduckgo"):
            logger.warning("unknown search provider %r, skipping", name)
            continue

        for attempt in range(retries + 1):
            try:
                if name == "searxng":
                    hits = _searxng_search(query, max_results, effective_searxng_url)
                else:  # duckduckgo
                    hits = _duckduckgo_search(query, max_results)
            except Exception as exc:  # belt-and-suspenders; providers should not raise
                logger.warning("provider %r raised unexpectedly: %s", name, exc)
                hits = []

            if hits:
                logger.info(
                    "search(%r): %d hits from provider %r", query, len(hits), name
                )
                return hits

            # Empty result on this attempt.
            remaining = retries - attempt
            if remaining > 0:
                logger.info(
                    "provider %r empty, retrying (%d/%d)", name, attempt + 1, retries
                )
                sleep_fn(_RETRY_BACKOFF_S)
            # else: last attempt for this provider — move to next in chain

    logger.warning("all search providers returned empty for %r", query)
    return []
