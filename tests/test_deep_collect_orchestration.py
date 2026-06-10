"""Tests for Task 6: deep-collect orchestration + settings-closure wiring.

All offline — no network, no real LLM, no real API keys.  Fakes are injected via
monkeypatching or passed as keyword arguments.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_DUMMY_CACHE = MagicMock()
_DUMMY_CACHE.get.return_value = None  # cache miss → force fetch path


def _make_settings(
    *,
    depth: str = "quick",
    deep_collect_workers: int = 2,
    fetch_budget_per_run: int = 10,
    firecrawl_api_key: str = "",
    firecrawl_base_url: str = "https://api.firecrawl.dev/v1",
    min_source_chars: int = 0,
    fetch_timeout_s: float = 8.0,
    minimax_base_url: str = "https://api.example.com/v1",
    minimax_api_key: str = "test-key",
    minimax_model: str = "test-model",
    mode: str = "live_first",
) -> Any:
    """Build a minimal Settings-like object for tests."""
    from mingjing.config import Settings

    return Settings(
        minimax_base_url=minimax_base_url,
        minimax_api_key=minimax_api_key,
        minimax_model=minimax_model,
        mode=mode,
        rate_limiting_enabled=True,
        db_path="data/mingjing.db",
        cache_db_path="data/cache/cache.db",
        per_field_source_cap=3,
        min_source_chars=min_source_chars,
        fetch_timeout_s=fetch_timeout_s,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth=depth,
        deep_collect_workers=deep_collect_workers,
        fetch_budget_per_run=fetch_budget_per_run,
        firecrawl_api_key=firecrawl_api_key,
        firecrawl_base_url=firecrawl_base_url,
    )


def _make_fetch_result(url: str = "https://example.com", text: str = "Some text content") -> Any:
    from mingjing.collector.fetch import FetchResult

    return FetchResult(text=text, url=url, source_mode="LIVE")


def _make_previews(n_domains: int = 5) -> list[dict[str, Any]]:
    """Build n preview dicts across distinct domains for search mock."""
    return [
        {
            "url": f"https://domain{i}.com/page",
            "title": f"Domain {i} Title",
            "snippet": f"Snippet from domain {i}",
            "engine": "tavily",
        }
        for i in range(n_domains)
    ]


# ---------------------------------------------------------------------------
# Part A tests — collect() extended signature
# ---------------------------------------------------------------------------


class TestCollectEnginesNoneIsLegacyBehavior:
    """engines=None must fall through to the existing single-query path."""

    def test_engines_none_is_legacy_behavior(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """collect(engines=None) uses the legacy search() path; deep helpers NOT called."""
        import mingjing.agents.collector as mod

        search_calls: list[Any] = []

        def fake_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
            search_calls.append(query)
            return []  # empty → no fetches needed

        parallel_search_calls: list[Any] = []

        def fake_parallel_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            parallel_search_calls.append(args)
            return []

        monkeypatch.setattr(mod, "_search_fn", fake_search)

        # parallel_search lives in collector.search — patch it there AND in collector
        with (
            patch("mingjing.collector.search.parallel_search", side_effect=fake_parallel_search),
            patch("mingjing.agents.collector.parallel_search", side_effect=fake_parallel_search, create=True),
        ):
            result = mod.collect("test query", _DUMMY_CACHE, engines=None)

        assert isinstance(result, list)
        assert len(search_calls) == 1
        assert search_calls[0] == "test query"
        assert len(parallel_search_calls) == 0, "parallel_search must NOT be called on legacy path"


class TestDeepPathReturnsManyDedupedSources:
    """When engines is provided, collect() runs the deep pipeline and returns sources."""

    def test_deep_path_returns_many_deduped_sources(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Deep path returns multiple deduped sources when search + fetch succeed."""
        import mingjing.agents.collector as mod

        previews = _make_previews(5)

        def fake_parallel_search(
            queries: list[str],
            engines: dict[str, Any],
            *,
            workers: int = 4,
        ) -> list[dict[str, Any]]:
            return previews

        fetch_calls: list[str] = []

        def fake_fetch(url: str, cache: Any, timeout: float = 8.0, mode: str = "live_first", **kw: Any) -> Any:
            fetch_calls.append(url)
            return _make_fetch_result(url=url, text=f"Content for {url}")

        def fake_robots_allowed(url: str, fetch_robots: Any) -> bool:
            return True

        monkeypatch.setattr("mingjing.agents.collector.parallel_search", fake_parallel_search)
        monkeypatch.setattr("mingjing.agents.collector.fetch_with_fallback", fake_fetch)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", fake_robots_allowed)

        engines = {"tavily": lambda q: []}  # content provided via fake_parallel_search
        result = mod.collect(
            "test query",
            _DUMMY_CACHE,
            engines=engines,
            source_cap=5,
            top_k=5,
        )

        fetched = [r for r in result if r.get("fetched")]
        assert len(fetched) >= 2, f"Expected multiple fetched sources, got {len(fetched)}"

        # Verify required keys are present on fetched results
        for item in fetched:
            assert "url" in item
            assert "fetched" in item
            assert item["fetched"] is True
            assert "text" in item
            assert "source_mode" in item
            assert "fetched_at" in item
            assert "content_hash" in item


class TestFetchBudgetCapsTotalFetches:
    """Fetch budget must be respected across multiple collect() calls in the closure."""

    def test_fetch_budget_caps_total_fetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Total fetches across closure calls must not exceed fetch_budget_per_run."""
        from mingjing.graph import make_default_collect_fn

        settings = _make_settings(fetch_budget_per_run=3, depth="quick")

        # Many previews to ensure budget is the binding constraint
        previews = _make_previews(10)

        def fake_parallel_search(
            queries: list[str],
            engines: dict[str, Any],
            *,
            workers: int = 4,
        ) -> list[dict[str, Any]]:
            return previews

        fetch_call_count: list[int] = [0]

        def fake_fetch(url: str, cache: Any, timeout: float = 8.0, mode: str = "live_first", **kw: Any) -> Any:
            fetch_call_count[0] += 1
            return _make_fetch_result(url=url, text="x" * 200)

        def fake_robots_allowed(url: str, fetch_robots: Any) -> bool:
            return True

        monkeypatch.setattr("mingjing.agents.collector.parallel_search", fake_parallel_search)
        monkeypatch.setattr("mingjing.agents.collector.fetch_with_fallback", fake_fetch)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", fake_robots_allowed)

        collect_fn = make_default_collect_fn(settings)

        # Call the closure multiple times — total fetches must not exceed budget
        collect_fn("query one", cache=_DUMMY_CACHE, source_cap=5)
        collect_fn("query two", cache=_DUMMY_CACHE, source_cap=5)
        collect_fn("query three", cache=_DUMMY_CACHE, source_cap=5)

        assert fetch_call_count[0] <= settings.fetch_budget_per_run, (
            f"Expected at most {settings.fetch_budget_per_run} fetches, "
            f"got {fetch_call_count[0]}"
        )


class TestMakeDefaultCollectFnHasLegacyContract:
    """The collect_fn returned by make_default_collect_fn must have the correct contract."""

    def test_make_default_collect_fn_has_legacy_contract(self) -> None:
        """make_default_collect_fn returns a callable with (query, *, cache, source_cap, mode=...)."""
        from mingjing.graph import make_default_collect_fn

        settings = _make_settings()
        fn = make_default_collect_fn(settings)

        assert callable(fn), "make_default_collect_fn must return a callable"

        sig = inspect.signature(fn)
        params = sig.parameters

        # Must have 'query' as first positional param
        param_names = list(params.keys())
        assert param_names[0] == "query", f"First param must be 'query', got {param_names[0]}"

        # Must have keyword-only params: cache, source_cap, mode
        for name in ("cache", "source_cap", "mode"):
            assert name in params, f"Missing required param '{name}' in collect_fn signature"
            assert params[name].kind in (
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ), f"Param '{name}' must be keyword-only or positional-or-keyword"

        # mode must have a default
        assert params["mode"].default != inspect.Parameter.empty, "mode must have a default value"


class TestClosureBuilds4TierEnginesForDetailedDepth:
    """For depth='detailed', the engines dict must have all 4 configured engines."""

    def test_closure_builds_tier_engines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """For settings.depth='detailed', engines dict has the 4 tier engines."""
        from mingjing.graph import make_default_collect_fn

        settings = _make_settings(depth="detailed", fetch_budget_per_run=100)

        captured_engines: list[dict[str, Any]] = []

        def fake_parallel_search(
            queries: list[str],
            engines: dict[str, Any],
            *,
            workers: int = 4,
        ) -> list[dict[str, Any]]:
            captured_engines.append(dict(engines))
            return []

        def fake_robots_allowed(url: str, fetch_robots: Any) -> bool:
            return True

        monkeypatch.setattr("mingjing.agents.collector.parallel_search", fake_parallel_search)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", fake_robots_allowed)

        collect_fn = make_default_collect_fn(settings)
        collect_fn("test query", cache=_DUMMY_CACHE, source_cap=3)

        assert len(captured_engines) > 0, "parallel_search was never called"
        engine_keys = set(captured_engines[0].keys())

        # "detailed" tier has: tavily, brave, duckduckgo, searxng
        # searxng is skipped if no SEARXNG_URL; test tavily+brave+duckduckgo always present
        expected_always = {"tavily", "brave", "duckduckgo"}
        assert expected_always.issubset(engine_keys), (
            f"Expected engines {expected_always} in {engine_keys}"
        )


# ---------------------------------------------------------------------------
# Part C test — runner.py wiring
# ---------------------------------------------------------------------------


class TestRunnerInjectsClosureWhenNoCollectFnProvided:
    """runner.py must inject make_default_collect_fn(settings) when no collect_fn is given."""

    def test_runner_uses_closure_when_no_collect_fn_injected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GraphDeps.collect_fn is the closure when the caller does not inject collect_fn."""
        from mingjing import runner as runner_mod
        from mingjing.graph import _default_collect_fn

        settings = _make_settings()

        captured_deps: list[Any] = []

        def fake_build_graph(deps: Any = None) -> Any:
            captured_deps.append(deps)
            # Return a minimal runnable stub
            stub = MagicMock()
            stub.invoke.return_value = {"phase": "write", "verdict": "pass"}
            return stub

        # Patch build_graph in the runner's import namespace
        monkeypatch.setattr("mingjing.runner.build_graph", fake_build_graph, raising=False)

        # Also patch the local import inside run() — the runner does
        # ``from .graph import GraphDeps, build_graph`` inside the function
        import mingjing.graph as graph_mod

        original_build = graph_mod.build_graph
        graph_mod.build_graph = fake_build_graph

        db = MagicMock()
        db.get_run.return_value = {
            "competitors": ["TestCo"],
            "category": "saas",
            "goal": "test",
            "domain": None,
        }
        db.insert_trace_event.return_value = None
        db.set_run_status.return_value = None

        fake_cache = MagicMock()
        fake_cache.__enter__ = lambda s: s
        fake_cache.__exit__ = MagicMock(return_value=False)
        fake_cache.get.return_value = None

        try:
            with (
                patch("mingjing.collector.cache.Cache", return_value=fake_cache),
                patch("mingjing.runner._prewarm_best_effort"),
                patch("mingjing.runner._seed_survey_lane_best_effort", return_value=[]),
            ):
                executor = runner_mod.make_run_executor(
                    get_db=lambda: db,
                    settings=settings,
                    # No collect_fn injected
                    prewarm=False,
                )
                executor("run-123")
        finally:
            graph_mod.build_graph = original_build

        assert len(captured_deps) > 0, "build_graph was not called"
        deps = captured_deps[0]
        assert deps is not None

        # The collect_fn must NOT be the bare legacy _default_collect_fn;
        # it should be the settings-closure (a distinct object).
        assert deps.collect_fn is not _default_collect_fn, (
            "runner must inject the settings closure, not the bare legacy _default_collect_fn"
        )
        assert callable(deps.collect_fn)

    def test_runner_preserves_injected_collect_fn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When a collect_fn is injected, runner must pass it through unchanged."""
        from mingjing import runner as runner_mod

        settings = _make_settings()

        captured_deps: list[Any] = []

        def fake_build_graph(deps: Any = None) -> Any:
            captured_deps.append(deps)
            stub = MagicMock()
            stub.invoke.return_value = {"phase": "write", "verdict": "pass"}
            return stub

        import mingjing.graph as graph_mod

        original_build = graph_mod.build_graph
        graph_mod.build_graph = fake_build_graph

        my_collect_fn = MagicMock(return_value=[])

        db = MagicMock()
        db.get_run.return_value = {
            "competitors": ["TestCo"],
            "category": "saas",
            "goal": "test",
            "domain": None,
        }
        db.insert_trace_event.return_value = None
        db.set_run_status.return_value = None

        fake_cache = MagicMock()
        fake_cache.__enter__ = lambda s: s
        fake_cache.__exit__ = MagicMock(return_value=False)
        fake_cache.get.return_value = None

        try:
            with (
                patch("mingjing.collector.cache.Cache", return_value=fake_cache),
                patch("mingjing.runner._prewarm_best_effort"),
                patch("mingjing.runner._seed_survey_lane_best_effort", return_value=[]),
            ):
                executor = runner_mod.make_run_executor(
                    get_db=lambda: db,
                    settings=settings,
                    collect_fn=my_collect_fn,
                    prewarm=False,
                )
                executor("run-456")
        finally:
            graph_mod.build_graph = original_build

        assert len(captured_deps) > 0
        deps = captured_deps[0]
        assert deps.collect_fn is my_collect_fn, (
            "Injected collect_fn must be preserved, not replaced by closure"
        )


# ---------------------------------------------------------------------------
# Snippet-as-evidence: candidates beyond the fetch cap become evidence via
# their search snippet (no fetch) — breadth without fetch-budget cost.
# ---------------------------------------------------------------------------


class TestSnippetAsEvidence:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, n_domains: int):
        import mingjing.agents.collector as mod

        previews = _make_previews(n_domains)
        fetch_calls: list[str] = []

        def fake_parallel_search(queries, engines, *, workers=4):  # type: ignore[no-untyped-def]
            return previews

        def fake_fetch(url, cache, timeout=8.0, mode="live_first", **kw):  # type: ignore[no-untyped-def]
            fetch_calls.append(url)
            return _make_fetch_result(url=url, text=f"Full content for {url}")

        monkeypatch.setattr("mingjing.agents.collector.parallel_search", fake_parallel_search)
        monkeypatch.setattr("mingjing.agents.collector.fetch_with_fallback", fake_fetch)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", lambda u, f: True)
        return mod, fetch_calls

    def test_snippets_added_beyond_fetch_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch_cap=source_cap full fetches; the rest of top_k become snippet rows."""
        mod, fetch_calls = self._setup(monkeypatch, n_domains=6)

        result = mod.collect(
            "q", _DUMMY_CACHE,
            engines={"e": lambda q: []},
            source_cap=2,   # fetch cap
            top_k=6,        # candidate/snippet pool
            include_snippets=True,
        )

        fetched = [r for r in result if r.get("fetched") and not r.get("from_snippet")]
        snippets = [r for r in result if r.get("from_snippet")]
        assert len(fetched) == 2, "only source_cap full fetches"
        assert len(fetch_calls) == 2, "snippets must NOT trigger a fetch"
        assert len(snippets) == 4, "remaining candidates become snippet evidence"
        for s in snippets:
            assert s["fetched"] is True
            assert s["source_mode"] == "SNIPPET"
            assert s["text"], "snippet text present"
            assert s["fetched_at"] is None
            assert s["content_hash"]

    def test_disabled_by_default_means_no_snippets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without include_snippets, only the fetched (source_cap) sources appear."""
        mod, fetch_calls = self._setup(monkeypatch, n_domains=6)

        result = mod.collect(
            "q", _DUMMY_CACHE,
            engines={"e": lambda q: []},
            source_cap=2,
            top_k=6,
        )

        assert [r for r in result if r.get("from_snippet")] == []
        assert len([r for r in result if r.get("fetched")]) == 2

    def test_empty_snippet_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A candidate with no snippet text produces no snippet row (no empty evidence)."""
        import mingjing.agents.collector as mod

        previews = [
            {"url": "https://a.com/p", "title": "A", "snippet": "real snippet", "engine": "e"},
            {"url": "https://b.com/p", "title": "B", "snippet": "", "engine": "e"},
        ]
        monkeypatch.setattr("mingjing.agents.collector.parallel_search", lambda *a, **k: previews)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", lambda u, f: True)

        result = mod.collect(
            "q", _DUMMY_CACHE,
            engines={"e": lambda q: []},
            source_cap=0,   # fetch nothing → both candidates go to snippet branch
            top_k=2,
            include_snippets=True,
        )
        snippets = [r for r in result if r.get("from_snippet")]
        assert len(snippets) == 1, "only the candidate with a non-empty snippet becomes evidence"
        assert snippets[0]["url"] == "https://a.com/p"

    def test_failed_fetches_do_not_exceed_fetch_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: a run of FAILING fetches must not attempt (and bill) more
        than fetch_cap. The cap bounds attempts, not just successes."""
        import mingjing.agents.collector as mod

        previews = _make_previews(8)  # 8 candidates, far more than the fetch cap
        fetch_calls: list[str] = []

        def always_fail(url, cache, timeout=8.0, mode="live_first", **kw):  # type: ignore[no-untyped-def]
            fetch_calls.append(url)
            raise LookupError("fetch failed")

        monkeypatch.setattr("mingjing.agents.collector.parallel_search", lambda *a, **k: previews)
        monkeypatch.setattr("mingjing.agents.collector.fetch_with_fallback", always_fail)
        monkeypatch.setattr("mingjing.agents.collector.robots.is_allowed", lambda u, f: True)

        result = mod.collect(
            "q", _DUMMY_CACHE,
            engines={"e": lambda q: []},
            source_cap=2,   # fetch cap = 2
            top_k=8,        # large candidate pool
            include_snippets=True,
        )

        # Only fetch_cap ATTEMPTS, even though all fail and 8 candidates exist.
        assert len(fetch_calls) == 2, f"attempts must be capped at 2, got {len(fetch_calls)}"
        # The remaining candidates still become snippet evidence (breadth preserved).
        assert len([r for r in result if r.get("from_snippet")]) >= 1
