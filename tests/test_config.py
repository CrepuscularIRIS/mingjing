import pytest

from mingjing.config import Settings


def test_rate_limiting_must_be_enabled(monkeypatch):
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "false")
    with pytest.raises(ValueError, match="rate_limiting"):
        Settings.load()


@pytest.mark.parametrize("token", ["1", "true", "TRUE", "yes", "on"])
def test_rate_limiting_accepts_truthy_tokens(monkeypatch, token):
    """Common truthy tokens (incl. .env.example's '1') load OK."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", token)
    assert Settings.load().rate_limiting_enabled is True


@pytest.mark.parametrize("token", ["0", "false", "no", "off"])
def test_rate_limiting_rejects_falsy_tokens(monkeypatch, token):
    """Explicitly falsy values still fail fast."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", token)
    with pytest.raises(ValueError, match="rate_limiting"):
        Settings.load()


def test_mode_defaults_live_first(monkeypatch):
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.delenv("MINGJING_MODE", raising=False)
    assert Settings.load().mode == "live_first"


# ---------------------------------------------------------------------------
# Task 15a — MingJing-owned base URL (must NOT inherit MINIMAX_BASE_URL=/anthropic)
# ---------------------------------------------------------------------------


def test_base_url_ignores_minimax_base_url_env(monkeypatch):
    """MINIMAX_BASE_URL (set to /anthropic variant) must NOT affect MingJing base URL.

    When MINGJING_LLM_BASE_URL is unset, the MingJing default (/v1) is used
    regardless of whatever MINIMAX_BASE_URL is set to in the environment.
    """
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.delenv("MINGJING_LLM_BASE_URL", raising=False)
    assert Settings.load().minimax_base_url == "https://api.minimaxi.com/v1"


def test_base_url_honored_via_mingjing_var(monkeypatch):
    """MINGJING_LLM_BASE_URL is honored when set."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_LLM_BASE_URL", "https://x/v1")
    assert Settings.load().minimax_base_url == "https://x/v1"


def test_model_defaults_to_minimax_m27(monkeypatch):
    """minimax_model defaults to MiniMax-M2.7 when MINIMAX_MODEL is unset."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.delenv("MINIMAX_MODEL", raising=False)
    assert Settings.load().minimax_model == "MiniMax-M2.7"


def test_llm_max_tokens_defaults_to_8000(monkeypatch):
    """llm_max_tokens defaults to 8000 when MINGJING_LLM_MAX_TOKENS is unset."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.delenv("MINGJING_LLM_MAX_TOKENS", raising=False)
    assert Settings.load().llm_max_tokens == 8000


def test_llm_max_tokens_honoured_via_env(monkeypatch):
    """MINGJING_LLM_MAX_TOKENS is honoured when set."""
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_LLM_MAX_TOKENS", "16000")
    assert Settings.load().llm_max_tokens == 16000
