"""Source-independence counting (PURE).

Two sources on the same registrable domain are *not* independent (a vendor's
blog and its pricing page are one voice). ``count_independent`` dedupes a list
of sources by registrable domain.

Registrable-domain extraction uses a small built-in set of common multi-label
public suffixes (e.g. ``co.uk``) so we avoid a heavyweight ``publicsuffix``
dependency for the demo slice. Unknown TLDs fall back to the last two labels.
"""

from collections.abc import Iterable, Mapping
from urllib.parse import urlparse

# Common second-level public suffixes where the registrable domain is the
# label *before* this suffix (so example.co.uk -> example.co.uk, not co.uk).
_MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "co.jp",
    "co.kr",
    "co.in",
    "com.au",
    "com.br",
    "com.cn",
    "com.hk",
    "com.sg",
    "com.tw",
    "co.nz",
    "co.za",
}


def _host_of(source: object) -> str:
    """Extract a lowercased hostname from a URL string or a ``{'url': ...}`` dict."""
    if isinstance(source, Mapping):
        url = str(source.get("url", ""))
    else:
        url = str(source)
    netloc = urlparse(url).netloc or url
    host = netloc.split("@")[-1].split(":")[0]  # drop credentials/port
    return host.lower().strip(".")


def registrable_domain(source: object) -> str:
    """Return the registrable domain (eTLD+1) for a URL or source mapping.

    Strips subdomains: ``blog.example.com`` -> ``example.com``;
    ``example.co.uk`` is preserved via the known multi-label suffix set.
    """
    host = _host_of(source)
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) <= 2:
        return host

    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def count_independent(sources: Iterable[object]) -> int:
    """Count distinct registrable domains across ``sources``.

    Args:
        sources: An iterable of URL strings or ``{'url': ...}`` mappings.

    Returns:
        The number of independent sources (distinct registrable domains);
        empty/blank entries are ignored.
    """
    domains = {registrable_domain(s) for s in sources}
    domains.discard("")
    return len(domains)
