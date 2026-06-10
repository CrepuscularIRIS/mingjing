# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

MingJing (明镜) is an evidence-grounded competitive-analysis multi-agent runtime built on LangGraph. It searches the web, has an independent QA agent reject weakly-supported claims, re-collects real evidence, and upgrades claims from weak → strong. Every conclusion links to its original source. The current LLM is MiniMax-M2.7 via OpenAI SDK, run deliberately as a *high-hallucination stress test* for the provider-agnostic deterministic QA gate; the gate is also verified on the contest Doubao-Seed-2.0-lite (full run 33835db0, 2026-06-10 — config-level switch, see architecture.md "Evidence-Admissible gate").

## Commands

```bash
make setup          # uv sync + cd frontend && npm install (run once after clone)
make test           # full offline suite (883 backend tests, no API key needed)
make test-slow      # only @pytest.mark.slow tests (end-to-end graph loops)
make api            # FastAPI on :8000 (loads .env)
make web            # Vite dev server on :5173
make web-build      # production frontend build (tsc + vite)
make demo-reliable  # curated demo run (requires MINIMAX_API_KEY in .env)

# NOTE: typecheck the frontend with `tsc -b` (NOT `tsc --noEmit` — the root
# tsconfig is references-only, so --noEmit reports a false "clean").

# single test
uv run pytest tests/test_scoring.py -v
uv run pytest tests/test_scoring.py::test_strong_two_domains -v

# frontend tests
cd frontend && npx vitest run
```

Copy `.env.example` → `.env` and set `MINIMAX_API_KEY` for live runs. Offline/CI runs need no key — the test suite injects fakes via dependency injection.

## Architecture

### Graph loop (LangGraph StateGraph)

```
(discover) → intake → plan → collect → analyze → qa → route ─┬→ write → END
                        ↑                                     │
                        └──── revise (collect|analyze) ───────┘
```

Dual entry: **Directed Mode** (competitors supplied → straight to `intake`) and
**Discovery Mode** (empty competitors + a `category` → a bounded `discover`
runner pre-step in `discovery.py` selects WHICH competitors enter the loop;
never feeds previews into evidence/claims). See `runner._discover_competitors_best_effort`.

- **RunState** (`graph.py`): field-keyed, append-only TypedDict. List fields use `operator.add` reducers (concurrent-safe deltas); scalars are last-write-wins.
- **GraphDeps** (`graph.py`): dependency-injection carrier (db, cache, settings, collect_fn, analyze_fn). Nodes close over it; RunState stays serializable.
- **Two build modes**: `build_graph()` = compile-only skeleton for tests; `build_graph(deps=GraphDeps(...))` = live loop with real agents.

### 4 agents (`src/mingjing/agents/`)

| Agent | Role | Pure? |
|-------|------|-------|
| **collector** | web search → robots check → fetch with SSRF guard → evidence chunks | no (I/O) |
| **analyst** | one LLM call per field; prompt-injection envelope (`<UNTRUSTED>` block) | no (LLM) |
| **qa** | 7 deterministic verifier check families → 6 IssueCodes (no LLM, no prompt injection risk) | yes |
| **writer** | pure projection of QA-passed claims into report template | yes |

### Key invariants

- **Honest weak→strong**: source cap = 1 + revision_round. Later rounds fetch genuinely new data, not withheld.
- **Projection invariant**: writer only emits QA-passed claims. No unbacked claim can reach the report.
- **Append-only DB**: claims are never UPDATEd — new row with version++. History preserved.
- **SSRF guard**: `is_safe_url()` blocks private IPs/loopback/metadata; robots redirect hops re-validated.

### QA pipeline (`src/mingjing/qa/`)

- `rules.py`: deterministic checks — schema_gap, weak_evidence, hallucinated_snippet, contradiction, low_coverage, value_unsupported, inference_lineage.
- `route.py`: pure router — pass → write; reject + budget → revise (dispatch to collector or analyst per `assignee`); over cap → write_partial.

### Scoring (`scoring.py`)

Transparent 3-tier: strong / moderate / weak. Based on distinct registrable domains, authoritative source types (`official`, `survey`, `interview`), and contradiction flag. No confidence decimals.

### Database (`db/` package)

Single-file SQLite, WAL mode, `threading.Lock` for single-writer. Split into a
mixin package (`db/_base.py` lock+schema+migrations, `_runs.py`, `_claims.py`,
`_sources.py`, `_trace.py`; `db/__init__.py` composes `Database`). One canonical
`_WRITE_LOCK`. Tables: runs, claims, sources, evidence_chunks, qc_reports, revision_tasks, trace_events, llm_calls.

### Domain schemas (`schema_registry.py`, `src/mingjing/domains/`)

ContextVar-based per-run schema switching. Default 5 fields: pricing_model, user_sentiment, feature_tree, user_persona, swot. Set `MINGJING_SCHEMA_DOMAIN` env var for alternatives.

### API (`api.py`)

FastAPI, read-only views + `POST /runs` to kick off a run. `POST /runs` accepts `category` + `goal` + `competitors` (optional); Discovery Mode (empty `competitors` + non-empty `category`) also accepts `market_scope` / `max_competitors` / `seed_competitors` and runs a bounded `discover` pre-step (`discovery.py`) that selects WHICH competitors enter the loop. See `CreateRunRequest` (`api_models.py`). Key endpoints: `GET /runs` (list), `/runs/{id}/trace`, `/runs/{id}/report`, `/runs/{id}/synthesis`, `/runs/{id}/withheld`, `/runs/{id}/credibility`, `/runs/{id}/metrics`, `/runs/{id}/claims/{cid}/history`, `/sources/{id}`, `/schemas`, `/health`.

### Frontend (`frontend/`)

React 19 + Vite + TypeScript + Tailwind. Key views: FinalReport, QAReplay, ExecutionTrace, Observability, SchemaMatrix, EvidenceAndQA. Polls `/runs/{id}/trace` every 2s. Tests via Vitest.

## Testing patterns

- All offline tests use dependency injection (fake collect_fn / analyze_fn) — no network, no API key.
- `@pytest.mark.slow` marks end-to-end graph-loop tests.
- QA rule tests are pure: construct claim/source fixtures, assert verdicts.
- Writer tests verify the projection invariant: rejected claims must not appear in output.
- SSRF tests cover private IP blocking, redirect bypass, port restrictions.

## Source layout

```
src/mingjing/
├── graph.py / graph_nodes.py   # LangGraph wiring + live node factories
├── runner.py                   # production run executor
├── config.py                   # Settings (Pydantic, frozen, from env)
├── schemas.py                  # domain models (Pydantic v2)
├── schema_registry.py          # per-run domain switching
├── db/                         # SQLite persistence (mixin package)
├── scoring.py                  # 3-tier evidence strength
├── llm.py                      # MiniMax client + JSON repair
├── api.py                      # FastAPI
├── agents/{collector,analyst,qa,writer}.py
├── collector/{search,fetch,robots,independence,cache}.py
├── qa/{rules,route}.py
├── trace.py / trace_events.py  # observability
├── survey.py / survey_seed.py  # 问卷/访谈 evidence lane
└── domains/                    # field schema definitions
```
