"""Firecrawl JS-render fetch fallback.

Provides :func:`firecrawl_fetch`, which POSTs to the Firecrawl ``/scrape``
endpoint to obtain a fully JS-rendered version of a page. This is useful for
SPAs (e.g. feishu.cn) that return an 8-char shell to a plain ``requests.get``
but render kilobytes of real content after JavaScript executes.

Design decisions:
- Lazy ``import requests`` to keep the module importable in environments where
  requests is not installed (though it is a project dependency).
- NEVER raises — all failure modes return None and log a warning. The caller
  decides whether to fall back to the plain result.
- Key-agnostic fetch.py: the ``api_key`` / ``base_url`` / ``timeout`` are bound
  here, and the caller passes a zero-argument-style partial to
  :func:`~mingjing.collector.fetch.fetch_with_fallback`. This keeps fetch.py
  offline-testable without any Firecrawl knowledge.
"""

import logging
from collections.abc import Callable

from mingjing.collector.fetch import FetchResult

logger = logging.getLogger(__name__)


def firecrawl_fetch(
    url: str,
    *,
    api_key: str,
    base_url: str,
    timeout: float = 20.0,
) -> FetchResult | None:
    """Fetch ``url`` via the Firecrawl ``/scrape`` endpoint.

    Args:
        url: Target URL to render server-side.
        api_key: Firecrawl API key (``Bearer`` token). Empty string → return
            ``None`` immediately without making any network call.
        base_url: Firecrawl API base URL, e.g.
            ``"https://api.firecrawl.dev/v1"``.
        timeout: Request timeout in seconds.

    Returns:
        A :class:`~mingjing.collector.fetch.FetchResult` with
        ``source_mode="LIVE"`` on success, or ``None`` on any failure
        (HTTP >= 400, network exception, empty rendered text, empty key).
    """
    if not api_key:
        logger.debug("firecrawl_fetch: empty api_key — skipping network call.")
        return None

    import requests  # lazy import

    scrape_url = f"{base_url.rstrip('/')}/scrape"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"url": url, "formats": ["markdown"]}

    try:
        resp = requests.post(scrape_url, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:
        logger.warning("firecrawl_fetch: request exception for %s: %s", url, exc)
        return None

    if not resp.ok:
        logger.warning(
            "firecrawl_fetch: HTTP %s for %s", resp.status_code, url
        )
        return None

    try:
        body = resp.json()
        data = body.get("data", {})
        # Prefer markdown; fall back to content.
        text: str = data.get("markdown") or data.get("content") or ""
    except Exception as exc:
        logger.warning("firecrawl_fetch: JSON parse error for %s: %s", url, exc)
        return None

    if not text.strip():
        logger.warning("firecrawl_fetch: empty rendered text for %s", url)
        return None

    return FetchResult(text=text, url=url, source_mode="LIVE")


def make_firecrawl_fn(
    api_key: str,
    base_url: str,
    timeout: float = 20.0,
) -> Callable[[str], FetchResult | None]:
    """Return a single-argument callable ``(url) -> FetchResult | None``.

    Binds ``api_key``, ``base_url``, and ``timeout`` into a closure so the
    result can be passed directly as the ``firecrawl=`` argument of
    :func:`~mingjing.collector.fetch.fetch_with_fallback` without exposing
    Firecrawl credentials to that module.

    Example::

        fn = make_firecrawl_fn(api_key=os.environ["FIRECRAWL_API_KEY"],
                               base_url="https://api.firecrawl.dev/v1")
        result = fetch_with_fallback(url, cache, firecrawl=fn, min_chars=200)
    """

    def _fetch(url: str) -> FetchResult | None:
        return firecrawl_fetch(url, api_key=api_key, base_url=base_url, timeout=timeout)

    return _fetch
