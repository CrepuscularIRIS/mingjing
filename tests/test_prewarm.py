"""Offline tests for :func:`mingjing.prewarm.prewarm_all`.

All tests use deterministic fake ``fetch_fn`` callables and a ``tmp_path``
:class:`~mingjing.collector.cache.Cache` — no network, no live LLM.

Three assertions (per the Task 16 spec):

(a) Every (competitor × field) pair is warmed into the cache and retrievable
    via ``cache.get``.
(b) A ``fetch_fn`` that raises for one URL lands its error in ``errors``
    without aborting the rest.
(c) Max in-flight never exceeds ``max_workers`` (verified via a shared
    increment/decrement counter — deterministic, no long sleeps).
"""

import threading
import time
from typing import Any

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.prewarm import prewarm_all

COMPETITORS = ["Acme", "Beta", "Gamma"]
FIELDS = ["pricing_model", "feature_tree", "user_sentiment"]

# ---------------------------------------------------------------------------
# Fake fetch factories
# ---------------------------------------------------------------------------


def _make_simple_fetch_fn() -> tuple[Any, list[str]]:
    """Return a (fake_fetch_fn, call_log) pair.

    Every call records the URL and returns a deterministic FetchResult tagged
    LIVE.  No exceptions raised.
    """
    call_log: list[str] = []

    def fake_fetch(url: str) -> FetchResult:
        call_log.append(url)
        return FetchResult(
            text=f"content for {url}",
            url=url,
            source_mode="LIVE",
            fetched_at=1.0,
        )

    return fake_fetch, call_log


def _make_failing_fetch_fn(bad_url: str) -> tuple[Any, list[str]]:
    """Return a (fake_fetch_fn, call_log) that raises for exactly ``bad_url``."""
    call_log: list[str] = []

    def fake_fetch(url: str) -> FetchResult:
        call_log.append(url)
        if url == bad_url:
            raise RuntimeError(f"Simulated fetch failure for {url}")
        return FetchResult(
            text=f"content for {url}",
            url=url,
            source_mode="LIVE",
            fetched_at=1.0,
        )

    return fake_fetch, call_log


def _make_concurrency_tracking_fetch_fn(
    max_workers: int,
) -> tuple[Any, list[int]]:
    """Return a (fake_fetch_fn, peak_log) that measures actual peak concurrency.

    ``peak_log`` is a single-element list so callers can read the peak after the
    executor has joined.  The fetch_fn increments a shared counter on entry,
    records the peak, then decrements on exit.  A tiny ``time.sleep`` creates
    enough window for concurrent workers to overlap — kept very short (1 ms) to
    avoid slowing the test suite while still being deterministic enough to
    trigger realistic overlap on a multi-core machine.
    """
    lock = threading.Lock()
    in_flight = [0]
    peak = [0]

    def fake_fetch(url: str) -> FetchResult:
        with lock:
            in_flight[0] += 1
            if in_flight[0] > peak[0]:
                peak[0] = in_flight[0]
        # Tiny pause so threads can pile up to max_workers.
        time.sleep(0.001)
        with lock:
            in_flight[0] -= 1
        return FetchResult(
            text=f"content for {url}",
            url=url,
            source_mode="LIVE",
            fetched_at=1.0,
        )

    return fake_fetch, peak


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_prewarm_all_warms_every_pair(tmp_path: Any) -> None:
    """(a) Every (competitor × field) pair is warmed and retrievable via cache.get."""
    fetch_fn, call_log = _make_simple_fetch_fn()

    with Cache(str(tmp_path / "cache.db")) as cache:
        # Provide a deterministic URL resolver so we know what to look up.
        def url_for(competitor: str, field: str) -> str:
            return f"https://{competitor.lower()}.example.com/{field}"

        result = prewarm_all(
            COMPETITORS,
            FIELDS,
            cache=cache,
            fetch_fn=fetch_fn,
            max_workers=4,
            url_for=url_for,
        )

        # Check return structure.
        assert "warmed" in result
        assert "errors" in result
        assert result["errors"] == [], f"unexpected errors: {result['errors']}"

        # Every (competitor × field) combination must appear in warmed.
        warmed_keys = {(comp, fld) for comp, fld, _url, _mode in result["warmed"]}
        expected = {(comp, fld) for comp in COMPETITORS for fld in FIELDS}
        assert warmed_keys == expected, (
            f"missing pairs: {expected - warmed_keys}"
        )

        # Every URL is retrievable from the cache.
        for comp in COMPETITORS:
            for fld in FIELDS:
                url = url_for(comp, fld)
                cached = cache.get(url)
                assert cached is not None, f"cache miss for {url}"
                assert cached.url == url
                # Cache always serves with CACHED tag regardless of original mode.
                assert cached.source_mode == "CACHED"
                assert f"content for {url}" in cached.text


def test_prewarm_partial_failure_does_not_abort(tmp_path: Any) -> None:
    """(b) A fetch_fn that raises for one URL lands in errors; rest still warm."""

    def url_for(competitor: str, field: str) -> str:
        return f"https://{competitor.lower()}.example.com/{field}"

    # Pick a URL that will fail.
    bad_competitor, bad_field = COMPETITORS[0], FIELDS[0]
    bad_url = url_for(bad_competitor, bad_field)

    fetch_fn, call_log = _make_failing_fetch_fn(bad_url)

    with Cache(str(tmp_path / "cache.db")) as cache:
        result = prewarm_all(
            COMPETITORS,
            FIELDS,
            cache=cache,
            fetch_fn=fetch_fn,
            max_workers=4,
            url_for=url_for,
        )

    total_pairs = len(COMPETITORS) * len(FIELDS)

    # Exactly one error.
    assert len(result["errors"]) == 1, f"expected 1 error, got {result['errors']}"
    err = result["errors"][0]
    assert err["url"] == bad_url
    assert "Simulated fetch failure" in err["error"]

    # All other pairs warmed successfully.
    assert len(result["warmed"]) == total_pairs - 1

    # The bad URL is NOT in warmed.
    warmed_urls = {url for _comp, _fld, url, _mode in result["warmed"]}
    assert bad_url not in warmed_urls


def test_prewarm_max_concurrency_never_exceeded(tmp_path: Any) -> None:
    """(c) Peak in-flight threads never exceeds max_workers."""
    max_workers = 3
    # Use more work items than max_workers to ensure the pool is saturated.
    many_competitors = [f"C{i}" for i in range(6)]
    many_fields = ["pricing_model", "feature_tree", "user_sentiment", "swot", "user_persona"]

    fetch_fn, peak_log = _make_concurrency_tracking_fetch_fn(max_workers)

    def url_for(competitor: str, field: str) -> str:
        return f"https://{competitor.lower()}.example.com/{field}"

    with Cache(str(tmp_path / "cache.db")) as cache:
        result = prewarm_all(
            many_competitors,
            many_fields,
            cache=cache,
            fetch_fn=fetch_fn,
            max_workers=max_workers,
            url_for=url_for,
        )

    assert result["errors"] == [], f"unexpected errors: {result['errors']}"

    n_tasks = len(many_competitors) * len(many_fields)

    # Upper bound: pool never exceeds max_workers.
    assert peak_log[0] <= max_workers, (
        f"observed peak {peak_log[0]} exceeded max_workers={max_workers}"
    )
    internal_peak = result.get("_peak_in_flight", 0)
    assert internal_peak <= max_workers, (
        f"internal peak {internal_peak} exceeded max_workers={max_workers}"
    )

    # Lower bound: pool was actually saturated (proves real concurrency, not
    # a trivially-serial pass).
    min_expected = min(max_workers, n_tasks)
    assert peak_log[0] >= min_expected, (
        f"observed peak {peak_log[0]} < min_expected={min_expected}; "
        "pool was never saturated — test may be passing trivially serially"
    )


def test_prewarm_empty_inputs_returns_empty(tmp_path: Any) -> None:
    """Calling with empty competitors or fields produces no work and no errors."""
    fetch_fn, call_log = _make_simple_fetch_fn()
    with Cache(str(tmp_path / "cache.db")) as cache:
        result = prewarm_all([], FIELDS, cache=cache, fetch_fn=fetch_fn)
        assert result["warmed"] == []
        assert result["errors"] == []
        assert call_log == []

        result2 = prewarm_all(COMPETITORS, [], cache=cache, fetch_fn=fetch_fn)
        assert result2["warmed"] == []
        assert result2["errors"] == []


def test_prewarm_min_interval_gate(tmp_path: Any) -> None:
    """(I2) min_interval_s spaces out request STARTS and does not drop any URL.

    Assertions:
    (a) All URLs are warmed (no errors).
    (b) Total elapsed >= (n_urls - 1) * min_interval_s (start-spacing lower bound).
    (c) No errors.
    """
    min_interval_s = 0.02  # small enough to keep the test fast

    # Use >max_workers URLs to ensure the gate sees multiple waves.
    gate_competitors = [f"G{i}" for i in range(4)]
    gate_fields = ["pricing_model"]
    n_urls = len(gate_competitors) * len(gate_fields)

    fetch_fn, call_log = _make_simple_fetch_fn()

    def url_for(competitor: str, field: str) -> str:
        return f"https://{competitor.lower()}.example.com/{field}"

    t_start = time.monotonic()
    with Cache(str(tmp_path / "cache.db")) as cache:
        result = prewarm_all(
            gate_competitors,
            gate_fields,
            cache=cache,
            fetch_fn=fetch_fn,
            max_workers=4,
            min_interval_s=min_interval_s,
            url_for=url_for,
        )
    elapsed = time.monotonic() - t_start

    # (a) & (c) All URLs warmed, no errors.
    assert result["errors"] == [], f"unexpected errors: {result['errors']}"
    assert len(result["warmed"]) == n_urls, (
        f"expected {n_urls} warmed, got {len(result['warmed'])}"
    )

    # (b) Start-spacing lower bound: n_urls starts, each separated by at least
    # min_interval_s, so total >= (n_urls - 1) * min_interval_s.
    lower_bound = (n_urls - 1) * min_interval_s
    assert elapsed >= lower_bound, (
        f"elapsed {elapsed:.4f}s < lower bound {lower_bound:.4f}s; "
        "gate appears not to be spacing starts"
    )


def test_prewarm_source_mode_recorded(tmp_path: Any) -> None:
    """source_mode from the FetchResult is exposed in the warmed list."""
    def url_for(comp: str, fld: str) -> str:
        return f"https://{comp.lower()}.example.com/{fld}"

    def fetch_fn(url: str) -> FetchResult:
        return FetchResult(text="text", url=url, source_mode="LIVE", fetched_at=1.0)

    with Cache(str(tmp_path / "cache.db")) as cache:
        result = prewarm_all(
            ["Acme"],
            ["pricing_model"],
            cache=cache,
            fetch_fn=fetch_fn,
            url_for=url_for,
        )

    assert len(result["warmed"]) == 1
    _comp, _fld, _url, mode = result["warmed"][0]
    assert mode == "LIVE"
