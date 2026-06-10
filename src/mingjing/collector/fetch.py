"""Live fetch with a read-only-cache fallback and a lightweight SSRF guard.

Per the D0 decision (the LDR import-closure spike was *not* run), this module
does NOT vendor heavy ``local-deep-research`` modules. Instead it uses a thin
``requests`` + ``BeautifulSoup`` ``_live_fetch`` and a small built-in
``is_safe_url`` SSRF guard.

Contract:
- ``live_first`` (default): try ``_live_fetch``; on ``TimeoutError``, HTTP
  4xx/5xx, or *any* exception, fall back to the read-only ``cache`` and tag the
  result ``source_mode="CACHED"``. A live success is tagged ``"LIVE"``.
- ``cache_first`` (the D0 auto-downgrade): read the cache first; only if the
  cache misses do we attempt a live fetch.

Unit tests monkeypatch ``_live_fetch`` so no real network is hit.
"""

import hashlib
import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse

# Only these ports may be fetched. SSRF frequently targets internal services on
# nonstandard ports (redis 6379, memcached 11211, metadata 80, etc.); allowing
# only the normal web ports removes that whole class.
_ALLOWED_PORTS = {80, 443, None}
# Redirects are followed manually so every hop is re-validated by the guard.
_MAX_REDIRECTS = 5

# Hostnames that resolve to instance-metadata endpoints on the major clouds.
_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata",
    "instance-data",
}
_METADATA_IPS = {"169.254.169.254", "100.100.100.200", "fd00:ec2::254"}


@dataclass(frozen=True)
class FetchResult:
    """A fetched (or cache-served) document and its provenance."""

    text: str
    url: str
    source_mode: str  # "LIVE" | "CACHED"
    fetched_at: float = field(default_factory=time.time)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
            object.__setattr__(self, "content_hash", digest)


class _Cache(Protocol):
    def get(self, url: str) -> FetchResult | None: ...


def _ip_is_blocked(ip_str: str) -> bool:
    """True if ``ip_str`` is loopback/private/link-local/reserved/metadata."""
    if ip_str in _METADATA_IPS:
        return True
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_url(url: str) -> bool:
    """Minimal SSRF guard: block private/loopback/link-local/metadata targets.

    Only ``http``/``https`` URLs to public hosts pass. The hostname is resolved
    and every resolved address is checked, so a public name pointing at a
    private IP is also rejected. This is a deliberately small replacement for
    LDR's ``ssrf_validator`` (not vendored, per the D0 decision).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    try:
        port = parsed.port
    except ValueError:
        return False  # malformed port
    if port not in _ALLOWED_PORTS:
        return False
    host = parsed.hostname
    if not host:
        return False
    if host.lower() in _METADATA_HOSTS:
        return False

    # Decide whether the host is a literal IP. Only literal IPs go through the
    # IP-block check directly; hostnames must be resolved first. (Calling
    # _ip_is_blocked on a hostname wrongly returns True, because it fails closed
    # on non-IP input — that bug rejected every normal hostname.)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        is_literal_ip = False
    else:
        is_literal_ip = True

    if is_literal_ip:
        return not _ip_is_blocked(host)

    # Hostname: resolve and reject only if ANY resolved address is blocked.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        if _ip_is_blocked(info[4][0]):
            return False
    return True


def _live_fetch(url: str, timeout: float) -> FetchResult:
    """Fetch ``url`` live via requests + BeautifulSoup; raise on any failure.

    Runs the SSRF guard first. Raises for HTTP 4xx/5xx (``raise_for_status``),
    ``TimeoutError`` on timeouts, and propagates other request exceptions so the
    caller's fallback path can engage.
    """
    import requests
    from bs4 import BeautifulSoup

    # Follow redirects MANUALLY so the SSRF guard re-validates every hop. With
    # requests' default allow_redirects=True, a public page could 3xx to an
    # internal target (169.254.169.254, 127.0.0.1:6379) and the guard — which
    # only saw the initial URL — would be bypassed. NOTE: a residual
    # DNS-rebinding TOCTOU remains (the guard resolves the name, then requests
    # resolves it again to connect); it is accepted for this demo because fetch
    # targets come from an allowlisted competitor/search set, not arbitrary input.
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not is_safe_url(current):
            raise ValueError(f"Blocked unsafe URL (SSRF guard): {current}")
        try:
            resp = requests.get(current, timeout=timeout, allow_redirects=False)
        except requests.Timeout as exc:
            raise TimeoutError(str(exc)) from exc

        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                break
            current = urljoin(current, location)  # re-validated at loop top
            continue
        break
    else:
        raise ValueError(f"Too many redirects (SSRF guard) starting at {url}")

    if resp.status_code >= 400:
        raise HTTPError(url, resp.status_code, resp.reason or "", hdrs=None, fp=None)

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return FetchResult(text=text, url=current, source_mode="LIVE")


def fetch_with_fallback(
    url: str,
    cache: _Cache,
    timeout: float = 8.0,
    mode: str = "live_first",
    *,
    firecrawl: Callable[[str], FetchResult | None] | None = None,
    min_chars: int = 0,
) -> FetchResult:
    """Fetch ``url`` with a read-only-cache fallback.

    Args:
        url: Target URL.
        cache: Read-only cache exposing ``get(url) -> FetchResult | None``.
        timeout: Per-fetch timeout in seconds.
        mode: ``"live_first"`` (default) or ``"cache_first"`` (D0 downgrade).
        firecrawl: Optional single-argument callable ``(url) -> FetchResult |
            None`` that renders JS-heavy pages via the Firecrawl API (already
            bound to key/base_url/timeout by the caller — keeps this module
            key-agnostic and offline-testable). When provided and the plain
            result has fewer than ``min_chars`` stripped characters, the
            Firecrawl result is used instead if it is richer.
        min_chars: Minimum stripped-character count for the plain result. If
            the plain result is below this threshold *and* ``firecrawl`` is
            provided, the Firecrawl fallback is attempted. Defaults to ``0``
            (disabled — preserves existing behaviour when not set).

    Returns:
        A :class:`FetchResult` tagged ``LIVE`` (live success) or ``CACHED``
        (served from the read-only cache).

    Raises:
        LookupError: When a live fetch fails *and* the cache has no entry.
    """
    if mode == "cache_first":
        cached = cache.get(url)
        if cached is not None:
            return _as_cached(cached, url)
        # Cache miss in cache_first still attempts live as a last resort.

    try:
        result = _live_fetch(url, timeout)
    except Exception as err:
        cached = cache.get(url)
        if cached is not None:
            return _as_cached(cached, url)
        raise LookupError(f"Live fetch failed and no cached copy for {url}") from err

    # Firecrawl upgrade path: only engage when the caller opted in (firecrawl
    # is not None) AND the plain result is thin (below min_chars).
    if firecrawl is not None and min_chars > 0:
        plain_len = len((result.text or "").strip())
        if plain_len < min_chars:
            fc_result = firecrawl(url)
            if fc_result is not None and len((fc_result.text or "").strip()) > plain_len:
                return fc_result

    return result


def _as_cached(result: FetchResult, url: str) -> FetchResult:
    """Return ``result`` normalized to ``source_mode='CACHED'``."""
    if result.source_mode == "CACHED":
        return result
    return FetchResult(
        text=result.text,
        url=result.url or url,
        source_mode="CACHED",
        fetched_at=result.fetched_at,
        content_hash=result.content_hash,
    )
