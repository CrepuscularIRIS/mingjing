"""Tests for finite LLM client timeout (fix for production hang).

ROOT CAUSE fixed here:
    call_llm built an OpenAI client with no timeout, so a stuck provider
    could block for up to ~1800 s (SDK default 600 s × 2 retries) before
    raising. A hang never raises, so the analyze node's existing degradation
    guard (except Exception → _log_skipped_field_exc → continue) was never
    triggered — the whole run stayed in ``running`` forever.

THE FIX:
    _build_client now passes ``timeout=settings.llm_timeout_s`` to the
    OpenAI constructor, giving every call a finite ceiling. A timeout raises
    ``openai.APITimeoutError``, which IS an Exception → the analyze node's
    existing guard catches it, logs it as a skipped field, and continues.

The "raise → skip field → partial" degradation path is ALREADY covered by:
    - tests/test_analyze_guard.py (exception-guard unit tests)
    - tests/test_runner.py (end-to-end with exception injection)
We do NOT duplicate those here — we only lock that _build_client passes a
finite timeout so the hang condition can never occur.
"""

import pytest

# ---------------------------------------------------------------------------
# test_build_client_sets_finite_timeout
# ---------------------------------------------------------------------------

def test_build_client_sets_finite_timeout() -> None:
    """_build_client passes llm_timeout_s to the OpenAI constructor.

    Constructing the OpenAI client does NO network I/O, so this test is
    fully offline. We read `.timeout` off the returned client to assert the
    value was accepted.
    """
    from mingjing.config import Settings
    from mingjing.llm import _build_client

    settings = Settings(
        minimax_base_url="https://api.minimaxi.com/v1",
        minimax_api_key="test-key",
        minimax_model="test-model",
        mode="live_first",
        rate_limiting_enabled=True,
        db_path=":memory:",
        cache_db_path=":memory:",
        per_field_source_cap=3,
        min_source_chars=0,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        depth="quick",
        deep_collect_workers=8,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
        llm_timeout_s=42.0,
    )

    client = _build_client(settings)

    # The openai SDK exposes the configured timeout via client.timeout.
    # It may be a float or an httpx.Timeout object; either way the scalar
    # read-back should equal 42.0.
    timeout_val = client.timeout
    # httpx.Timeout stores the value in .read / .connect / .write / .pool;
    # plain float stored directly. Handle both.
    try:
        # httpx.Timeout case
        actual = float(timeout_val.read)
    except AttributeError:
        actual = float(timeout_val)

    assert actual == 42.0, (
        f"Expected client.timeout == 42.0 but got {timeout_val!r}. "
        "_build_client must pass timeout=settings.llm_timeout_s to OpenAI(...)."
    )


# ---------------------------------------------------------------------------
# test_settings_load_reads_llm_timeout
# ---------------------------------------------------------------------------

def test_settings_load_reads_llm_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings.load() reads MINGJING_LLM_TIMEOUT and defaults to 90.0."""
    # 1. Explicit value: 15 → 15.0
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_LLM_TIMEOUT", "15")

    from mingjing.config import Settings

    settings_15 = Settings.load()
    assert settings_15.llm_timeout_s == 15.0, (
        f"Expected 15.0 but got {settings_15.llm_timeout_s!r}. "
        "Settings.load() must read MINGJING_LLM_TIMEOUT as a float."
    )

    # 2. Unset → default 90.0
    monkeypatch.delenv("MINGJING_LLM_TIMEOUT", raising=False)

    # Force reimport to clear any module-level caching
    settings_default = Settings.load()
    assert settings_default.llm_timeout_s == 90.0, (
        f"Expected 90.0 (default) but got {settings_default.llm_timeout_s!r}. "
        "Settings.load() must default MINGJING_LLM_TIMEOUT to 90.0."
    )
