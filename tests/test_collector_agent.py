"""Unit tests for agents/collector.py (C1 regression guard).

Key invariant: ``collect()`` must call ``_search_fn`` (the direct function
import), not ``search_mod.search`` (the old broken attribute access).

Test: ``test_collect_calls_search_then_robots_then_fetch``
  - Monkeypatches ``_search_fn`` on the agent module namespace (the canonical
    call-site after the C1 fix); would have raised ``AttributeError`` against
    the old ``search_mod.search(...)`` code path.
  - Monkeypatches ``robots.is_allowed`` -> True (allow the URL).
  - Monkeypatches ``fetch_with_fallback`` -> returns a fake FetchResult.
  - Asserts ``collect()`` returns one source dict with expected fields.

No network, no live LLM.
"""

import time

import pytest

import mingjing.agents.collector as collector_agent
from mingjing.collector import robots as robots_mod
from mingjing.collector.fetch import FetchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyCache:
    """Minimal read-only cache that always misses."""

    def get(self, url: str) -> FetchResult | None:
        return None


FAKE_URL = "https://example.com/article"
FAKE_TITLE = "Example Article"
FAKE_SNIPPET = "An interesting snippet."
FAKE_HIT = {"url": FAKE_URL, "title": FAKE_TITLE, "snippet": FAKE_SNIPPET}

FAKE_TEXT = "Full article text here."
FAKE_FETCH_RESULT = FetchResult(
    text=FAKE_TEXT,
    url=FAKE_URL,
    source_mode="LIVE",
    fetched_at=time.time(),
)


# ---------------------------------------------------------------------------
# C1 regression: search callable must be _search_fn, not search_mod.search
# ---------------------------------------------------------------------------


def test_collect_calls_search_then_robots_then_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """collect() must invoke _search_fn directly; robots gate then fetch.

    This test FAILS against the old ``search_mod.search(...)`` call-site
    (AttributeError: 'function' object has no attribute 'search') and PASSES
    after the C1 fix (``_search_fn(query, ...)``).
    """
    search_calls: list[tuple] = []
    robots_calls: list[str] = []
    fetch_calls: list[str] = []

    # Patch _search_fn (direct function — the fixed call-site).
    def fake_search_fn(query: str, max_results: int = 5) -> list[dict]:
        search_calls.append((query, max_results))
        return [FAKE_HIT]

    monkeypatch.setattr(collector_agent, "_search_fn", fake_search_fn)

    # Patch robots.is_allowed -> True (allow fetching).
    def fake_is_allowed(url: str, fetch_robots_fn) -> bool:  # type: ignore[no-untyped-def]
        robots_calls.append(url)
        return True

    monkeypatch.setattr(robots_mod, "is_allowed", fake_is_allowed)

    # Patch fetch_with_fallback -> returns the fake FetchResult.
    def fake_fetch(url: str, **kwargs) -> FetchResult:  # type: ignore[no-untyped-def]
        fetch_calls.append(url)
        return FAKE_FETCH_RESULT

    monkeypatch.setattr(collector_agent, "fetch_with_fallback", fake_fetch)

    # Run.
    result = collector_agent.collect(
        "competitive pricing",
        _DummyCache(),
        max_results=3,
        source_cap=5,
        fetch_robots=lambda domain: "",  # inject no-op robots fetcher
    )

    # --- Assertions ---

    # 1. Search was called once with the right query.
    assert len(search_calls) == 1, f"Expected 1 search call, got {search_calls}"
    assert search_calls[0][0] == "competitive pricing"
    assert search_calls[0][1] == 3

    # 2. Robots gate was checked for the URL before fetch.
    assert FAKE_URL in robots_calls, (
        f"robots.is_allowed was not called for {FAKE_URL!r}; calls={robots_calls}"
    )

    # 3. Fetch was called for the allowed URL.
    assert FAKE_URL in fetch_calls, (
        f"fetch_with_fallback was not called for {FAKE_URL!r}; calls={fetch_calls}"
    )

    # 4. collect() returns one source dict with expected fields.
    assert len(result) == 1, f"Expected 1 result, got {len(result)}"
    src = result[0]
    assert src["url"] == FAKE_URL
    assert src["title"] == FAKE_TITLE
    assert src["snippet"] == FAKE_SNIPPET
    assert src["fetched"] is True
    assert src["text"] == FAKE_TEXT
    assert src["source_mode"] == "LIVE"
    assert "source_id" in src
    assert "content_hash" in src
    assert "fetched_at" in src
