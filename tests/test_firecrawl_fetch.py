"""Task 5 unit tests: Firecrawl JS-render fallback fetcher.

All tests are offline: HTTP is mocked via unittest.mock / monkeypatch.
No real network is touched and no API key is required.
"""

from unittest.mock import MagicMock, patch

from mingjing.collector.fetch import FetchResult
from mingjing.collector.firecrawl_fetch import firecrawl_fetch

# ---------------------------------------------------------------------------
# firecrawl_fetch unit tests
# ---------------------------------------------------------------------------


class _FakeCache:
    """Minimal read-only cache for fetch_with_fallback integration tests."""

    def __init__(self, store: dict):
        self._store = store

    def get(self, url: str) -> FetchResult | None:
        return self._store.get(url)


def test_firecrawl_success_returns_fetchresult():
    """POST 200 with data.markdown → FetchResult with that text, source_mode LIVE."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "success": True,
        "data": {"markdown": "# Rendered page\nLots of real content here."},
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="fc-testkey",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is not None
    assert isinstance(result, FetchResult)
    assert result.text == "# Rendered page\nLots of real content here."
    assert result.source_mode == "LIVE"
    assert result.url == "https://example.com/spa"
    assert result.content_hash  # auto-computed
    mock_post.assert_called_once()


def test_firecrawl_empty_key_returns_none():
    """api_key='' → return None immediately; requests must NOT be called."""
    with patch("requests.post") as mock_post:
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is None
    mock_post.assert_not_called()


def test_firecrawl_http_error_returns_none():
    """HTTP 500 response → log warning, return None, never raise."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.ok = False
    mock_resp.raise_for_status.side_effect = Exception("Server Error")

    with patch("requests.post", return_value=mock_resp):
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="fc-testkey",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is None


def test_firecrawl_exception_returns_none():
    """requests raises (network error, timeout, etc.) → return None, never raise."""
    with patch("requests.post", side_effect=ConnectionError("network down")):
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="fc-testkey",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is None


def test_firecrawl_uses_data_content_fallback():
    """data.markdown absent, data.content present → use data.content."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "success": True,
        "data": {"content": "Fallback content text."},
    }

    with patch("requests.post", return_value=mock_resp):
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="fc-testkey",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is not None
    assert result.text == "Fallback content text."


def test_firecrawl_empty_text_returns_none():
    """Rendered text is empty → treat as a failure, return None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.json.return_value = {"success": True, "data": {"markdown": ""}}

    with patch("requests.post", return_value=mock_resp):
        result = firecrawl_fetch(
            "https://example.com/spa",
            api_key="fc-testkey",
            base_url="https://api.firecrawl.dev/v1",
        )

    assert result is None


# ---------------------------------------------------------------------------
# fetch_with_fallback integration tests (firecrawl= parameter)
# ---------------------------------------------------------------------------


def test_fallback_invokes_firecrawl_on_thin_plain_result(monkeypatch):
    """Plain fetch yields thin text (< min_chars); firecrawl returns rich text → use rich."""
    from mingjing.collector.fetch import fetch_with_fallback

    thin_result = FetchResult(text="tiny", url="https://example.com/spa", source_mode="LIVE")
    rich_result = FetchResult(
        text="A" * 500, url="https://example.com/spa", source_mode="LIVE"
    )

    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: thin_result,
    )

    fake_firecrawl = lambda url: rich_result  # noqa: E731

    cache = _FakeCache({})
    result = fetch_with_fallback(
        "https://example.com/spa",
        cache=cache,
        firecrawl=fake_firecrawl,
        min_chars=100,
    )

    assert result.text == "A" * 500


def test_fallback_keeps_plain_when_firecrawl_also_thin(monkeypatch):
    """Plain thin + firecrawl returns None → original thin result kept."""
    from mingjing.collector.fetch import fetch_with_fallback

    thin_result = FetchResult(text="tiny", url="https://example.com/spa", source_mode="LIVE")

    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: thin_result,
    )

    fake_firecrawl = lambda url: None  # noqa: E731

    cache = _FakeCache({})
    result = fetch_with_fallback(
        "https://example.com/spa",
        cache=cache,
        firecrawl=fake_firecrawl,
        min_chars=100,
    )

    assert result.text == "tiny"


def test_fallback_keeps_plain_when_firecrawl_returns_shorter(monkeypatch):
    """Firecrawl IS called (plain below min_chars) but returns a shorter result → keep plain.

    Specifically exercises the branch:
      plain_len < min_chars  →  firecrawl(url) is called
      len(fc_result.text.strip()) <= plain_len  →  NOT richer → keep plain
    """
    from mingjing.collector.fetch import fetch_with_fallback

    # plain text is 50 chars, below min_chars=100 → firecrawl will be invoked
    plain_result = FetchResult(text="x" * 50, url="https://example.com/spa", source_mode="LIVE")
    # firecrawl returns 20 chars — not richer than 50
    firecrawl_result = FetchResult(
        text="y" * 20, url="https://example.com/spa", source_mode="LIVE"
    )

    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: plain_result,
    )

    called = []

    def fake_firecrawl(url: str) -> FetchResult | None:
        called.append(url)
        return firecrawl_result

    cache = _FakeCache({})
    result = fetch_with_fallback(
        "https://example.com/spa",
        cache=cache,
        firecrawl=fake_firecrawl,
        min_chars=100,  # 50 < 100 → firecrawl IS invoked
    )

    # firecrawl was called (50 < 100) but its result is not richer (20 <= 50)
    assert called == ["https://example.com/spa"]
    assert result.text == "x" * 50  # original plain result kept


def test_fallback_keeps_plain_when_firecrawl_not_richer(monkeypatch):
    """Firecrawl returns a result that is not richer → keep plain result."""
    from mingjing.collector.fetch import fetch_with_fallback

    plain_result = FetchResult(text="x" * 50, url="https://example.com/spa", source_mode="LIVE")
    firecrawl_result = FetchResult(
        text="y" * 10, url="https://example.com/spa", source_mode="LIVE"
    )

    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: plain_result,
    )

    fake_firecrawl = lambda url: firecrawl_result  # noqa: E731

    cache = _FakeCache({})
    result = fetch_with_fallback(
        "https://example.com/spa",
        cache=cache,
        firecrawl=fake_firecrawl,
        min_chars=10,  # plain_result.text (50 chars) < min_chars? No, 50 >= 10, so no upgrade
    )

    # plain text is >= min_chars (50 >= 10), so firecrawl should NOT be invoked
    assert result.text == "x" * 50


def test_no_firecrawl_means_unchanged_behavior(monkeypatch):
    """firecrawl=None (default) → identical to existing behavior."""
    from mingjing.collector.fetch import fetch_with_fallback

    live_result = FetchResult(text="live content", url="http://x", source_mode="LIVE")
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: live_result,
    )

    cache = _FakeCache({})
    result = fetch_with_fallback("http://x", cache=cache)

    assert result.source_mode == "LIVE"
    assert result.text == "live content"


def test_no_firecrawl_cache_fallback_unchanged(monkeypatch):
    """firecrawl=None, live fails → falls back to cache exactly as before."""
    from mingjing.collector.fetch import fetch_with_fallback

    cached = FetchResult(text="cached body", url="http://x", source_mode="CACHED")
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: (_ for _ in ()).throw(TimeoutError()),
    )

    cache = _FakeCache({"http://x": cached})
    result = fetch_with_fallback("http://x", cache=cache)

    assert result.source_mode == "CACHED"
    assert result.text == "cached body"


def test_firecrawl_not_called_when_plain_meets_min_chars(monkeypatch):
    """Plain result satisfies min_chars → firecrawl callable is never invoked."""
    from mingjing.collector.fetch import fetch_with_fallback

    rich_plain = FetchResult(
        text="x" * 200, url="https://example.com/spa", source_mode="LIVE"
    )
    monkeypatch.setattr(
        "mingjing.collector.fetch._live_fetch",
        lambda url, timeout: rich_plain,
    )

    called = []

    def fake_firecrawl(url: str) -> FetchResult | None:
        called.append(url)
        return None

    cache = _FakeCache({})
    result = fetch_with_fallback(
        "https://example.com/spa",
        cache=cache,
        firecrawl=fake_firecrawl,
        min_chars=100,  # 200 chars >= 100 → no firecrawl
    )

    assert result.text == "x" * 200
    assert called == []  # firecrawl was NOT invoked
