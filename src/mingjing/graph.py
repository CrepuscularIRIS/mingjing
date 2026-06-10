"""LangGraph wiring the evidence-runtime loop (plan Task 10 + Task 15b).

The graph models ``intake -> plan -> collect -> analyze -> qa -> route -> revise
-> write``. ``route`` is a conditional edge driven by the pure
:func:`mingjing.qa.route.route` decision: a passing run goes straight to
``write``; a reject within the round/budget cap goes back to ``collect`` or
``analyze`` via ``revise``; a reject at the cap (or out of budget) degrades to a
partial ``write``.

``RunState`` is field-keyed and append-only: list-valued fields (``tasks``,
``sources``, ``claims``, ``qc_reports``) use additive reducers so concurrent
nodes never clobber a shared mutable god-object — each node returns only the
delta it produced. Scalars (``revision_round``, ``phase``, ``budget_calls``) are
last-write-wins.

Two build modes (Task 15b):
- ``build_graph()`` / ``build_graph(deps=None)`` — the compile-only skeleton
  used by the build/route tests. Nodes only stamp a ``phase`` and emit a trace
  event; no agent, network, or LLM is touched.
- ``build_graph(deps=GraphDeps(...))`` — the live loop. Node functions CLOSE
  OVER ``deps`` (the agents, cache, settings) so the graph state stays
  field-keyed/serializable while the agents are dependency-injected for
  testability. The honest weak->strong self-correction lives in ``collect``: the
  per-field source cap GROWS with the revision round, so a later round performs a
  *real additional fetch* rather than withholding data.
"""

import logging
import operator
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import graph_nodes
from .agents import analyst as analyst_agent
from .agents import collector as collector_agent
from .qa.route import route as route_decision
from .trace import node_trace

_log = logging.getLogger(__name__)

# Defensive super-step ceiling for the live graph (see build_graph). The pure
# router (qa/route.py) terminates the revise loop far below this; it is only a
# backstop against a wiring bug spinning forever. Sized above the measured
# worst-case legitimate run (18 super-steps at revise_round_cap=2) with margin.
_GRAPH_RECURSION_LIMIT = 40


def _strip_reasoning(text: str) -> str:
    """Return only the final answer from a reasoning-model reply.

    MiniMax-M2.7 / Doubao emit ``<think>...</think>`` reasoning before the answer.
    For plain-text expansion we want ONLY the post-reasoning answer:

    - text after the LAST ``</think>`` (drops the reasoning, which may itself
      contain example queries that would otherwise pollute the result), or
    - ``""`` when a ``<think>`` block is present but never closed (the reply was
      truncated mid-reasoning and no answer was emitted) — the caller then falls
      back to the base query instead of searching reasoning fragments.
    """
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    if "<think>" in text:
        return ""
    return text.strip()


class RunState(TypedDict, total=False):
    """Field-keyed, append-only run state threaded through the graph.

    List fields use additive reducers (append-only); scalar fields are
    last-write-wins. ``db`` is an optional carrier so nodes can emit trace
    events without making the graph un-buildable when absent.
    """

    run_id: str
    intake: dict[str, Any]
    tasks: Annotated[list[dict[str, Any]], operator.add]
    sources: Annotated[list[dict[str, Any]], operator.add]
    claims: Annotated[list[dict[str, Any]], operator.add]
    qc_reports: Annotated[list[dict[str, Any]], operator.add]
    revision_round: int
    phase: str
    budget_calls: int
    budget_max: int
    # Carriers (not domain state): present only at runtime.
    db: Any
    verdict: str
    assignee: str
    budget_ok: bool
    cap: int
    report: str


def _default_collect_fn(
    query: str,
    *,
    cache: Any,
    source_cap: int,
    mode: str = "live_first",
) -> list[dict[str, Any]]:
    """Production collect wrapper: adapt the loop's call shape to ``collector.collect``."""
    return collector_agent.collect(
        query, cache, source_cap=source_cap, mode=mode
    )


def make_default_collect_fn(settings: Any) -> Callable[..., list[dict[str, Any]]]:
    """Build a settings-aware collect closure with the EXACT graph contract.

    The returned callable has the contract::

        (query: str, *, cache, source_cap: int, mode: str = "live_first") -> list[dict]

    This matches what ``graph_nodes.collect_node`` calls via ``deps.collect_fn``.
    Settings reach production via CLOSURE (not an extra kwarg) so the call site
    is never changed — all offline test fakes already use this exact signature.

    Fetch-budget tracking:
        A ``{"used": 0}`` dict is captured in the closure. Each call to the
        returned collect_fn deducts from the budget. When the budget is exhausted,
        a warning is logged and collect returns an empty list for that call.
        NOTE: the collect_fn has no db handle (the contract does not carry one),
        so the budget-exhaustion event is emitted to the logger ONLY — it is NOT
        written to the trace_events table. This is a known limitation documented
        here; changing the contract to thread a db handle would break every
        offline fake.

    Args:
        settings: A :class:`~mingjing.config.Settings` instance.

    Returns:
        A closure with the standard collect_fn contract.
    """
    from .collector.firecrawl_fetch import make_firecrawl_fn
    from .collector.query_expansion import expand_queries
    from .collector.search import bind_provider
    from .config import tier_for

    tier = tier_for(settings.depth)

    # ------------------------------------------------------------------
    # Build the engines dict via bind_provider.
    # NOTE: env keys TAVILY_API_KEY, BRAVE_API_KEY, MINGJING_SEARXNG_URL
    # are read HERE at closure-BUILD time — tests must set them BEFORE
    # calling make_default_collect_fn, not before individual collect calls.
    # ------------------------------------------------------------------
    engines: dict[str, Callable[[str], list[dict[str, Any]]]] = {}
    for name in tier.engines:
        bound = bind_provider(
            name,
            top_k=tier.top_k,
            tavily_key=os.environ.get("TAVILY_API_KEY", ""),
            brave_key=os.environ.get("BRAVE_API_KEY", ""),
            bocha_key=os.environ.get("BOCHA_API_KEY", ""),
            searxng_url=os.environ.get("MINGJING_SEARXNG_URL", ""),
        )
        if bound is None:
            if name in ("tavily", "brave", "bocha", "duckduckgo", "searxng"):
                # bind_provider returned None → engine unavailable (e.g. searxng without url)
                _log.debug(
                    "make_default_collect_fn: engine %r unavailable (missing url/key), skipping",
                    name,
                )
            else:
                _log.warning("make_default_collect_fn: unknown engine %r, skipping", name)
            continue
        engines[name] = bound

    # ------------------------------------------------------------------
    # Build the Firecrawl callable (None when key is empty — disabled).
    # ------------------------------------------------------------------
    firecrawl: Callable[[str], Any] | None = None
    if settings.firecrawl_api_key:
        firecrawl = make_firecrawl_fn(
            api_key=settings.firecrawl_api_key,
            base_url=settings.firecrawl_base_url,
        )

    # ------------------------------------------------------------------
    # Build a thin LLM adapter for query expansion.
    # Wraps call_llm so any failure falls back gracefully (expand_queries
    # already catches LLM exceptions and returns [base_query]).
    # ------------------------------------------------------------------
    def _llm_adapter(prompt: str) -> str:
        """Thin adapter: plain-text prompt → plain-text reply (no schema parse)."""
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=settings.minimax_base_url,
                api_key=settings.minimax_api_key,
            )
            max_tokens = getattr(settings, "llm_max_tokens", 8000) or 8000
            resp = client.chat.completions.create(
                model=settings.minimax_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return _strip_reasoning(resp.choices[0].message.content or "")
        except Exception:
            _log.warning(
                "make_default_collect_fn: LLM adapter call failed; "
                "query expansion will fall back to base_query",
                exc_info=True,
            )
            raise  # let expand_queries handle it

    # In-memory cache for query expansion (shared within this closure).
    _expand_cache: dict[Any, list[str]] = {}

    def _make_expand(n: int) -> Callable[[str], list[str]]:
        """Return an expansion callable for *n* sub-queries."""
        def _expand(base_query: str) -> list[str]:
            return expand_queries(
                competitor="",
                field="",
                base_query=base_query,
                n=n,
                llm=_llm_adapter,
                cache=_expand_cache,
                run_id="",
            )
        return _expand

    expand_fn = _make_expand(tier.sub_queries)

    # ------------------------------------------------------------------
    # Fetch budget counter captured in the closure (shared across calls).
    # ------------------------------------------------------------------
    budget = {"used": 0, "limit": settings.fetch_budget_per_run}

    # ------------------------------------------------------------------
    # The actual collect_fn closure — contract is EXACTLY:
    #   (query, *, cache, source_cap, mode="live_first") -> list[dict]
    # ------------------------------------------------------------------
    def _collect_fn(
        query: str,
        *,
        cache: Any,
        source_cap: int,
        mode: str = "live_first",
    ) -> list[dict[str, Any]]:
        remaining = budget["limit"] - budget["used"]
        if remaining <= 0:
            _log.warning(
                "deep-collect fetch budget exhausted (%d); skipping collect for query %r",
                budget["limit"],
                query,
            )
            return []

        # Decouple the two caps:
        #   - fetch_cap: expensive full-page fetches, bounded by the round-aware
        #     source_cap AND the remaining run fetch budget.
        #   - top_k: the cheap candidate/snippet pool (full tier breadth), so
        #     snippet-as-evidence adds coverage without consuming fetch budget.
        fetch_cap = min(source_cap, remaining)

        result = collector_agent.collect(
            query,
            cache,
            source_cap=fetch_cap,
            mode=mode,
            engines=engines,
            top_k=tier.top_k,
            workers=settings.deep_collect_workers,
            firecrawl=firecrawl,
            min_chars=settings.min_source_chars,
            expand=expand_fn,
            include_snippets=True,
        )

        # Count only real full-page fetch attempts against the budget. Snippet
        # evidence (from_snippet=True) performs no fetch and is therefore free.
        fetch_attempts = sum(
            1
            for r in result
            if (r.get("fetched") and not r.get("from_snippet"))
            or r.get("reason") == "fetch_failed"
        )
        budget["used"] += fetch_attempts

        return result

    return _collect_fn


@dataclass(frozen=True)
class GraphDeps:
    """Injectable dependencies for the live graph.

    All fields carry real defaults so production code calls the real agents; the
    offline smoke gate injects deterministic fakes. Callables are CLOSED OVER by
    the node functions — they are never stored in ``RunState`` (which stays
    serializable).
    """

    db: Any
    cache: Any = None
    settings: Any = None
    collect_fn: Callable[..., list[dict[str, Any]]] = field(default=_default_collect_fn)
    analyze_fn: Callable[..., dict[str, Any]] = field(default=analyst_agent.analyze_field)


# ---------------------------------------------------------------------------
# Skeleton nodes (compile-only build path; defaults for build_graph()).
# These remain importable for the existing build/route tests and are the
# fallback behavior when no GraphDeps are injected.
# ---------------------------------------------------------------------------


def intake_node(state: RunState) -> dict[str, Any]:
    """Record the run request and seed the loop counters.

    Seeds ``cap`` (max revision rounds), ``budget_max`` (max LLM/fetch calls),
    and ``budget_ok`` (always ``True`` at intake — budget is checked per-route).
    Loading settings is guarded with a try/except so the graph compiles and
    runs in the build/test path without a valid environment. A ``ValueError``
    from ``Settings.load`` (rate limiting disabled) is a fail-fast invariant and
    is NOT swallowed.
    """
    node_trace(state, "intake")
    cap = 2          # fallback only — mirrors MINGJING_REVISE_CAP default in config.py
    budget_max = 40  # fallback only — mirrors MINGJING_BUDGET_CALLS default in config.py
    try:
        from .config import Settings

        settings = Settings.load()
        cap = settings.revise_round_cap
        budget_max = settings.budget_calls_max
    except (ImportError, OSError):
        pass  # build/test path without a valid environment
    return {
        "phase": "intake",
        "revision_round": 0,
        "budget_calls": 0,
        "cap": cap,
        "budget_max": budget_max,
        "budget_ok": True,
    }


def plan_node(state: RunState) -> dict[str, Any]:
    """Expand the intake into per-field research tasks (skeleton)."""
    node_trace(state, "plan")
    return {"phase": "plan"}


def collect_node(state: RunState) -> dict[str, Any]:
    """Collector: search -> robots -> fetch -> evidence (skeleton)."""
    node_trace(state, "collect", agent="collector")
    return {"phase": "collect", "budget_calls": state.get("budget_calls", 0) + 1}


def analyze_node(state: RunState) -> dict[str, Any]:
    """Analyst: one claim per field from collected evidence (skeleton)."""
    node_trace(state, "analyze", agent="analyst")
    return {"phase": "analyze", "budget_calls": state.get("budget_calls", 0) + 1}


def qa_node(state: RunState) -> dict[str, Any]:
    """QA: run verifier rules, emit a verdict + assignee (skeleton)."""
    node_trace(state, "qa", agent="qa")
    return {"phase": "qa"}


def route_node(state: RunState) -> dict[str, Any]:
    """Compute ``budget_ok`` from live call count and land for the conditional router.

    ``budget_ok`` is recomputed here (rather than at intake) so every iteration
    of the loop reflects the current spend before ``_route_branch`` is evaluated.
    """
    node_trace(state, "route")
    budget_calls = state.get("budget_calls", 0)
    budget_max = state.get("budget_max", 40)
    budget_ok = budget_calls < budget_max
    return {"phase": "route", "budget_ok": budget_ok}


def revise_node(state: RunState) -> dict[str, Any]:
    """Apply open RevisionTasks and advance the revision round.

    Unchanged across both build modes: the assignee edge (set in ``qa_node``)
    routes the next iteration to ``collect`` or ``analyze``. Because the collect
    cap grows with the round, the next collect fetches MORE — the honest
    weak->strong mechanism.

    Emits ``revise_start`` (with the claim targeted by the first open revision
    task) so the frontend's self-correction cue lights up. ``revise_done`` is
    emitted at the start of the subsequent QA node (round > 0 path).
    """
    from .trace_events import emit_revise_start

    node_trace(state, "revise")
    db = state.get("db")
    run_id = state.get("run_id")
    round_idx = state.get("revision_round", 0)
    assignee = state.get("assignee")
    # Pull the claim_id from the first open QC report so the frontend can show
    # which specific claim triggered this revision.
    claim_id = None
    for report in state.get("qc_reports", []):
        if isinstance(report, dict) and report.get("claim_id"):
            claim_id = report["claim_id"]
            break
    emit_revise_start(
        db, run_id,
        assignee=assignee, round_idx=round_idx + 1, claim_id=claim_id,
    )
    return {"phase": "revise", "revision_round": round_idx + 1}


def write_node(state: RunState) -> dict[str, Any]:
    """Writer: pure projection of QA-passed claims into the report (skeleton)."""
    node_trace(state, "write", agent="writer")
    return {"phase": "write"}


def _route_branch(state: RunState) -> str:
    """Conditional edge: map the pure router decision to a graph target.

    ``write`` / ``write_partial`` both terminate at the writer; ``collect`` and
    ``analyze`` re-enter the loop through ``revise``.
    """
    decision = route_decision(
        verdict=state.get("verdict", "pass"),
        round=state.get("revision_round", 0),
        cap=state.get("cap", 2),
        budget_ok=state.get("budget_ok", True),
        assignee=state.get("assignee"),
    )
    if decision in ("write", "write_partial"):
        return "write"
    return "revise"


def build_graph(deps: GraphDeps | None = None) -> Any:
    """Build and compile the LangGraph StateGraph.

    Args:
        deps: When ``None`` (default), build the compile-only skeleton (no agents,
            no network/LLM) used by the build/route tests. When provided, wire the
            live nodes that close over ``deps`` and call the real (or injected)
            agents.

    Returns:
        A compiled LangGraph runnable.
    """
    synthesis = None
    if deps is None:
        plan = plan_node
        collect = collect_node
        analyze = analyze_node
        qa = qa_node
        write = write_node
    else:
        plan = graph_nodes.live_plan_node
        collect = graph_nodes.make_collect_node(deps)
        analyze = graph_nodes.make_analyze_node(deps)
        qa = graph_nodes.make_qa_node(deps)
        write = graph_nodes.make_write_node(deps)
        synthesis = graph_nodes.make_synthesis_node(deps)

    g: StateGraph = StateGraph(RunState)

    g.add_node("intake", intake_node)
    g.add_node("plan", plan)
    g.add_node("collect", collect)
    g.add_node("analyze", analyze)
    g.add_node("qa", qa)
    g.add_node("route", route_node)
    g.add_node("revise", revise_node)
    g.add_node("write", write)

    g.add_edge(START, "intake")
    g.add_edge("intake", "plan")
    g.add_edge("plan", "collect")
    g.add_edge("collect", "analyze")
    g.add_edge("analyze", "qa")
    g.add_edge("qa", "route")
    # route branches: terminate at write, or loop back through revise.
    g.add_conditional_edges("route", _route_branch, {"write": "write", "revise": "revise"})
    # revise dispatches by assignee back into the loop.
    g.add_conditional_edges(
        "revise",
        lambda s: "analyze" if s.get("assignee") == "analyst" else "collect",
        {"collect": "collect", "analyze": "analyze"},
    )
    # The live graph runs a post-write synthesis pass (write -> synthesis -> END);
    # the compile-only skeleton has no deps/LLM, so it terminates at write.
    if synthesis is not None:
        g.add_node("synthesis", synthesis)
        g.add_edge("write", "synthesis")
        g.add_edge("synthesis", END)
    else:
        g.add_edge("write", END)

    compiled = g.compile()
    # Termination of the revise loop is guaranteed by the pure router
    # (``qa/route.py``: revise_round_cap + budget gate). This explicit
    # recursion_limit is only a DEFENSIVE ceiling so a wiring bug can never
    # spin forever; the router stops the loop well before it is reached.
    #
    # Sizing: LangGraph counts each node execution as one super-step. A
    # legitimate full run is base(6: intake,plan,collect,analyze,qa,route) +
    # revise_round_cap × 5(revise,collect,analyze,qa,route) + 2(write,synthesis)
    # = 18 super-steps at the default cap of 2 (measured). _GRAPH_RECURSION_LIMIT
    # sits comfortably above that worst case (margin for a higher cap / future
    # nodes) while still being a hard runaway ceiling. The router never reaches
    # it on any legitimate path.
    #
    # ``with_config`` returns the same CompiledStateGraph type, so existing
    # callers/tests (``.invoke`` / ``.get_graph``) are unaffected. We apply it
    # only to the live (deps-backed) path; the compile-only skeleton stays bare.
    if deps is not None:
        return compiled.with_config(recursion_limit=_GRAPH_RECURSION_LIMIT)
    return compiled
