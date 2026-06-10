"""Tests for the env-gated LangSmith tracing helpers in mingjing.llm.

Invariant: when LangSmith env vars are UNSET, behavior is byte-identical to
the baseline (no langsmith import, no overhead, same return value).
"""

import sys
import types

from mingjing.llm import _maybe_wrap_openai, tracing_enabled

# ---------------------------------------------------------------------------
# tracing_enabled — env var logic
# ---------------------------------------------------------------------------


def test_tracing_disabled_when_both_unset(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    assert tracing_enabled() is False


def test_tracing_enabled_via_langsmith_tracing(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    assert tracing_enabled() is True


def test_tracing_enabled_via_langchain_v2_alias(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "1")
    assert tracing_enabled() is True


def test_tracing_disabled_for_false_value(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert tracing_enabled() is False


def test_tracing_disabled_for_garbage_value(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "nope")
    assert tracing_enabled() is False


def test_tracing_case_insensitive(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "TRUE")
    assert tracing_enabled() is True


def test_tracing_strips_whitespace(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "  yes  ")
    assert tracing_enabled() is True


# ---------------------------------------------------------------------------
# _maybe_wrap_openai — identity when disabled
# ---------------------------------------------------------------------------


def test_no_wrap_returns_same_object_when_disabled(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    sentinel = object()
    result = _maybe_wrap_openai(sentinel)
    assert result is sentinel, "Must return the identical object when tracing is disabled"


def test_no_wrap_does_not_import_langsmith_when_disabled(monkeypatch):
    """When tracing is disabled, _maybe_wrap_openai must not import langsmith."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    # Remove langsmith from sys.modules if present so we can detect fresh import.
    saved = sys.modules.pop("langsmith", None)
    saved_wrappers = sys.modules.pop("langsmith.wrappers", None)
    try:
        sentinel = object()
        _maybe_wrap_openai(sentinel)
        assert "langsmith" not in sys.modules, (
            "langsmith must NOT be imported when tracing is disabled"
        )
    finally:
        # Restore original state so other tests are unaffected.
        if saved is not None:
            sys.modules["langsmith"] = saved
        if saved_wrappers is not None:
            sys.modules["langsmith.wrappers"] = saved_wrappers


# ---------------------------------------------------------------------------
# _maybe_wrap_openai — calls wrap_openai when enabled (patched stub)
# ---------------------------------------------------------------------------


def test_wrap_calls_wrap_openai_when_enabled(monkeypatch):
    """When tracing is enabled, _maybe_wrap_openai delegates to wrap_openai."""
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    marker = object()

    # Build a minimal fake langsmith.wrappers module so no real network/SDK needed.
    fake_wrappers = types.ModuleType("langsmith.wrappers")
    fake_wrappers.wrap_openai = lambda client: marker  # type: ignore[attr-defined]

    fake_langsmith = types.ModuleType("langsmith")

    original_langsmith = sys.modules.get("langsmith")
    original_wrappers = sys.modules.get("langsmith.wrappers")
    sys.modules["langsmith"] = fake_langsmith
    sys.modules["langsmith.wrappers"] = fake_wrappers
    try:
        sentinel = object()
        result = _maybe_wrap_openai(sentinel)
        assert result is marker, "Must return the value from wrap_openai stub"
    finally:
        # Restore original state.
        if original_langsmith is None:
            sys.modules.pop("langsmith", None)
        else:
            sys.modules["langsmith"] = original_langsmith
        if original_wrappers is None:
            sys.modules.pop("langsmith.wrappers", None)
        else:
            sys.modules["langsmith.wrappers"] = original_wrappers


def test_wrap_degrades_gracefully_on_import_error(monkeypatch):
    """When langsmith is absent but tracing is enabled, return client unchanged.

    We simulate ImportError by injecting a broken module into sys.modules that
    raises ImportError when wrap_openai is accessed, and by temporarily making
    the import fail via a fake module object.
    """
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    # Build a fake langsmith.wrappers that raises ImportError on import.
    # We do this by inserting a special module object whose import raises.
    # The cleanest approach: temporarily replace langsmith.wrappers in sys.modules
    # with a broken module whose __getattr__ raises ImportError, but since the
    # import statement `from langsmith.wrappers import wrap_openai` first imports
    # the module then accesses the attr, we need the module itself to not exist.
    # Solution: remove it from sys.modules and use a custom importer that raises.

    original_wrappers = sys.modules.pop("langsmith.wrappers", None)

    class _FailModule(types.ModuleType):
        """A module that raises ImportError when any attribute is accessed."""

        def __getattr__(self, name):
            raise ImportError(f"Simulated absent langsmith: {name}")

    # Replace with a failing module so `from langsmith.wrappers import wrap_openai`
    # triggers AttributeError which is NOT caught — instead, make the module itself
    # unavailable by removing it and patching the parent to not have .wrappers.
    # Simplest reliable approach: inject an _FailModule that raises ImportError
    # when wrap_openai is accessed.
    fail_mod = _FailModule("langsmith.wrappers")
    sys.modules["langsmith.wrappers"] = fail_mod
    try:
        sentinel = object()
        result = _maybe_wrap_openai(sentinel)
        assert result is sentinel, (
            "On ImportError, must return the unwrapped client unchanged"
        )
    finally:
        if original_wrappers is None:
            sys.modules.pop("langsmith.wrappers", None)
        else:
            sys.modules["langsmith.wrappers"] = original_wrappers


# ---------------------------------------------------------------------------
# Graph-build invariant — building the graph works with LangSmith env unset
# ---------------------------------------------------------------------------


def test_graph_builds_without_langsmith_env(monkeypatch):
    """Building the LangGraph must not require LangSmith env vars."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    from mingjing.graph import build_graph

    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    expected = {"intake", "plan", "collect", "analyze", "qa", "route", "revise", "write"}
    assert expected <= nodes, f"Graph nodes missing expected keys; got {nodes}"


# ---------------------------------------------------------------------------
# Module-level import invariant — mingjing.llm source must have no top-level
# langsmith import (the guard is inside functions only)
# ---------------------------------------------------------------------------


def test_llm_module_has_no_toplevel_langsmith_import():
    """mingjing.llm must not have a top-level 'import langsmith' statement.

    We inspect the module source directly — this is more robust than checking
    sys.modules (which varies with test ordering) and pinpoints a source-level
    regression rather than an import-order accident.
    """
    import importlib
    import inspect

    import mingjing.llm as llm_mod

    importlib.reload(llm_mod)  # ensure fresh parse
    source = inspect.getsource(llm_mod)

    # Find all lines that are plain top-level imports (not inside a def/class).
    top_level_import_langsmith = False
    for line in source.splitlines():
        stripped = line.lstrip()
        # A top-level import line has zero leading spaces (not inside a block).
        if not line.startswith(" ") and not line.startswith("\t"):
            if stripped.startswith("import langsmith") or stripped.startswith(
                "from langsmith"
            ):
                top_level_import_langsmith = True
                break

    assert not top_level_import_langsmith, (
        "mingjing.llm must not have a top-level 'import langsmith' / "
        "'from langsmith' statement — all langsmith imports must be guarded "
        "inside functions."
    )
