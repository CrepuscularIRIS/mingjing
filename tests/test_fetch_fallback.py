"""Task 7 unit tests: timeout/4xx -> read-only-cache fallback wrapper.

All tests monkeypatch ``_live_fetch`` so no real network is touched and no API
key is required. The cache is a tiny in-memory fake.
"""

from urllib.error import HTTPError

import pytest

from mingjing.collector.fetch import FetchResult, fetch_with_fallback


class _FakeCache:
    """In-memory read-only cache keyed by URL, returning a FetchResult."""

    def __init__(self, store):
        self._store = store

    def get(self, url):
        return self._store.get(url)


@pytest.fixture
def fake_cache():
    return _FakeCache(
        {
            "http://x": FetchResult(
                text="cached body",
                url="http://x",
                source_mode="CACHED",
            )
        }
    )


def _raise(exc):
    def _inner(url, timeout):
        raise exc

    return _inner


def test_fallback_on_timeout(monkeypatch, fake_cache):
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch", _raise(TimeoutError())
    )
    res = fetch_with_fallback("http://x", cache=fake_cache)
    assert res.source_mode == "CACHED"


def test_fallback_on_4xx(monkeypatch, fake_cache):
    err = HTTPError("http://x", 404, "Not Found", hdrs=None, fp=None)
    monkeypatch.setattr("mingjing.collector.fetch._live_fetch", _raise(err))
    assert fetch_with_fallback("http://x", cache=fake_cache).source_mode == "CACHED"


def test_live_success_sets_live(monkeypatch, fake_cache):
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda u, t: FetchResult(text="ok", url="http://x", source_mode="LIVE"),
    )
    assert fetch_with_fallback("http://x", cache=fake_cache).source_mode == "LIVE"


def test_cache_first_reads_cache_before_live(monkeypatch, fake_cache):
    # In cache_first mode the cache is consulted first; _live_fetch must not run.
    def _boom(url, timeout):
        raise AssertionError("live fetch should not be called in cache_first")

    monkeypatch.setattr("mingjing.collector.fetch._live_fetch", _boom)
    res = fetch_with_fallback("http://x", cache=fake_cache, mode="cache_first")
    assert res.source_mode == "CACHED"
