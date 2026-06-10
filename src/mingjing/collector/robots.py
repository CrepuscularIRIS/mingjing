"""robots.txt gate, called BEFORE every live fetch.

Uses the stdlib :class:`urllib.robotparser.RobotFileParser` with a per-domain
cache so robots is parsed once per host. The robots body is supplied by an
injectable ``fetch_robots(domain) -> str`` callable, which keeps the gate fully
testable offline (the Collector wires in a real fetch at runtime).

Disallowed URLs must be recorded by the caller as ``skipped_robots`` and never
fetched. If robots cannot be fetched at all, the gate fails open (allows) — the
caller still logs the attempt.

Successful parses are cached for the whole process. A *failed* fetch is NOT
cached permanently: caching ``None`` forever would let a single transient error
whitelist a domain for the lifetime of the process. Instead, failures are cached
only briefly (:data:`_FAILURE_TTL_SECONDS`) so a later request re-attempts the
fetch and can pick up a real (possibly restrictive) robots policy. A genuine
404 / empty robots is still fail-open (no robots = allow), but that decision is
re-derived on each retry rather than frozen.
"""

import logging
import time
from collections.abc import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

_USER_AGENT = "MingJingBot"

# How long a failed robots fetch stays cached before we re-attempt it. Short, so
# a transient failure cannot permanently fail-open (whitelist) a domain.
_FAILURE_TTL_SECONDS = 60.0

# Domain -> parsed robots. Only SUCCESSFUL parses are stored here.
_CACHE: dict[str, RobotFileParser] = {}
# Domain -> monotonic timestamp of the last failed fetch (short-TTL negative cache).
_FAILURES: dict[str, float] = {}


def _domain_of(url: str) -> str:
    """Return the scheme://netloc domain key for ``url``."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _load_parser(domain: str, fetch_robots: Callable[[str], str]) -> RobotFileParser | None:
    """Fetch and parse robots for ``domain``; ``None`` if it could not be loaded.

    A successful parse is cached for the process. A failure is recorded in a
    short-TTL negative cache so we do not hammer a broken host every call, yet a
    transient failure does not permanently whitelist the domain — once the TTL
    elapses the next request re-attempts the fetch.
    """
    cached = _CACHE.get(domain)
    if cached is not None:
        return cached

    failed_at = _FAILURES.get(domain)
    if failed_at is not None:
        if (time.monotonic() - failed_at) < _FAILURE_TTL_SECONDS:
            # Still within the short failure window -> stay fail-open without refetch.
            return None
        # TTL elapsed; drop the stale failure marker and re-attempt below.
        _FAILURES.pop(domain, None)

    try:
        body = fetch_robots(domain)
    except Exception as exc:  # robots unreachable -> fail open, but only briefly cached
        logger.warning("robots fetch failed for %s: %s; failing open (short TTL)", domain, exc)
        _FAILURES[domain] = time.monotonic()
        return None
    parser = RobotFileParser()
    parser.parse((body or "").splitlines())
    _CACHE[domain] = parser
    _FAILURES.pop(domain, None)
    return parser


def is_allowed(url: str, fetch_robots: Callable[[str], str]) -> bool:
    """Return whether ``url`` may be fetched per its domain's robots.txt.

    Args:
        url: The candidate URL.
        fetch_robots: Callable returning the robots.txt body for a domain key
            (``scheme://netloc``). Injected so the gate is testable offline.

    Returns:
        ``True`` if allowed (or robots could not be loaded — fail open),
        ``False`` if explicitly disallowed.
    """
    domain = _domain_of(url)
    parser = _load_parser(domain, fetch_robots)
    if parser is None:
        return True
    return parser.can_fetch(_USER_AGENT, url)


def clear_cache() -> None:
    """Clear the per-domain robots caches (test isolation helper)."""
    _CACHE.clear()
    _FAILURES.clear()
