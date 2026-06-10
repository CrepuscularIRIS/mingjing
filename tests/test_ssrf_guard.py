"""Direct tests for the SSRF guard `is_safe_url`.

Regression: the guard used to reject *every* normal hostname because the
IP-block check fails closed on non-IP input. These tests pin both the
allow path (public hostnames/IPs) and the block path (private/metadata),
with DNS monkeypatched so the suite stays offline.
"""

from mingjing.collector import fetch


def _fake_getaddrinfo(ip):
    return lambda host, port, *a, **k: [(2, 1, 6, "", (ip, 0))]


def test_public_hostname_allowed(monkeypatch):
    # Regression: a normal hostname resolving to a public IP must pass.
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert fetch.is_safe_url("https://www.example.com/pricing") is True


def test_public_hostname_resolving_to_private_ip_blocked(monkeypatch):
    # A public name pointing at a private IP (DNS-rebinding shape) is rejected.
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.5"))
    assert fetch.is_safe_url("https://internal.evil.test/") is False


def test_literal_public_ip_allowed():
    assert fetch.is_safe_url("https://1.1.1.1/") is True


def test_literal_private_ip_blocked():
    assert fetch.is_safe_url("http://127.0.0.1/") is False
    assert fetch.is_safe_url("http://10.0.0.1/") is False


def test_metadata_blocked():
    assert fetch.is_safe_url("http://169.254.169.254/latest/meta-data/") is False
    assert fetch.is_safe_url("http://metadata.google.internal/") is False


def test_non_http_scheme_blocked():
    assert fetch.is_safe_url("file:///etc/passwd") is False
    assert fetch.is_safe_url("ftp://example.com/") is False


def test_unresolvable_host_blocked(monkeypatch):
    def _boom(host, port, *a, **k):
        raise fetch.socket.gaierror("no such host")

    monkeypatch.setattr(fetch.socket, "getaddrinfo", _boom)
    assert fetch.is_safe_url("https://nonexistent.invalid/") is False


def test_nonstandard_port_blocked():
    # Internal services on odd ports (redis 6379, etc.) are rejected pre-DNS.
    assert fetch.is_safe_url("http://example.com:6379/") is False
    assert fetch.is_safe_url("http://example.com:8080/") is False


def test_standard_ports_allowed(monkeypatch):
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert fetch.is_safe_url("https://example.com:443/") is True
    assert fetch.is_safe_url("http://example.com:80/") is True


class _FakeResp:
    def __init__(self, status_code, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.reason = ""

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)


def test_redirect_to_private_ip_blocked(monkeypatch):
    # A public page that 302-redirects to the metadata IP must be refused at the
    # redirect hop, not silently followed.
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    import requests

    def fake_get(url, timeout=None, allow_redirects=None):
        return _FakeResp(302, headers={"Location": "http://169.254.169.254/latest/"})

    monkeypatch.setattr(requests, "get", fake_get)
    import pytest

    with pytest.raises(ValueError, match="SSRF guard"):
        fetch._live_fetch("https://www.example.com/start", timeout=8.0)


def test_default_fetch_robots_blocks_unsafe_url(monkeypatch):
    """robots.txt for a loopback/metadata host must NOT be fetched (SSRF guard).

    The guard RAISES (rather than returning "") so ``robots._load_parser`` treats
    it as a short-TTL failure instead of caching an empty allow-all policy
    permanently. ``requests.get`` must never run for an unsafe robots URL.
    """
    import pytest
    import requests

    from mingjing.agents import collector

    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("requests.get must not run for an unsafe robots URL")

    monkeypatch.setattr(requests, "get", boom)

    with pytest.raises(ValueError, match="SSRF guard"):
        collector._default_fetch_robots("http://169.254.169.254")
    with pytest.raises(ValueError, match="SSRF guard"):
        collector._default_fetch_robots("http://127.0.0.1")
    assert called["n"] == 0


def test_default_fetch_robots_redirect_to_unsafe_raises(monkeypatch):
    """A safe host that 3xx-redirects robots.txt to a private/metadata target
    must be refused at the redirect hop, not followed (SSRF via redirect)."""
    import pytest

    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    import requests

    from mingjing.agents import collector

    fetched = []

    def fake_get(url, timeout=None, allow_redirects=None):
        fetched.append(url)
        # First (safe) hop redirects to the metadata IP.
        return _FakeResp(302, headers={"Location": "http://169.254.169.254/latest/"})

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ValueError, match="SSRF guard"):
        collector._default_fetch_robots("https://www.example.com")
    # Only the initial safe robots URL was requested; the unsafe redirect target
    # was validated and rejected BEFORE any request to it.
    assert fetched == ["https://www.example.com/robots.txt"]


def test_default_fetch_robots_genuine_404_returns_empty(monkeypatch):
    """A genuine 404 (no robots) returns "" — a real success = fail-open allow."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    import requests

    from mingjing.agents import collector

    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResp(404, text="nope"))
    assert collector._default_fetch_robots("https://www.example.com") == ""


def test_default_fetch_robots_allows_safe_url(monkeypatch):
    """A public host still issues the robots.txt request via requests.get."""
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    import requests

    from mingjing.agents import collector

    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _FakeResp(200, text="User-agent: *\n")
    )
    assert collector._default_fetch_robots("https://www.example.com") == "User-agent: *\n"


def test_redirect_to_public_followed(monkeypatch):
    monkeypatch.setattr(fetch.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    import requests

    calls = {"n": 0}

    def fake_get(url, timeout=None, allow_redirects=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(302, headers={"Location": "https://www.example.com/final"})
        return _FakeResp(200, text="<html><body>Pricing $10</body></html>")

    monkeypatch.setattr(requests, "get", fake_get)
    result = fetch._live_fetch("https://www.example.com/start", timeout=8.0)
    assert result.source_mode == "LIVE"
    assert "Pricing $10" in result.text
    assert result.url == "https://www.example.com/final"
