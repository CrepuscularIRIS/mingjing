"""Task 8 unit tests: robots.txt gate, tested fully offline.

A fake ``fetch_robots(domain) -> str`` callable injects a robots body so the
gate can be exercised without network access.
"""

from mingjing.collector import robots
from mingjing.collector.robots import clear_cache, is_allowed

_ROBOTS = """
User-agent: *
Disallow: /private
Allow: /public
"""


def _fake_fetch(_domain):
    return _ROBOTS


def test_disallowed_path_blocked():
    assert is_allowed("https://example.com/private/page", _fake_fetch) is False


def test_allowed_path_permitted():
    assert is_allowed("https://example.com/public/page", _fake_fetch) is True


def test_unlisted_path_permitted():
    assert is_allowed("https://example.com/", _fake_fetch) is True


def test_domain_keyed_cache_fetches_once():
    calls = {"n": 0}

    def counting_fetch(_domain):
        calls["n"] += 1
        return _ROBOTS

    is_allowed("https://cache.example.com/a", counting_fetch)
    is_allowed("https://cache.example.com/b", counting_fetch)
    assert calls["n"] == 1


def test_fetch_failure_fails_open():
    # If robots cannot be fetched, default to allowing (record handled by caller).
    clear_cache()
    def boom(_domain):
        raise RuntimeError("no robots")

    assert is_allowed("https://err.example.com/x", boom) is True


def test_genuine_empty_robots_allows():
    # A genuine 404/empty robots (no exception, empty body) means "no rules" -> allow.
    clear_cache()
    assert is_allowed("https://empty.example.com/anything", lambda _d: "") is True


def test_transient_failure_not_cached_permanently(monkeypatch):
    # A transient failure must NOT permanently whitelist the domain. Once the
    # short failure-TTL elapses, the next request re-fetches and can pick up a
    # restrictive policy that now blocks a previously fail-open URL.
    clear_cache()
    monkeypatch.setattr(robots, "_FAILURE_TTL_SECONDS", 0.0)

    state = {"fail": True}

    def flaky(_domain):
        if state["fail"]:
            raise RuntimeError("transient")
        return "User-agent: *\nDisallow: /secret\n"

    # First call: fetch fails -> fail open (allowed).
    assert is_allowed("https://flaky.example.com/secret/p", flaky) is True

    # Failure recovers; with TTL=0 the next call re-attempts and honors robots.
    state["fail"] = False
    assert is_allowed("https://flaky.example.com/secret/p", flaky) is False
    assert is_allowed("https://flaky.example.com/public/p", flaky) is True


def test_failure_within_ttl_not_refetched(monkeypatch):
    # Within the TTL window, a failed fetch is not re-attempted every call
    # (negative cache), but still fails open.
    clear_cache()
    monkeypatch.setattr(robots, "_FAILURE_TTL_SECONDS", 1000.0)
    calls = {"n": 0}

    def boom(_domain):
        calls["n"] += 1
        raise RuntimeError("down")

    assert is_allowed("https://ttl.example.com/a", boom) is True
    assert is_allowed("https://ttl.example.com/b", boom) is True
    assert calls["n"] == 1
