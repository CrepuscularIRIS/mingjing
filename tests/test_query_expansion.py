"""Tests for query expansion — all offline, no network, no LLM key required."""

from __future__ import annotations

from collections.abc import Callable

from mingjing.collector.query_expansion import expand_queries

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm(response: str) -> Callable[[str], str]:
    """Return a fake llm callable that always returns *response*."""

    def _llm(prompt: str) -> str:  # noqa: ARG001
        return response

    return _llm


def _make_counting_llm(response: str) -> tuple[Callable[[str], str], list[int]]:
    """Return a fake llm callable AND a call-counter list."""
    calls: list[int] = []

    def _llm(prompt: str) -> str:  # noqa: ARG001
        calls.append(1)
        return response

    return _llm, calls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_expands_to_n_queries():
    """Fake llm returns 3 newline-separated queries → result has 3 unique queries."""
    llm = _make_llm("query alpha\nquery beta\nquery gamma")
    result = expand_queries("CompA", "pricing", "CompA pricing", n=3, llm=llm)
    assert result == ["query alpha", "query beta", "query gamma"]


def test_parses_and_strips_list_markers():
    """Numbered list markers and bullet markers must be stripped."""
    llm = _make_llm("1. foo\n2. bar")
    result = expand_queries("CompA", "pricing", "CompA pricing", n=5, llm=llm)
    assert result == ["foo", "bar"]


def test_parses_bullet_markers():
    """Dash and asterisk bullet markers must be stripped."""
    llm = _make_llm("- foo\n* bar")
    result = expand_queries("CompA", "pricing", "CompA pricing", n=5, llm=llm)
    assert result == ["foo", "bar"]


def test_parses_bullet_markers_no_space():
    """Bullets with NO trailing space (*foo, -foo) must also be stripped."""
    llm = _make_llm("*foo\n-bar")
    result = expand_queries("CompA", "pricing", "CompA pricing", n=5, llm=llm)
    assert result == ["foo", "bar"]


def test_parses_parenthesis_marker():
    """Parenthesis-style numbered marker (e.g. '1) foo') must be stripped."""
    llm = _make_llm("1) foo\n2) bar")
    result = expand_queries("CompA", "pricing", "CompA pricing", n=5, llm=llm)
    assert result == ["foo", "bar"]


def test_dedups_and_caps_at_n():
    """5 lines with duplicates, n=3 → exactly [alpha, beta, gamma] in order."""
    lines = "alpha\nbeta\nalpha\ngamma\nbeta"
    llm = _make_llm(lines)
    result = expand_queries("CompB", "market share", "CompB market", n=3, llm=llm)
    assert result == ["alpha", "beta", "gamma"]


def test_empty_response_falls_back_to_base():
    """LLM returns empty string → [base_query]."""
    base = "CompC revenue 2024"
    llm = _make_llm("")
    result = expand_queries("CompC", "revenue", base, n=3, llm=llm)
    assert result == [base]


def test_whitespace_only_response_falls_back_to_base():
    """LLM returns only whitespace → [base_query]."""
    base = "CompD product line"
    llm = _make_llm("   \n\n  ")
    result = expand_queries("CompD", "products", base, n=3, llm=llm)
    assert result == [base]


def test_llm_failure_falls_back_to_base():
    """LLM raises → [base_query], no exception propagates."""

    def _failing_llm(prompt: str) -> str:  # noqa: ARG001
        raise RuntimeError("network error")

    base = "CompE strategy"
    result = expand_queries("CompE", "strategy", base, n=3, llm=_failing_llm)
    assert result == [base]


def test_cache_hit_skips_second_llm_call():
    """Second call with same (run_id, competitor, field) uses cache; llm called once."""
    llm, calls = _make_counting_llm("line one\nline two\nline three")
    cache: dict = {}

    result1 = expand_queries(
        "CompF", "tech", "CompF tech", n=3, llm=llm, cache=cache, run_id="run1"
    )
    result2 = expand_queries(
        "CompF", "tech", "CompF tech", n=3, llm=llm, cache=cache, run_id="run1"
    )

    assert len(calls) == 1, f"llm should be called once, was called {len(calls)} times"
    assert result1 == result2


def test_cache_miss_on_different_run_id():
    """Different run_id → cache miss → llm called again."""
    llm, calls = _make_counting_llm("line one\nline two")
    cache: dict = {}

    expand_queries("CompG", "ops", "CompG ops", n=2, llm=llm, cache=cache, run_id="run-a")
    expand_queries("CompG", "ops", "CompG ops", n=2, llm=llm, cache=cache, run_id="run-b")

    assert len(calls) == 2


def test_result_is_never_empty():
    """Guarantee: result list is never empty regardless of llm output."""
    llm = _make_llm("")
    result = expand_queries("CompH", "HR", "CompH HR", n=3, llm=llm)
    assert len(result) >= 1


def test_prompt_includes_base_query():
    """The base_query (the actual topic) MUST appear in the prompt.

    In production the closure passes competitor="" and field="" (collect_fn has
    neither), so base_query is the only research signal — it must reach the LLM.
    """
    captured: list[str] = []

    def _capturing_llm(prompt: str) -> str:
        captured.append(prompt)
        return "q1\nq2"

    expand_queries("", "", "Feishu pricing tiers", n=2, llm=_capturing_llm)
    assert captured, "llm should have been called"
    assert "Feishu pricing tiers" in captured[0]


def test_different_base_query_same_empty_context_does_not_collide():
    """Regression: the production closure passes constant empty competitor/field/run_id
    with a DIFFERENT base_query per field. base_query must be in the cache key so each
    field's expansion is computed fresh (not reused from the first field)."""
    calls: list[str] = []

    def _per_query_llm(prompt: str) -> str:
        calls.append(prompt)
        # Echo a query derived from the prompt so different base_queries yield
        # different results (proves no stale-cache reuse).
        return f"expanded::{len(calls)}"

    cache: dict = {}
    r1 = expand_queries("", "", "pricing model", n=1, llm=_per_query_llm, cache=cache, run_id="")
    r2 = expand_queries("", "", "user sentiment", n=1, llm=_per_query_llm, cache=cache, run_id="")
    r3 = expand_queries("", "", "feature tree", n=1, llm=_per_query_llm, cache=cache, run_id="")

    assert len(calls) == 3, "each distinct base_query must trigger its own llm call"
    assert r1 != r2 != r3, "different base_queries must not reuse the first expansion"

    # And a true repeat (same base_query) DOES hit the cache.
    r1_again = expand_queries("", "", "pricing model", n=1, llm=_per_query_llm, cache=cache, run_id="")
    assert len(calls) == 3, "repeat of an already-expanded base_query must hit the cache"
    assert r1_again == r1
