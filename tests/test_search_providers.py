"""Tests for Tavily + Brave search providers and parallel_search.

All tests are offline — HTTP is monkeypatched; no real network calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mingjing.collector.search import (
    _brave_search,
    _tavily_search,
    bind_provider,
    parallel_search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int, json_data: Any) -> MagicMock:
    """Build a minimal fake requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


# ---------------------------------------------------------------------------
# _tavily_search
# ---------------------------------------------------------------------------


class TestTavilySearch:
    def test_tavily_returns_previews(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_data = {
            "results": [
                {"url": "https://a.com", "title": "A Title", "content": "A snippet"},
                {"url": "https://b.com", "title": "B Title", "content": "B snippet"},
            ]
        }
        mock_post = MagicMock(return_value=_make_response(200, fake_data))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "post", mock_post)

        results = _tavily_search("test query", max_results=2, api_key="sk-test")

        assert len(results) == 2
        assert results[0] == {
            "url": "https://a.com",
            "title": "A Title",
            "snippet": "A snippet",
        }
        assert results[1] == {
            "url": "https://b.com",
            "title": "B Title",
            "snippet": "B snippet",
        }
        mock_post.assert_called_once()

    def test_tavily_http_error_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_post = MagicMock(return_value=_make_response(500, {}))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "post", mock_post)

        results = _tavily_search("query", max_results=5, api_key="sk-test")
        assert results == []

    def test_tavily_request_exception_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import requests as _requests_mod

        monkeypatch.setattr(
            _requests_mod, "post", MagicMock(side_effect=Exception("network error"))
        )

        results = _tavily_search("query", max_results=5, api_key="sk-test")
        assert results == []

    def test_tavily_empty_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty api_key must short-circuit without touching requests."""
        mock_post = MagicMock()

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "post", mock_post)

        results = _tavily_search("query", max_results=5, api_key="")
        assert results == []
        mock_post.assert_not_called()

    def test_tavily_missing_results_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response without 'results' key → []."""
        mock_post = MagicMock(return_value=_make_response(200, {"other": []}))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "post", mock_post)

        results = _tavily_search("query", max_results=5, api_key="sk-x")
        assert results == []

    def test_tavily_snippet_falls_back_to_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Result item without 'content' key → snippet is empty string."""
        fake_data = {
            "results": [
                {"url": "https://c.com", "title": "C"},
            ]
        }
        mock_post = MagicMock(return_value=_make_response(200, fake_data))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "post", mock_post)

        results = _tavily_search("q", max_results=1, api_key="sk-x")
        assert results == [{"url": "https://c.com", "title": "C", "snippet": ""}]


# ---------------------------------------------------------------------------
# _brave_search
# ---------------------------------------------------------------------------


class TestBraveSearch:
    def test_brave_returns_previews(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_data = {
            "web": {
                "results": [
                    {
                        "url": "https://x.com",
                        "title": "X Title",
                        "description": "X desc",
                    },
                    {
                        "url": "https://y.com",
                        "title": "Y Title",
                        "description": "Y desc",
                    },
                ]
            }
        }
        mock_get = MagicMock(return_value=_make_response(200, fake_data))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "get", mock_get)

        results = _brave_search("test query", max_results=2, api_key="brave-key")

        assert len(results) == 2
        assert results[0] == {
            "url": "https://x.com",
            "title": "X Title",
            "snippet": "X desc",
        }
        assert results[1] == {
            "url": "https://y.com",
            "title": "Y Title",
            "snippet": "Y desc",
        }
        mock_get.assert_called_once()

    def test_brave_http_error_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_get = MagicMock(return_value=_make_response(403, {}))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "get", mock_get)

        results = _brave_search("query", max_results=5, api_key="brave-key")
        assert results == []

    def test_brave_request_exception_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import requests as _requests_mod

        monkeypatch.setattr(
            _requests_mod, "get", MagicMock(side_effect=Exception("timeout"))
        )

        results = _brave_search("query", max_results=5, api_key="brave-key")
        assert results == []

    def test_brave_empty_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty api_key must short-circuit without touching requests."""
        mock_get = MagicMock()

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "get", mock_get)

        results = _brave_search("query", max_results=5, api_key="")
        assert results == []
        mock_get.assert_not_called()

    def test_brave_missing_web_key_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response without 'web' key → []."""
        mock_get = MagicMock(return_value=_make_response(200, {}))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "get", mock_get)

        results = _brave_search("query", max_results=5, api_key="k")
        assert results == []

    def test_brave_snippet_falls_back_to_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Result item without 'description' key → snippet is empty string."""
        fake_data = {
            "web": {
                "results": [
                    {"url": "https://z.com", "title": "Z"},
                ]
            }
        }
        mock_get = MagicMock(return_value=_make_response(200, fake_data))

        import requests as _requests_mod

        monkeypatch.setattr(_requests_mod, "get", mock_get)

        results = _brave_search("q", max_results=1, api_key="k")
        assert results == [{"url": "https://z.com", "title": "Z", "snippet": ""}]


# ---------------------------------------------------------------------------
# parallel_search
# ---------------------------------------------------------------------------


class TestParallelSearch:
    def _make_engine(self, name: str):
        """Return a callable that encodes the query into the URL so we can assert
        every (query × engine) pair was actually executed."""

        def engine(query: str) -> list[dict[str, Any]]:
            return [{"url": f"https://{name}.com/{query}", "title": name, "snippet": "s"}]

        engine.__name__ = name
        return engine

    def test_parallel_search_merges_and_tags(self) -> None:
        """Two engines × two queries → 4 calls, every (query × engine) pair present."""
        engine_a = self._make_engine("eng_a")
        engine_b = self._make_engine("eng_b")

        results = parallel_search(
            queries=["q1", "q2"],
            engines={"eng_a": engine_a, "eng_b": engine_b},
            workers=4,
        )

        # 2 queries × 2 engines = 4 result dicts total
        assert len(results) == 4

        engines_seen = {r["engine"] for r in results}
        assert engines_seen == {"eng_a", "eng_b"}

        urls = {r["url"] for r in results}
        # Assert every (query × engine) pair was actually dispatched
        assert urls == {
            "https://eng_a.com/q1",
            "https://eng_a.com/q2",
            "https://eng_b.com/q1",
            "https://eng_b.com/q2",
        }

    def test_parallel_search_one_engine_raises_does_not_kill_batch(self) -> None:
        """A raising engine callable must not propagate; other engine's results returned."""

        def bad_engine(query: str) -> list[dict[str, Any]]:
            raise RuntimeError("provider down")

        good_engine = self._make_engine("good")

        results = parallel_search(
            queries=["q1"],
            engines={"bad": bad_engine, "good": good_engine},
            workers=2,
        )

        # bad engine → 0 results; good engine → 1 result
        assert len(results) == 1
        assert results[0]["engine"] == "good"
        assert results[0]["url"] == "https://good.com/q1"

    def test_parallel_search_empty_queries_returns_empty(self) -> None:
        engine_a = self._make_engine("eng_a")
        results = parallel_search(queries=[], engines={"eng_a": engine_a})
        assert results == []

    def test_parallel_search_empty_engines_returns_empty(self) -> None:
        results = parallel_search(queries=["q1"], engines={})
        assert results == []

    def test_parallel_search_engine_tag_does_not_overwrite_existing_fields(self) -> None:
        """Engine tag is added; existing url/title/snippet are untouched."""
        engine = self._make_engine("tagger")

        results = parallel_search(queries=["q"], engines={"tagger": engine})
        assert len(results) == 1
        assert results[0]["url"] == "https://tagger.com/q"
        assert results[0]["title"] == "tagger"
        assert results[0]["snippet"] == "s"
        assert results[0]["engine"] == "tagger"


# ---------------------------------------------------------------------------
# bind_provider
# ---------------------------------------------------------------------------


class TestBindProvider:
    """bind_provider returns a bound callable or None per contract."""

    def test_known_engines_return_callable(self) -> None:
        """tavily, brave, duckduckgo all return a callable."""
        assert callable(bind_provider("tavily", top_k=5, tavily_key="k"))
        assert callable(bind_provider("brave", top_k=5, brave_key="k"))
        assert callable(bind_provider("duckduckgo", top_k=5))

    def test_searxng_with_url_returns_callable(self) -> None:
        """searxng with a non-empty url returns a callable."""
        fn = bind_provider("searxng", top_k=5, searxng_url="http://localhost:8080")
        assert callable(fn)

    def test_searxng_with_empty_url_returns_none(self) -> None:
        """searxng with empty url → None (engine unavailable)."""
        assert bind_provider("searxng", top_k=5, searxng_url="") is None
        assert bind_provider("searxng", top_k=5, searxng_url="   ") is None

    def test_unknown_engine_returns_none(self) -> None:
        """Unknown engine name → None."""
        assert bind_provider("bing", top_k=5) is None
        assert bind_provider("", top_k=5) is None


def test_duckduckgo_passes_finite_timeout(monkeypatch):
    """Regression: _duckduckgo_search must bound DDGS with a timeout, else a hung
    DDG backend hangs the whole run (DDG is in both depth tiers, and parallel_search
    blocks on executor join). The other 3 providers already set timeout=8."""
    captured: dict = {}

    class _FakeDDGS:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def text(self, query, max_results):
            return []

    import duckduckgo_search

    monkeypatch.setattr(duckduckgo_search, "DDGS", _FakeDDGS)
    from mingjing.collector.search import _duckduckgo_search

    _duckduckgo_search("notion pricing", 5)
    assert captured.get("timeout") == 8, f"DDGS must receive timeout=8, got {captured!r}"
