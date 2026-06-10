# 2026-06-01 — Research Breadth & Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the prioritized 2026-06-01 TODO items into shipped code — give MingJing real research **breadth** (revive the dead source cap, multi-query expansion, gap-driven iterative follow-up adapted from local-deep-research) and convert two built-but-invisible assets (per-run domain switch, ContradictionCard) into demo-visible points.

**Architecture:** Breadth is added at the collection layer without touching the QA/scoring/synthesis spine: (1) the live collect node consumes the real `per_field_source_cap`; (2) `build_query` becomes `build_field_queries` returning 2–4 schema/source-type-grounded variants per (competitor×field); (3) a new `gap_research` graph node, inserted `qa → gap_research → route`, re-searches on knowledge gaps (our QA codes + evidence-strength tiers, NOT LDR confidence decimals) independent of the QA verdict, looping back to analyze, bounded by a gap-round cap; (4) a `MINGJING_BREADTH=deep|fast` toggle scales caps. Visibility: `POST /runs` accepts a persisted `domain`; the frontend wires the existing `ContradictionCard` into the evidence/QA view.

**Tech Stack:** Python 3.12 + uv + pytest; LangGraph StateGraph (`graph.py`/`graph_nodes.py`); React 19 + Vite + TS + vitest. LLM = MiniMax (OpenAI-compatible) via `llm.call_llm`.

**Boundary (from `local-deep-research`):** We adapt LDR's query-decomposition prompts (`questions/decomposition_question.py`, `standard_question.py`) and its iterative-refinement loop structure + termination (`strategies/iterative_refinement_strategy.py`). We DO NOT import LDR's free-text synthesis (`citation_handler.py`, `report_generator.py`, `citation_handlers/*`) — our synthesis stays the deterministic claim-cited projection (`synthesis.project_synthesis`). The gap signal is our `IssueCode` + `evidence_strength` tiers + contradiction `stance`, never LDR's confidence floats.

**Scope:** This plan covers TODO **Breadth-0/1/2/3** + High-score **#1 (domain switch)** + **#2 (ContradictionCard)**. Deferred to a follow-on plan (not today): #3 KPI panel, #5 survey wiring, #6 docs sync, and the 🟢/⚪ items. The 🚫 guardrail list (concurrency, dynamic DAG, full Admiralty/propagation math, ACH, RAG) stays out.

---

## Verified code anchors (2026-06-01 exploration)

- `graph_nodes.py:106` — `source_cap = 1 + round_idx` (the dead-cap bug). Collect node calls `deps.collect_fn(task["query"], cache=deps.cache, source_cap=source_cap, mode=mode)`.
- `graph_nodes.py:50-69` — `FIELD_QUERY_TEMPLATES` dict + `build_query(competitor, field)`. `live_plan_node` (72-88) builds one task per (competitor×field) via a list comprehension.
- `graph.py:68-78` — `_default_collect_fn(query, *, cache, source_cap, mode)` → `collector.collect(query, cache, source_cap=, mode=)` (default `max_results=5`).
- `agents/collector.py:64-98` — `collect(query, cache, *, max_results=5, source_cap=3, timeout=8.0, mode, fetch_robots)`; breaks once `source_cap` fetched (line 98); `_search_fn(query, max_results=max_results)` at line 94.
- `config.py:22,49` — `per_field_source_cap` (env `MINGJING_SOURCE_CAP`, default 3) — **loaded, never used by the live node**. `budget_calls_max` (env `MINGJING_BUDGET_CALLS`, default 40). `revise_round_cap` (env `MINGJING_REVISE_CAP`, default 2).
- `graph.py:230-292` — `build_graph(deps)`; live wiring `plan→collect→analyze→qa→route→(write|revise)→[synthesis]`; `route` via `_route_branch`; `revise` dispatches `analyze` if `assignee=="analyst"` else `collect`.
- `qa/route.py:14-47` — `route(*, verdict, round, cap, budget_ok, assignee)`.
- `schemas.py:21-29` — `IssueCode` = SCHEMA_GAP / WEAK_EVIDENCE / CONTRADICTION / HALLUCINATED_SNIPPET / LOW_COVERAGE / VALUE_UNSUPPORTED.
- `db.py:296-304` — `latest_claims_for_run`; `db.py:155-164` — `create_run(*, category, competitors, goal)`; `db.py:323-353` — `flagged_claim_ids_last_round`.
- `schema_registry.py:141-177` — `resolve_active_schema()` reads `MINGJING_SCHEMA_DOMAIN` at import; `resolved_active_domain()`; `list_domains()`.
- `runner.py` — `make_run_executor(get_db, *, settings, collect_fn, analyze_fn, prewarm)` builds intake from `FIELD_SCHEMAS` and drives the graph.
- LDR: `questions/decomposition_question.py:107-125` (3–5 sub-queries prompt); `strategies/iterative_refinement_strategy.py:157-274` (while-loop: evaluate → gaps → refinement_query → merge; terminate on COMPLETE / confidence≥threshold / no-query / <2 new sources; `max_refinements=3`).

---

## File Structure

- Modify `src/mingjing/config.py` — add `breadth_mode` + `gap_round_cap`; raise budget default.
- Modify `src/mingjing/graph_nodes.py` — consume `per_field_source_cap` (Task 1); `build_field_queries` + multi-query plan node (Task 2); `make_gap_research_node` (Task 3).
- Modify `src/mingjing/graph.py` — pass `max_results` through `_default_collect_fn` (Task 1); wire `gap_research` node (Task 3).
- Modify `src/mingjing/runner.py` + `src/mingjing/api.py` + `src/mingjing/db.py` — per-run `domain` (Task 5).
- Modify frontend `views/EvidenceAndQA.tsx` (Task 6) + `App.tsx`/run form for domain dropdown (Task 5).
- Tests: `tests/test_breadth_cap.py`, `tests/test_field_queries.py`, `tests/test_gap_research.py`, `tests/test_breadth_toggle.py`, `tests/test_run_domain.py` (new); frontend `EvidenceAndQA.test.tsx`, run-form test.

---

## PART A — Research breadth (LDR-grounded)

### Task 1 (Breadth-0): Revive the dead `per_field_source_cap` + raise breadth budget

**Files:**
- Modify: `src/mingjing/graph_nodes.py:106`
- Modify: `src/mingjing/graph.py:68-78` (`_default_collect_fn`)
- Modify: `src/mingjing/config.py:52` (budget default)
- Test: `tests/test_breadth_cap.py`

- [ ] **Step 1: Write the failing test** — the live collect node requests `source_cap = per_field_source_cap + round_idx`, via a recording `collect_fn`.

```python
# tests/test_breadth_cap.py
from mingjing.config import Settings
from mingjing.graph_nodes import make_collect_node


def _settings(**over):
    base = dict(
        minimax_base_url="x", minimax_api_key="x", minimax_model="x", mode="live_first",
        rate_limiting_enabled=True, db_path=":memory:", cache_db_path=":memory:",
        per_field_source_cap=3, fetch_timeout_s=8.0, revise_round_cap=2,
        budget_calls_max=40, llm_max_tokens=8000,
    )
    base.update(over)
    return Settings(**base)


class _DepsStub:
    def __init__(self, settings, recorder):
        self.settings = settings
        self.cache = None
        self.collect_fn = recorder


def test_collect_uses_per_field_source_cap_plus_round(monkeypatch):
    seen = {}
    def recorder(query, *, cache, source_cap, mode):
        seen["source_cap"] = source_cap
        return []  # no fetched sources -> node just records the cap
    deps = _DepsStub(_settings(per_field_source_cap=3), recorder)
    node = make_collect_node(deps)
    # Minimal state: one task, round 0.
    class _DB:
        def append_source(self, *a, **k): ...
        def append_evidence_chunk(self, *a, **k): ...
    state = {"db": _DB(), "run_id": "r1", "revision_round": 0,
             "tasks": [{"competitor": "Acme", "field": "pricing_model", "query": "q"}]}
    node(state)
    assert seen["source_cap"] == 3  # per_field_source_cap(3) + round(0)
```

- [ ] **Step 2: Run — expect FAIL** (`assert 1 == 3`). `cd mingjing && uv run pytest tests/test_breadth_cap.py -v`

- [ ] **Step 3: Fix the cap in `graph_nodes.py`** (line 106). Replace:

```python
        source_cap = 1 + round_idx
```
with:
```python
        base_cap = (
            getattr(deps.settings, "per_field_source_cap", 1) if deps.settings else 1
        )
        source_cap = max(1, base_cap) + round_idx
```

- [ ] **Step 4: Raise search breadth in `_default_collect_fn`** (`graph.py:68-78`) so `collector.collect` actually fetches up to the cap — pass `max_results`:

```python
def _default_collect_fn(
    query: str,
    *,
    cache: Any,
    source_cap: int,
    mode: str = "live_first",
) -> list[dict[str, Any]]:
    """Production collect wrapper: adapt the loop's call shape to ``collector.collect``.

    ``max_results`` is widened to at least ~2× the source cap so the robots/fetch
    funnel has enough candidate hits to actually reach ``source_cap`` distinct
    fetched sources.
    """
    return collector_agent.collect(
        query, cache, max_results=max(5, source_cap * 2), source_cap=source_cap, mode=mode
    )
```

- [ ] **Step 5: Raise the call budget** so a wider corpus is not truncated. In `config.py:52` change the default from `"40"` to `"120"`:

```python
            budget_calls_max=int(os.environ.get("MINGJING_BUDGET_CALLS", "120")),
```

- [ ] **Step 6: Run — expect PASS**, then full suite. `uv run pytest tests/test_breadth_cap.py -v && uv run pytest -q` (must stay green).

- [ ] **Step 7: Commit**

```bash
git add mingjing/src/mingjing/graph_nodes.py mingjing/src/mingjing/graph.py mingjing/src/mingjing/config.py mingjing/tests/test_breadth_cap.py
git commit -m "feat(collect): consume per_field_source_cap + widen max_results & budget (Breadth-0)"
```

---

### Task 2 (Breadth-1): Multi-query expansion per (competitor × field), schema/source-type grounded

Adapt LDR's decomposition idea (`decomposition_question.py:107-125`, "3–5 specific sub-queries"), but make it **deterministic + schema-grounded**: each (competitor×field) yields 2–4 query variants, each aimed at a **source TYPE the Admiralty model values** for that field (official docs → reliability B, third-party reviews → C/D, news → C). This feeds evidence-strength grading, not just volume. No LLM call (deterministic = testable + demo-stable).

**Files:**
- Modify: `src/mingjing/graph_nodes.py:50-88`
- Test: `tests/test_field_queries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_field_queries.py
from mingjing.graph_nodes import build_field_queries, live_plan_node


def test_build_field_queries_returns_typed_variants():
    qs = build_field_queries("Notion", "pricing_model")
    assert 2 <= len(qs) <= 4
    # Each variant carries the query string + the source-type it targets.
    assert all("query" in v and "source_type" in v for v in qs)
    joined = " ".join(v["query"] for v in qs)
    assert "Notion" in joined
    # pricing should seek an official/pricing angle AND a third-party angle.
    types = {v["source_type"] for v in qs}
    assert "official" in types and ("review" in types or "news" in types)


def test_plan_node_expands_one_task_per_variant():
    state = {"intake": {"competitors": ["Notion"], "fields": ["pricing_model", "swot"]}}
    out = live_plan_node(state)
    tasks = out["tasks"]
    # >= 2 fields x >= 2 variants each.
    assert len(tasks) >= 4
    assert all({"field", "competitor", "query", "source_type"} <= set(t) for t in tasks)
    # Same (competitor, field) appears under multiple distinct queries.
    pricing = [t for t in tasks if t["field"] == "pricing_model"]
    assert len({t["query"] for t in pricing}) >= 2
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: build_field_queries`). `uv run pytest tests/test_field_queries.py -v`

- [ ] **Step 3: Implement `build_field_queries`** in `graph_nodes.py` (keep `build_query` for back-compat; add the multi-variant builder). Add a per-field variant table keyed by source type:

```python
# Per-field query variants, each tagged with the source TYPE it targets so the
# wider corpus feeds the Admiralty-inspired evidence-strength grading. Adapted
# from LDR's decomposition idea (decomposition_question.py) but deterministic
# and grounded in our competitive-analysis schema + source taxonomy.
FIELD_QUERY_VARIANTS: dict[str, list[tuple[str, str]]] = {
    "pricing_model": [
        ("official", "{competitor} official pricing plans per month"),
        ("review", "{competitor} pricing review value for money"),
        ("news", "{competitor} price change announcement"),
    ],
    "user_sentiment": [
        ("review", "{competitor} user reviews pros and cons"),
        ("review", "{competitor} complaints problems reddit"),
        ("news", "{competitor} user satisfaction report"),
    ],
    "feature_tree": [
        ("official", "{competitor} official features documentation"),
        ("review", "{competitor} feature comparison vs alternatives"),
    ],
    "user_persona": [
        ("official", "{competitor} who is it for target users"),
        ("review", "{competitor} best for which teams use cases"),
    ],
    "swot": [
        ("review", "{competitor} strengths and weaknesses analysis"),
        ("news", "{competitor} market position competitors threats"),
    ],
}


def build_field_queries(competitor: str, field: str) -> list[dict[str, str]]:
    """Return 2–4 source-type-tagged query variants for a (competitor, field).

    Falls back to a single generic variant for unknown fields so a custom domain
    schema still produces a query.
    """
    variants = FIELD_QUERY_VARIANTS.get(field)
    if not variants:
        return [{"query": build_query(competitor, field), "source_type": "web"}]
    return [
        {"query": tmpl.format(competitor=competitor).strip(), "source_type": stype}
        for stype, tmpl in variants
    ]
```

- [ ] **Step 4: Expand `live_plan_node`** to one task per variant (each task keeps `source_type` so downstream can prefer/annotate it):

```python
    tasks = [
        {"field": fld, "competitor": comp, "query": v["query"], "source_type": v["source_type"]}
        for comp in competitors
        for fld in fields
        for v in build_field_queries(comp, fld)
    ]
```

- [ ] **Step 5: Run — expect PASS**, then full suite. NOTE: the analyze node groups sources by `(competitor, field)` (`graph_nodes.py:200-203`) — multiple query-variant tasks for the same (competitor, field) all deposit sources under that pair, so analyze still produces ONE claim per field over the union of evidence. Confirm `test_fanout_smoke`/`test_pricing_path` still pass (more sources, same grouping). If a smoke test asserts an exact task count, update it to the new variant-expanded count with a one-line justification.

- [ ] **Step 6: Commit**

```bash
git add mingjing/src/mingjing/graph_nodes.py mingjing/tests/test_field_queries.py
git commit -m "feat(plan): multi-query expansion per field, source-type grounded (Breadth-1, LDR-adapted)"
```

---

### Task 3 (Breadth-2): Gap-driven iterative follow-up node (the differentiator)

A new `gap_research` node, wired `qa → gap_research → route`. **Independent of the QA verdict**, it re-searches on knowledge gaps and loops back to analyze, bounded by a gap-round cap. Adapts LDR's iterative-refinement loop (`iterative_refinement_strategy.py:157-274`: evaluate → identify gaps → follow-up query → merge → terminate), but the **gap signal is our QA codes + evidence-strength tiers**, the follow-up queries are **framed by the unproven sub-field + competitive intent**, and findings land as claim-cited evidence in the SAME analyze/qa flow (no LDR free-text synthesis).

**Files:**
- Modify: `src/mingjing/config.py` (add `gap_round_cap`)
- Create: `src/mingjing/gap_research.py` (pure gap detection + query generation)
- Modify: `src/mingjing/graph_nodes.py` (`make_gap_research_node`)
- Modify: `src/mingjing/graph.py` (wire `qa → gap_research → route`; conditional `gap_research → analyze | route`)
- Test: `tests/test_gap_research.py`

- [ ] **Step 1: Add `gap_round_cap` to Settings** (`config.py`): field `gap_round_cap: int` and in `load()`:

```python
            gap_round_cap=int(os.environ.get("MINGJING_GAP_ROUNDS", "1")),
```
(default 1 = one extra gap-driven research pass; `deep` mode raises it in Task 4.)

- [ ] **Step 2: Write the failing test for pure gap detection + query gen**

```python
# tests/test_gap_research.py
from mingjing.gap_research import detect_gap_fields, gap_followup_queries


def test_detect_gap_fields_flags_weak_missing_and_issue_fields():
    required = ["pricing_model", "user_sentiment", "feature_tree", "swot"]
    latest_claims = [
        {"schema_field": "pricing_model", "evidence_strength": "strong"},   # ok
        {"schema_field": "user_sentiment", "evidence_strength": "weak"},    # weak -> gap
        {"schema_field": "feature_tree", "evidence_strength": "moderate"},  # ok-ish, but has issue below
        # swot missing entirely -> gap
    ]
    issue_fields = {"feature_tree"}  # e.g. CONTRADICTION/LOW_COVERAGE still open
    gaps = detect_gap_fields(
        required_fields=required, latest_claims=latest_claims, issue_fields=issue_fields
    )
    assert set(gaps) == {"user_sentiment", "feature_tree", "swot"}
    assert "pricing_model" not in gaps  # strong + no issue -> not a gap


def test_gap_followup_queries_are_intent_framed_and_typed():
    qs = gap_followup_queries("Notion", "user_sentiment")
    assert qs and all("query" in q and "source_type" in q for q in qs)
    assert any("Notion" in q["query"] for q in qs)
```

- [ ] **Step 3: Run — expect FAIL** (`ImportError`). `uv run pytest tests/test_gap_research.py -v`

- [ ] **Step 4: Implement `gap_research.py`** (pure functions; the node wraps them):

```python
"""Gap-driven follow-up research — pure gap detection + query generation.

Adapts local-deep-research's iterative-refinement loop (re-search on what is
still unknown) but the GAP SIGNAL is our QA codes + evidence-strength tiers, not
LDR confidence floats, and follow-up queries are framed by the unproven
competitive-analysis sub-field. Findings flow back through the normal
analyze→qa path as claim-cited evidence; NO free-text LDR synthesis.
"""
from typing import Any

from .graph_nodes import build_field_queries

_OK_STRENGTHS = {"strong", "moderate"}


def detect_gap_fields(
    *,
    required_fields: list[str],
    latest_claims: list[dict[str, Any]],
    issue_fields: set[str],
) -> list[str]:
    """Return fields still needing more evidence: missing, weak-only, or flagged.

    A field is a gap when it has NO passing-strength claim (missing or weak) OR a
    QA issue is still open for it. Strong/moderate claims with no open issue are
    considered settled.
    """
    by_field: dict[str, str] = {}
    for c in latest_claims:
        f = c.get("schema_field")
        if f:
            by_field[f] = (c.get("evidence_strength") or "").lower()
    gaps: list[str] = []
    for f in required_fields:
        strength = by_field.get(f)
        if strength is None or strength not in _OK_STRENGTHS or f in issue_fields:
            gaps.append(f)
    return gaps


def gap_followup_queries(competitor: str, field: str) -> list[dict[str, str]]:
    """Generate follow-up queries for an unproven field (reuse the typed variants)."""
    return build_field_queries(competitor, field)
```

- [ ] **Step 5: Run — expect PASS.**

- [ ] **Step 6: Add `make_gap_research_node`** in `graph_nodes.py`. It reads the latest claims + last-round flagged claim ids, computes gap fields, and — if gaps remain AND `gap_round < gap_round_cap` AND budget remains — fetches follow-up sources for the gap fields (via `deps.collect_fn`), persists them exactly like the collect node, appends new `tasks`/`sources`, bumps a `gap_round`, and signals a re-analyze. Otherwise it passes through.

```python
def make_gap_research_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the gap-driven follow-up node (runs after qa, independent of verdict)."""

    def gap_research(state: "RunState") -> dict[str, Any]:
        node_trace(state, "gap_research", agent="collector")
        db = state["db"]
        run_id = state["run_id"]
        gap_round = state.get("gap_round", 0)
        gap_cap = getattr(deps.settings, "gap_round_cap", 0) if deps.settings else 0
        budget_calls = state.get("budget_calls", 0)
        budget_max = state.get("budget_max", 40)

        if gap_round >= gap_cap or budget_calls >= budget_max:
            return {"did_gap_research": False, "phase": "gap_research"}

        intake = state.get("intake", {}) or {}
        required = intake.get("fields", []) or []
        competitors = intake.get("competitors", []) or []
        latest = db.latest_claims_for_run(run_id)
        issue_fields = {
            c["schema_field"]
            for c in latest
            if c["id"] in db.flagged_claim_ids_last_round(run_id)
        }
        gaps = gap_research_mod.detect_gap_fields(
            required_fields=required, latest_claims=latest, issue_fields=issue_fields
        )
        if not gaps:
            return {"did_gap_research": False, "phase": "gap_research"}

        emit_gap_start(db, run_id, gap_fields=gaps, gap_round=gap_round)
        source_cap = (
            getattr(deps.settings, "per_field_source_cap", 1) if deps.settings else 1
        )
        new_sources: list[dict[str, Any]] = []
        new_tasks: list[dict[str, Any]] = []
        for comp in competitors:
            for field in gaps:
                for v in gap_research_mod.gap_followup_queries(comp, field):
                    new_tasks.append(
                        {"field": field, "competitor": comp,
                         "query": v["query"], "source_type": v["source_type"]}
                    )
                    results = deps.collect_fn(
                        v["query"], cache=deps.cache, source_cap=source_cap,
                        mode=getattr(deps.settings, "mode", "live_first"),
                    )
                    for res in results:
                        if not res.get("fetched"):
                            continue
                        sid = str(uuid.uuid4())
                        db.append_source({
                            "id": sid, "run_id": run_id, "url": res.get("url", ""),
                            "title": res.get("title"),
                            "source_type": claim_builder.infer_source_type(res.get("url", ""), comp),
                            "source_mode": res.get("source_mode"),
                            "fetched_at": res.get("fetched_at"),
                            "content_hash": res.get("content_hash"),
                            "raw_text": res.get("text", ""),
                        })
                        db.append_evidence_chunk({
                            "id": str(uuid.uuid4()), "run_id": run_id, "source_id": sid,
                            "locator": res.get("url", ""), "text": res.get("text", ""),
                            "content_hash": res.get("content_hash"),
                        })
                        new_sources.append({"source_id": sid, "field": field, "competitor": comp})
        emit_gap_done(db, run_id, sources_added=len(new_sources), gap_round=gap_round)
        return {
            "sources": new_sources,
            "tasks": new_tasks,
            "gap_round": gap_round + 1,
            "budget_calls": budget_calls + 1,
            "did_gap_research": bool(new_sources),
            "phase": "gap_research",
        }

    return gap_research
```

Add `import mingjing.gap_research as gap_research_mod` and `emit_gap_start`/`emit_gap_done` trace helpers (mirror `emit_collect_start`/`emit_collect_done` in `trace_events.py`, event types `gap_start`/`gap_done`). `RunState` (graph.py) gains `gap_round: int` and `did_gap_research: bool` (both `total=False`).

- [ ] **Step 7: Wire the node** in `graph.py` (live path only). Insert between qa and route:

```python
    g.add_node("gap_research", graph_nodes.make_gap_research_node(deps))  # live only
    # replace g.add_edge("qa", "route") with:
    g.add_edge("qa", "gap_research")
    g.add_conditional_edges(
        "gap_research",
        lambda s: "analyze" if s.get("did_gap_research") else "route",
        {"analyze": "analyze", "route": "route"},
    )
```
In the compile-only skeleton (`deps is None`), keep `qa → route` unchanged (no gap node), so the existing route/build tests are untouched.

- [ ] **Step 8: Integration test — gap loop fetches more evidence then settles.** Drive a run with a stub `collect_fn` that returns a strong source for a gap field on the gap pass, and a stub `analyze_fn`; assert: (a) `gap_research` ran and added sources, (b) the previously-weak field improved on the re-analyze, (c) the loop terminates within `gap_round_cap` (no infinite loop), (d) a `gap_start` trace event exists. Use the `make_run_executor(collect_fn=, analyze_fn=, settings=)` seam with `gap_round_cap=1`. (Pattern: mirror `tests/test_demo_feedback_loop.py`.)

- [ ] **Step 9: Run the full suite** `uv run pytest -q` (green). If a graph smoke test asserts the exact node set or `qa→route` adjacency, update it to include `gap_research` with a one-line justification.

- [ ] **Step 10: Commit**

```bash
git add mingjing/src/mingjing/gap_research.py mingjing/src/mingjing/graph_nodes.py mingjing/src/mingjing/graph.py mingjing/src/mingjing/config.py mingjing/src/mingjing/trace_events.py mingjing/tests/test_gap_research.py
git commit -m "feat(graph): gap-driven iterative follow-up node (Breadth-2, LDR-adapted, QA-code gap signal)"
```

---

### Task 4 (Breadth-3): `deep` vs `fast` breadth toggle

**Files:**
- Modify: `src/mingjing/config.py`
- Test: `tests/test_breadth_toggle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_breadth_toggle.py
import importlib
from mingjing import config


def _load(monkeypatch, mode):
    monkeypatch.setenv("MINGJING_BREADTH", mode)
    monkeypatch.delenv("MINGJING_SOURCE_CAP", raising=False)
    monkeypatch.delenv("MINGJING_GAP_ROUNDS", raising=False)
    monkeypatch.delenv("MINGJING_BUDGET_CALLS", raising=False)
    importlib.reload(config)
    return config.Settings.load()


def test_deep_mode_raises_caps(monkeypatch):
    deep = _load(monkeypatch, "deep")
    assert deep.per_field_source_cap >= 5
    assert deep.gap_round_cap >= 2


def test_fast_mode_is_lean(monkeypatch):
    fast = _load(monkeypatch, "fast")
    assert fast.per_field_source_cap <= 3
    assert fast.gap_round_cap <= 1
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/test_breadth_toggle.py -v`

- [ ] **Step 3: Implement the toggle** in `config.py` `load()` — `MINGJING_BREADTH` (default `fast`) sets the DEFAULTS for the three breadth knobs; explicit env vars still override:

```python
        breadth = os.environ.get("MINGJING_BREADTH", "fast").strip().lower()
        _deep = breadth == "deep"
        _src_default = "6" if _deep else "3"
        _gap_default = "2" if _deep else "1"
        _budget_default = "200" if _deep else "120"
        # ... in the Settings(...) construction:
            per_field_source_cap=int(os.environ.get("MINGJING_SOURCE_CAP", _src_default)),
            gap_round_cap=int(os.environ.get("MINGJING_GAP_ROUNDS", _gap_default)),
            budget_calls_max=int(os.environ.get("MINGJING_BUDGET_CALLS", _budget_default)),
            breadth_mode=breadth,
```
Add `breadth_mode: str` to the `Settings` dataclass.

- [ ] **Step 4: Run — expect PASS**, then full suite. Confirm determinism tests that build `Settings` directly (e.g. `test_breadth_cap.py`) are unaffected (they pass `per_field_source_cap` explicitly).

- [ ] **Step 5: Commit**

```bash
git add mingjing/src/mingjing/config.py mingjing/tests/test_breadth_toggle.py
git commit -m "feat(config): MINGJING_BREADTH deep|fast toggle scaling source cap / gap rounds / budget (Breadth-3)"
```

---

## PART B — Visibility wins

### Task 5 (#1): Per-run domain switch

`POST /runs` accepts an optional `domain`; it is persisted and the executor sets `MINGJING_SCHEMA_DOMAIN` for that run before resolving the schema; the frontend run form gets a domain dropdown (populated from `GET /schemas`).

**Files:**
- Modify: `src/mingjing/db.py` (persist `domain` on the run)
- Modify: `src/mingjing/api.py` (`CreateRunRequest.domain`; pass through)
- Modify: `src/mingjing/runner.py` (set `MINGJING_SCHEMA_DOMAIN` per run, build intake from that domain's schema)
- Modify: `frontend/src/App.tsx` (domain dropdown) + `api/client.ts` (`createRun` body)
- Test: `tests/test_run_domain.py`

- [ ] **Step 1: Write the failing test** — a run created with `domain="hr"` resolves the hr schema's fields for its intake.

```python
# tests/test_run_domain.py
from mingjing.runner import intake_fields_for_domain  # new helper


def test_intake_fields_follow_requested_domain():
    hr = set(intake_fields_for_domain("hr"))
    default = set(intake_fields_for_domain("default"))
    assert hr  # non-empty
    assert hr != default  # hr domain has different fields than default
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError`). `uv run pytest tests/test_run_domain.py -v`

- [ ] **Step 3: Add `intake_fields_for_domain`** in `runner.py` using the registry (does NOT depend on the import-time env):

```python
from .schema_registry import load_domain, resolved_active_domain

def intake_fields_for_domain(domain: str | None) -> list[str]:
    """Return the field list for ``domain`` (falls back to the active domain)."""
    name = domain or resolved_active_domain()
    try:
        return list(load_domain(name).keys())
    except ValueError:
        return list(load_domain(resolved_active_domain()).keys())
```

- [ ] **Step 4: Persist + thread `domain`.**
  - `db.py`: add a `domain` column to the `runs` table `_SCHEMA` (`domain TEXT`); extend `create_run(*, category, competitors, goal, domain=None)` to insert it; `get_run` already returns `*` so it surfaces.
  - `api.py`: add `domain: str | None = None` to `CreateRunRequest`; pass to `create_run`. Validate against `list_domains()` (400 on unknown).
  - `runner.py`: in the executor, read the run's `domain` (via `db.get_run`) and build intake from `intake_fields_for_domain(run_domain)` instead of the import-time `FIELD_SCHEMAS`. (The QA `required_fields` already come from intake, so the whole run follows the per-run domain.)

- [ ] **Step 5: Test the API path** — `tests/test_run_domain.py::test_create_run_persists_domain`: `POST /runs` with `domain="hr"` → the run row has `domain=="hr"`; unknown domain → 400.

- [ ] **Step 6: Frontend** — add a domain `<select>` to the run form in `App.tsx` (options from `getSchemas().domains`, default the active one), include `domain` in the `createRun` body (`api/client.ts` + `types.ts` `CreateRunBody.domain?`). Add an `App.test.tsx` assertion that the dropdown renders the domains and the selected value is sent. `npx tsc -b --noEmit` + `npm test` green.

- [ ] **Step 7: Run full backend + frontend suites; commit**

```bash
git add mingjing/src/mingjing/db.py mingjing/src/mingjing/api.py mingjing/src/mingjing/runner.py mingjing/tests/test_run_domain.py mingjing/frontend/src/App.tsx mingjing/frontend/src/App.test.tsx mingjing/frontend/src/api/client.ts mingjing/frontend/src/api/types.ts
git commit -m "feat(run): per-run domain selection (POST /runs domain + frontend dropdown) — extensibility demo (#1)"
```

---

### Task 6 (#2): Surface `ContradictionCard` in the evidence/QA view

The backend already emits contradiction meta (`supports_domains`/`refutes_domains` on the `CONTRADICTION` issue, propagated through `emit_qa_verdict`); the `ContradictionCard` component exists but is wired into no view. Render it in `EvidenceAndQA` when the active claim has a contradiction.

**Files:**
- Modify: `frontend/src/views/EvidenceAndQA.tsx`
- Test: `frontend/src/views/EvidenceAndQA.test.tsx`

- [ ] **Step 1: Write the failing test** — given trace events / QA data with a `CONTRADICTION` meta for the selected claim, `EvidenceAndQA` renders a `ContradictionCard` (its "证据冲突" text + the two source chips + the "置信度由 X 降至 Y" delta).

```tsx
// EvidenceAndQA.test.tsx (append)
it('renders a ContradictionCard when the selected claim has a contradiction', async () => {
  // mock getReport/trace so a claim carries CONTRADICTION meta with
  // supports_domains/refutes_domains; render; select that claim.
  // assert screen.getByText(/证据冲突/) and both domain chips render.
});
```
(Fill in using the existing `EvidenceAndQA.test.tsx` mock pattern: read how `qa_fail`/contradiction meta arrives in `events` and shape a fixture with `code: "CONTRADICTION"` + `meta: { supports_domains: ["a.com"], refutes_domains: ["b.com"] }`.)

- [ ] **Step 2: Run — expect FAIL.** `cd frontend && npm test -- EvidenceAndQA`

- [ ] **Step 3: Implement** — in `EvidenceAndQA.tsx`, derive the contradiction (if any) for the selected claim from the trace `CONTRADICTION` issue meta, and render `<ContradictionCard sources={[{label: supports_domains[0]}, {label: refutes_domains[0]}]} from="..." to="..." />` above the QA section. Reuse the existing component contract (Task 8 of the P1 plan). Pull the from/to confidence from the strength tier before/after, or label "较可信/中" → "较低" generically if the numeric delta isn't available.

- [ ] **Step 4: Run — expect PASS**; `npx tsc -b --noEmit` + full `npm test` green.

- [ ] **Step 5: Commit**

```bash
git add mingjing/frontend/src/views/EvidenceAndQA.tsx mingjing/frontend/src/views/EvidenceAndQA.test.tsx
git commit -m "feat(frontend): surface ContradictionCard in evidence/QA view — visible 可信度 (#2)"
```

---

## Self-Review

**Spec coverage (TODO items):** Breadth-0 → Task 1; Breadth-1 → Task 2; Breadth-2 → Task 3; Breadth-3 → Task 4; #1 domain switch → Task 5; #2 ContradictionCard → Task 6. Deferred (explicitly, not today): #3 KPI panel, #5 survey wiring, #6 docs sync, 🟡/🟢/⚪ items, and the 🚫 guardrails stay out. ✅

**LDR grounding:** Task 2 adapts `decomposition_question.py` (3–5 variants) → deterministic schema/source-type variants; Task 3 adapts `iterative_refinement_strategy.py` loop+termination → gap node with QA-code gap signal; the free-text-synthesis boundary (`citation_handler.py`/`report_generator.py`) is explicitly NOT imported (synthesis stays `project_synthesis`). ✅

**Placeholder scan:** Task 6 Step 1 leaves the exact fixture shape to be read from the existing test (the contradiction-meta event shape is in `trace_events.emit_qa_verdict`); this is a bounded "read the real shape" step, not a vague placeholder — every other code step has concrete code. Task 3's node body is complete; the trace helpers + RunState fields are named explicitly.

**Type consistency:** `build_field_queries` returns `list[{query, source_type}]` used identically in `live_plan_node` (Task 2) and `gap_followup_queries` (Task 3). `detect_gap_fields(required_fields=, latest_claims=, issue_fields=)` signature matches its test and the node caller. `source_cap = per_field_source_cap + round_idx` (Task 1) and the gap node both read `getattr(deps.settings, "per_field_source_cap", 1)`. `gap_round_cap`/`breadth_mode` added to `Settings` in Tasks 3/4 and read in the gap node + toggle. `create_run(..., domain=None)` (Task 5) matches the api/runner/db threading.

**Biggest risks (flag for the implementer):** (1) Task 3 adds a real second loop — keep `gap_round_cap` default 1 and the budget guard so it always terminates; the integration test (Step 8) must prove termination. (2) Multi-query expansion (Task 2) multiplies tasks → more fetches/LLM calls; Task 1's budget raise + Task 4's `fast` default keep interactive runs bounded; the wide corpus is for the pre-recorded `deep` demo. (3) Re-record `scripts/demo_timing.py` after Tasks 1–4 but do NOT gate on the 360s budget (the demo is pre-recorded/time-compressed per the TODO).

**Build order:** Task 1 (foundational cap) → Task 2 (multi-query) → Task 3 (gap loop, depends on 2's `build_field_queries`) → Task 4 (toggle, scales 1+3) → Task 5 (domain switch, independent) → Task 6 (ContradictionCard, independent). Each task commits independently and keeps the suite green.
