"""Task 6 unit tests: the JSON parse/repair function (the 2am breaker).

These tests exercise ``parse_json_with_repair`` only — a PURE function with no
network access and no API key required.
"""

import pytest

from mingjing.llm import _strip_think_blocks, parse_json_with_repair


def test_clean_json():
    assert parse_json_with_repair('{"a":1}') == {"a": 1}


def test_fenced():
    assert parse_json_with_repair('```json\n{"a":1}\n```') == {"a": 1}


def test_prose_wrapped():
    assert parse_json_with_repair('Sure! {"a":1} done') == {"a": 1}


def test_unrepairable_raises():
    with pytest.raises(ValueError):
        parse_json_with_repair("not json at all")


# ---------------------------------------------------------------------------
# Task 15a — <think> block stripping (MiniMax-M2.7 reasoning model output)
# ---------------------------------------------------------------------------


def test_strip_think_blocks_basic():
    """Think block is removed; only the suffix remains."""
    assert _strip_think_blocks('<think>reasoning</think>{"a":1}') == '{"a":1}'


def test_strip_think_blocks_multiline():
    """Multi-line think block is removed."""
    raw = "<think>\nline1\nline2\n</think>\n{\"b\":2}"
    # The leading '\n' between </think> and the JSON is intentionally preserved:
    # _strip_think_blocks removes only the <think>...</think> span, not surrounding
    # whitespace.  Callers (parse_json_with_repair) strip/trim as needed.
    assert _strip_think_blocks(raw) == '\n{"b":2}'


def test_strip_think_blocks_none_present():
    """If no think tags, text is returned unchanged."""
    assert _strip_think_blocks('{"a":1}') == '{"a":1}'


def test_strip_think_blocks_stray_open_tag():
    """A lone <think> (no closing tag) is removed."""
    assert _strip_think_blocks('<think>{"a":1}') == '{"a":1}'


def test_strip_think_blocks_stray_close_tag():
    """A lone </think> is removed."""
    assert _strip_think_blocks('</think>{"a":1}') == '{"a":1}'


def test_think_block_stripped():
    """Decoy JSON inside <think> must NOT win — the outer JSON is returned."""
    assert parse_json_with_repair('<think>reasoning here {"decoy":99}</think>{"a":1}') == {"a": 1}


def test_think_block_multiline_then_fenced():
    """Multi-line think block followed by a fenced JSON block."""
    result = parse_json_with_repair(
        '<think>line1\nline2 {"x":0}</think>\n```json\n{"a":1}\n```'
    )
    assert result == {"a": 1}


def test_think_with_only_real_json_after():
    """Think block quotes JSON from the prompt; the real JSON follows after."""
    raw = '<think>The user wants {"plan":"pro"} maybe</think> {"plan":"pro","price_usd":10}'
    assert parse_json_with_repair(raw) == {"plan": "pro", "price_usd": 10}


def test_strip_think_handles_nested():
    """Nested <think> blocks must be fully stripped (convergent loop required).

    A single non-greedy re.sub pass removes only the innermost span and leaves
    the outer reasoning text.  The convergent loop ensures the outer shell is
    also removed before the JSON suffix is extracted.
    """
    assert _strip_think_blocks('<think>a <think>b {"decoy":9}</think> c</think>{"a":1}') == '{"a":1}'


# ---------------------------------------------------------------------------
# Fix — call_llm must pass max_tokens to the OpenAI client
# ---------------------------------------------------------------------------


def test_call_llm_passes_max_tokens_to_create(tmp_path, monkeypatch):
    """call_llm must forward max_tokens to client.chat.completions.create.

    MiniMax-M2.7 emits long <think> blocks; without an explicit cap the
    combined reasoning + structured JSON can be truncated mid-JSON.
    We mock the OpenAI client to capture the kwargs and assert max_tokens
    is present and > 0.
    """
    import unittest.mock as mock

    from mingjing.config import Settings
    from mingjing.db import Database
    from mingjing.llm import call_llm

    # Build a minimal settings object with the new field.
    settings = Settings(
        minimax_base_url="https://api.minimaxi.com/v1",
        minimax_api_key="test-key",
        minimax_model="MiniMax-M2.7",
        mode="live_first",
        rate_limiting_enabled=True,
        db_path=str(tmp_path / "run.db"),
        cache_db_path=str(tmp_path / "cache.db"),
        per_field_source_cap=3,
        min_source_chars=100,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth="quick",
        deep_collect_workers=8,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
    )

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(category="cat", competitors=[], goal="g")

    captured: dict = {}

    # Build a mock response that the client will return.
    fake_choice = mock.MagicMock()
    fake_choice.message.content = '{"a": 1}'
    fake_resp = mock.MagicMock()
    fake_resp.choices = [fake_choice]
    fake_resp.usage = None

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_resp

    fake_completions = mock.MagicMock()
    fake_completions.create = fake_create
    fake_chat = mock.MagicMock()
    fake_chat.completions = fake_completions
    fake_client = mock.MagicMock()
    fake_client.chat = fake_chat

    # OpenAI is a local import inside call_llm; patch the source module.
    with mock.patch("openai.OpenAI", return_value=fake_client):
        call_llm(
            db,
            run_id,
            messages=[{"role": "user", "content": "hello"}],
            settings=settings,
        )

    assert "max_tokens" in captured, "max_tokens must be passed to create()"
    assert captured["max_tokens"] > 0, "max_tokens must be a positive integer"
    assert captured["max_tokens"] == 8000
