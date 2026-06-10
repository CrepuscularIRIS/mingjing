"""Unit tests for the pluggable search provider chain (no network)."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import the module object directly (not via the package __init__ which re-exports
# the ``search`` *function* under the same name, causing ``import ... as`` to
# bind to the function rather than the module).
_search_module = importlib.import_module("mingjing.collector.search")

from mingjing.collector.search import (  # noqa: E402
    _searxng_search,
    search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DDG_HIT: dict[str, Any] = {"url": "d", "title": "dt", "snippet": "ds"}
SX_HIT: dict[str, Any] = {"url": "u1", "title": "t1", "snippet": "c1"}


def _fake_response(status: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    return resp


# ---------------------------------------------------------------------------
# _searxng_search
# ---------------------------------------------------------------------------


def test_searxng_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """SearXNG provider maps result fields correctly from the JSON response."""
    fake_data = {
        "results": [
            {"url": "u1", "title": "t1", "content": "c1"},
            {"url": "u2", "title": "t2", "content": "c2"},
        ]
    }
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response(200, fake_data))

    results = _searxng_search("q", 5, "http://sx:8080")

    assert results == [
        {"url": "u1", "title": "t1", "snippet": "c1"},
        {"url": "u2", "title": "t2", "snippet": "c2"},
    ]


def test_searxng_http_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """SearXNG provider returns [] on HTTP error status, does not raise."""
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response(502, {}))

    results = _searxng_search("q", 5, "http://sx:8080")

    assert results == []


def test_searxng_exception_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """SearXNG provider returns [] when requests.get raises, does not raise."""

    def _raise(*a: Any, **kw: Any) -> None:
        raise ConnectionError("unreachable")

    monkeypatch.setattr("requests.get", _raise)

    results = _searxng_search("q", 5, "http://sx:8080")

    assert results == []


def test_searxng_allows_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SearXNG endpoint is TRUSTED operator config and is *meant* to be a
    loopback/internal host — a localhost URL must proceed to the request (it is
    NOT subject to the public-only SSRF guard that protects untrusted fetches).
    """
    fake_data = {"results": [{"url": "u1", "title": "t1", "content": "c1"}]}
    monkeypatch.setattr("requests.get", lambda *a, **kw: _fake_response(200, fake_data))

    results = _searxng_search("q", 5, "http://127.0.0.1:8080")

    assert results == [{"url": "u1", "title": "t1", "snippet": "c1"}]


def test_searxng_rejects_invalid_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-http(s) / malformed instance URL returns [] without calling requests.get."""

    def _get_must_not_be_called(*a: Any, **kw: Any) -> Any:
        raise AssertionError("requests.get must not be called for an invalid scheme")

    monkeypatch.setattr("requests.get", _get_must_not_be_called)

    assert _searxng_search("q", 5, "file:///etc/passwd") == []
    assert _searxng_search("q", 5, "not-a-url") == []


# ---------------------------------------------------------------------------
# Provider chain — fallback behaviour
# ---------------------------------------------------------------------------


def test_chain_falls_back_to_ddg_when_searxng_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When searxng returns [], chain continues and returns the DDG hit."""
    monkeypatch.setattr(_search_module, "_searxng_search", lambda *a, **kw: [])
    monkeypatch.setattr(_search_module, "_duckduckgo_search", lambda *a, **kw: [DDG_HIT])

    result = search("q", provider="searxng,duckduckgo")

    assert result == [DDG_HIT]


def test_auto_chain_uses_ddg_only_without_searxng_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto + no MINGJING_SEARXNG_URL → only DDG called; SearXNG never invoked."""
    monkeypatch.delenv("MINGJING_SEARXNG_URL", raising=False)
    monkeypatch.delenv("MINGJING_SEARCH_PROVIDER", raising=False)

    called: list[str] = []

    def _sx_should_not_be_called(*a: Any, **kw: Any) -> list:
        called.append("searxng")
        raise AssertionError("_searxng_search must not be called in DDG-only mode")

    monkeypatch.setattr(_search_module, "_searxng_search", _sx_should_not_be_called)
    monkeypatch.setattr(_search_module, "_duckduckgo_search", lambda *a, **kw: [DDG_HIT])

    result = search("q")

    assert result == [DDG_HIT]
    assert "searxng" not in called


def test_auto_chain_prefers_searxng_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto + MINGJING_SEARXNG_URL set → SearXNG tried first; DDG never called."""
    monkeypatch.setenv("MINGJING_SEARXNG_URL", "http://sx:8080")
    monkeypatch.delenv("MINGJING_SEARCH_PROVIDER", raising=False)

    def _ddg_should_not_be_called(*a: Any, **kw: Any) -> list:
        raise AssertionError("_duckduckgo_search must not be called when SearXNG hits")

    monkeypatch.setattr(_search_module, "_searxng_search", lambda *a, **kw: [SX_HIT])
    monkeypatch.setattr(_search_module, "_duckduckgo_search", _ddg_should_not_be_called)

    result = search("q")

    assert result == [SX_HIT]


# ---------------------------------------------------------------------------
# Retry-on-empty tests
# ---------------------------------------------------------------------------


def test_retry_recovers_after_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """_searxng_search returns [] on 1st call then [SX_HIT] on 2nd; search returns [SX_HIT]."""
    calls: list[int] = []

    def _sx_stub(*a: Any, **kw: Any) -> list:
        calls.append(1)
        if len(calls) == 1:
            return []
        return [SX_HIT]

    monkeypatch.setattr(_search_module, "_searxng_search", _sx_stub)

    result = search("q", provider="searxng", sleep_fn=lambda _: None)

    assert result == [SX_HIT]
    assert len(calls) == 2


def test_retry_exhausts_then_falls_to_next_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """searxng always empty (3 attempts); chain falls to duckduckgo returning DDG_HIT."""
    sx_calls: list[int] = []

    def _sx_always_empty(*a: Any, **kw: Any) -> list:
        sx_calls.append(1)
        return []

    monkeypatch.setattr(_search_module, "_searxng_search", _sx_always_empty)
    monkeypatch.setattr(_search_module, "_duckduckgo_search", lambda *a, **kw: [DDG_HIT])

    result = search(
        "q", provider="searxng,duckduckgo", retries=2, sleep_fn=lambda _: None
    )

    assert result == [DDG_HIT]
    assert len(sx_calls) == 3  # 1 + retries=2


def test_retries_zero_means_single_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """retries=0: searxng attempted once then chain moves to duckduckgo."""
    sx_calls: list[int] = []

    def _sx_empty(*a: Any, **kw: Any) -> list:
        sx_calls.append(1)
        return []

    monkeypatch.setattr(_search_module, "_searxng_search", _sx_empty)
    monkeypatch.setattr(_search_module, "_duckduckgo_search", lambda *a, **kw: [DDG_HIT])

    result = search(
        "q", provider="searxng,duckduckgo", retries=0, sleep_fn=lambda _: None
    )

    assert result == [DDG_HIT]
    assert len(sx_calls) == 1


def test_sleep_called_between_attempts_not_after_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With retries=2 and always-empty single provider, sleep called exactly 2 times."""
    sleep_calls: list[float] = []

    monkeypatch.setattr(_search_module, "_searxng_search", lambda *a, **kw: [])

    result = search(
        "q",
        provider="searxng",
        retries=2,
        sleep_fn=lambda s: sleep_calls.append(s),
    )

    assert result == []
    assert len(sleep_calls) == 2  # between attempt 0→1 and 1→2, not after attempt 2


def test_env_retries_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without MINGJING_SEARCH_RETRIES env var, default is 2 → 3 total attempts."""
    monkeypatch.delenv("MINGJING_SEARCH_RETRIES", raising=False)

    sx_calls: list[int] = []

    def _sx_always_empty(*a: Any, **kw: Any) -> list:
        sx_calls.append(1)
        return []

    monkeypatch.setattr(_search_module, "_searxng_search", _sx_always_empty)

    result = search("q", provider="searxng", sleep_fn=lambda _: None)

    assert result == []
    assert len(sx_calls) == 3  # default retries=2 → 3 attempts


# ---------------------------------------------------------------------------
# _bocha_search (博查 — China-reachable primary engine)
# ---------------------------------------------------------------------------

from mingjing.collector.search import _bocha_search, bind_provider  # noqa: E402


def test_bocha_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bocha maps data.webPages.value → {url,title,snippet}, preferring summary."""
    fake_data = {
        "code": 200,
        "data": {
            "webPages": {
                "value": [
                    {"name": "t1", "url": "u1", "snippet": "short1", "summary": "long1"},
                    {"name": "t2", "url": "u2", "snippet": "short2"},  # no summary
                ]
            }
        },
    }
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(200, fake_data))

    results = _bocha_search("q", 5, "key")

    assert results == [
        {"url": "u1", "title": "t1", "snippet": "long1"},  # summary preferred
        {"url": "u2", "title": "t2", "snippet": "short2"},  # falls back to snippet
    ]


def test_bocha_empty_key_skips_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty key returns [] and never touches the network."""
    def _must_not_call(*a: Any, **kw: Any) -> Any:
        raise AssertionError("requests.post must not be called without a key")

    monkeypatch.setattr("requests.post", _must_not_call)
    assert _bocha_search("q", 5, "") == []


def test_bocha_http_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(429, {}))
    assert _bocha_search("q", 5, "key") == []


def test_bocha_exception_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*a: Any, **kw: Any) -> Any:
        raise ConnectionError("boom")

    monkeypatch.setattr("requests.post", _raise)
    assert _bocha_search("q", 5, "key") == []


def test_bocha_missing_levels_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive nav: a response missing data/webPages/value yields [], not a crash."""
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(200, {"code": 200}))
    assert _bocha_search("q", 5, "key") == []


def test_bocha_tolerates_top_level_webpages(monkeypatch: pytest.MonkeyPatch) -> None:
    """A response with webPages at the top level (no `data` wrapper) still parses."""
    fake_data = {"webPages": {"value": [{"name": "t", "url": "u", "summary": "s"}]}}
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(200, fake_data))
    assert _bocha_search("q", 5, "key") == [{"url": "u", "title": "t", "snippet": "s"}]


def test_bocha_non_dict_body_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-dict JSON body (e.g. a bare list) yields [], not a crash."""
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(200, ["oops"]))
    assert _bocha_search("q", 5, "key") == []


def test_bocha_skips_non_dict_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed (non-dict) entries in value are skipped, valid ones kept."""
    fake_data = {"data": {"webPages": {"value": ["junk", {"name": "t", "url": "u", "snippet": "x"}]}}}
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_response(200, fake_data))
    assert _bocha_search("q", 5, "key") == [{"url": "u", "title": "t", "snippet": "x"}]


def test_bind_provider_bocha_returns_callable() -> None:
    """bind_provider wires 'bocha' to a (query)->previews callable."""
    fn = bind_provider("bocha", top_k=5, bocha_key="key")
    assert callable(fn)
