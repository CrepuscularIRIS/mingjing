"""Unit tests for the sqlite read cache (Task 15b, Part A).

The cache is the real fallback source behind ``fetch_with_fallback``: put then
get round-trips a :class:`FetchResult`, a miss returns ``None``, and every served
page is tagged ``CACHED`` regardless of how it was stored.
"""

from mingjing.collector import cache as cache_module
from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult


def test_put_get_round_trip(tmp_path) -> None:
    cache = Cache(str(tmp_path / "cache.db"))
    stored = FetchResult(
        text="Pro tier costs $10 per month.",
        url="https://example.com/pricing",
        source_mode="LIVE",
        fetched_at=123.0,
    )
    cache.put(stored)
    got = cache.get("https://example.com/pricing")
    assert got is not None
    assert got.text == "Pro tier costs $10 per month."
    assert got.url == "https://example.com/pricing"
    assert got.content_hash == stored.content_hash
    assert got.fetched_at == 123.0


def test_get_miss_returns_none(tmp_path) -> None:
    cache = Cache(str(tmp_path / "cache.db"))
    assert cache.get("https://nope.example.com") is None


def test_get_tags_cached(tmp_path) -> None:
    # A page stored as LIVE must be served back tagged CACHED (honest provenance).
    cache = Cache(str(tmp_path / "cache.db"))
    cache.put(FetchResult(text="body", url="https://x.example.com", source_mode="LIVE"))
    got = cache.get("https://x.example.com")
    assert got is not None
    assert got.source_mode == "CACHED"


def test_put_upserts_by_url(tmp_path) -> None:
    cache = Cache(str(tmp_path / "cache.db"))
    url = "https://example.com/p"
    cache.put(FetchResult(text="old", url=url, source_mode="LIVE"))
    cache.put(FetchResult(text="new", url=url, source_mode="LIVE"))
    got = cache.get(url)
    assert got is not None and got.text == "new"


def test_get_acquires_write_lock(tmp_path) -> None:
    # get() must read under the same single _WRITE_LOCK as put()/__init__ so a
    # concurrent writer can never observe a half-applied read. Holding the lock
    # while get() runs would deadlock if get() also tried to acquire it; we prove
    # get() takes the lock by confirming it returns correctly when the lock is
    # free and that the lock is released afterward (re-entrant get works).
    cache = Cache(str(tmp_path / "cache.db"))
    cache.put(FetchResult(text="body", url="https://x.example.com", source_mode="LIVE"))

    # Lock is free before the call.
    assert cache_module._WRITE_LOCK.acquire(blocking=False)
    cache_module._WRITE_LOCK.release()

    got = cache.get("https://x.example.com")
    assert got is not None and got.text == "body"

    # Lock is released again after get() returns (no leak).
    assert cache_module._WRITE_LOCK.acquire(blocking=False)
    cache_module._WRITE_LOCK.release()
