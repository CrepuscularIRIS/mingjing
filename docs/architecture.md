# Architecture — MingJing Evidence Runtime

## The loop

Runs have two entry modes: **Directed** (competitors supplied → straight to
`intake`) and **Discovery** (empty competitors + a `category` → a bounded
`discover` runner pre-step selects the competitors first, then `intake`). The
`discover` step only picks *which* competitors enter the loop — it never feeds
search previews into evidence/claims (see `src/mingjing/discovery.py`).

```
(discover) → intake → plan → collect → analyze → qa → route
                         ↑                        │
                         │        reject +        │  pass / round cap / budget
                         └──── revise ────────────┘         │
                                                             ▼
                                                     write → synthesis → END
```

Node labels match the LangGraph `StateGraph` in `graph.py`:

| Node | Kind | Description |
|---|---|---|
| `discover` | orchestration (Discovery Mode only) | Bounded pre-step: `category` → ranked competitor names; never writes evidence/claims |
| `intake` | orchestration | Seeds loop counters (`cap`, `budget_max`, `revision_round=0`) |
| `plan` | orchestration | Expands intake into `(competitor × field)` research tasks |
| `collect` | **Collector agent** | deep-collect pipeline → evidence chunks (see below) |
| `analyze` | **Analyst agent** | One LLM call per field → claim + verbatim-evidence refs |
| `qa` | **QA agent** | 7 deterministic check families → 6 IssueCodes → verdict + issues + RevisionTasks |
| `route` | orchestration | Pure `route()` function → write / revise / write_partial |
| `revise` | orchestration | Reads open RevisionTasks; dispatches by assignee back to collect or analyze |
| `write` | **Writer agent** | Pure deterministic projection of QA-passed claims |
| `synthesis` | **Synthesis** (live graph only) | Post-write LLM brief over passed-claim ledger; emits `synthesis_start`/`synthesis_done`; NON-FATAL |

### Agent vs orchestrator — the critical distinction

There are exactly **4 scored agents**: Collector, Analyst, QA, and Writer.

`intake`, `plan`, `route`, `revise`, and `synthesis` are LangGraph **orchestration
or post-processing nodes** — they are not part of the 4-agent count. The 4-agent
count is load-bearing for the contest's 35% scoring axis.

### Synthesis node (live graph only)

The `synthesis` node runs **after** `write` and before `END` (the compile-only
test skeleton terminates at `write → END`). It calls `run_synthesis()` in
`synthesis.py`, which drives ≤3 LLM calls against the QA-passed claim ledger to
produce a BLUF brief, SWOT analysis, comparison matrix, recommendations, and
intelligence-gap/key-assumptions scaffold. The resulting payload is projected
through `project_synthesis()` (which enforces the same citation-only-from-passed
invariant as the writer) and persisted to the `syntheses` table. The node is
NON-FATAL: any exception is logged and the run still completes, with the frontend
falling back to the deterministic ledger.

On a zero-passed-claims (fully-rejected partial) run the synthesis skips the LLM
calls and instead writes a withheld-claims disclosure (`{"withheld": [...]}`)
enumerating every draft/rejected claim with its final-round issue codes.

### The Evidence-Admissible gate (trust boundary)

MingJing's central design stance: **the LLM proposes, deterministic code adjudicates,
evidence decides.** No conclusion enters the report unless it clears an *admissibility*
bar enforced entirely in non-LLM code (`qa/rules.py`), so the verdict can never be
talked-into by a hallucinating model:

| Rule | What it admits / rejects |
|---|---|
| `schema_gap` | claim missing a required schema sub-field → reject + route to collector |
| `value_unsupported` | a numeric/factual magnitude in the claim not literally present in any cited source → reject + route to collector |
| `hallucinated_snippet` | the claim's evidence snippet is not a verbatim substring of the source's raw text → route to analyst |
| `weak_evidence` | fewer than the required distinct authoritative sources → route to collector (re-collect) |
| `contradiction` / `low_coverage` / `inference_lineage` | cross-source conflict, thin field coverage, unsupported inference chain |

Admissibility is *provider-agnostic by construction*: because the gate reads only the
source text and the claim structure (never the model's self-assessment), swapping the
LLM cannot change what passes. This is why the current high-hallucination stress-test
model (MiniMax-M2.7) and the production target (Doubao-Seed-2.0-lite) yield the same
admission semantics — the gate is the moat, not the model.

### Per-run domain switching

The schema that defines "what fields a competitor must be analysed on" is selected
**per run** via a `ContextVar` (`_active_schema` in `schemas.py`, entered with
`use_domain()` from `runner.py`). The active domain is chosen from the `domain` field
on `POST /runs`, or the `MINGJING_SCHEMA_DOMAIN` env var for CLI runs (read in
`schema_registry.py`, which also loads each domain's field JSON). The default domain
exposes 5 fields (`pricing_model`, `user_sentiment`, `feature_tree`, `user_persona`,
`swot`); alternative domains (`ai_agent`, `hr`) ship their own field sets under
`src/mingjing/domains/`. The analyst and QA both read the active domain's schema, so the
*same* evidence-admissible gate applies regardless of industry — switching domains at
run time re-targets the analysis without touching agent code.

---

## Data flow (full run)

```
┌──────── React (6-tab ink/mirror BI workbench, src/App.tsx NAV_ITEMS) ─────────┐
│ 分析报告(FinalReport) · Schema矩阵(SchemaMatrix) · 证据&溯源(EvidenceAndQA)    │
│ · QA回放(QAReplay) · 执行轨迹(ExecutionTrace) · 可观测(Observability)          │
│ shadcn/ui primitives (src/components/ui/) + Magic UI blur-fade, recharts      │
└───────────────────────────────┬──────────────────────────────────────────────┘
                       2s poll  │  REST  (no SSE)
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  FastAPI  (read-only views over SQLite source of truth)                      │
│  POST /runs  GET /runs/{id}/trace  GET /runs/{id}/report                     │
│  GET /runs/{id}/claims/{cid}/history  GET /runs/{id}/llm_calls               │
│  GET /sources/{id}  GET /health                                              │
└───────────────────────────────┬──────────────────────────────────────────────┘
              LangGraph (single writer process):
              intake → plan → collect → analyze → qa → route
                                ↑                        │ reject (round < cap)
                                └──── revise ────────────┘
                                           pass / cap / budget → write → synthesis → END
                           ┌───────────┬──────────────────────┬──────────────┐
                       Collector    Analyst                  QA            Writer
                         │  uses       │  uses               pure rules    pure projection
                         ▼
               deep-collect pipeline (see below):
               LLM query expansion (per-tier sub_queries: 5 quick / 8 detailed)
               parallel multi-engine search: Bocha(CN) · Tavily · Brave · DuckDuckGo · SearXNG
               quality-biased dedupe (authority + independence + anti-spam scoring)
               two-phase fetch: plain requests (8 s) → Firecrawl JS-render fallback
               thin-source gate (< 100 chars dropped; SPA shells blocked)
               robots gate (urllib.robotparser)
               SSRF guard (is_safe_url, re-validates every redirect hop)
               LIVE or CACHED tag on every persisted source

                           ↓ shared connection + _WRITE_LOCK ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  SQLite WAL + busy_timeout=5000ms                                           │
│  _WRITE_LOCK (threading.Lock) serializes ALL reads and writes on the        │
│  shared connection (check_same_thread=False single-connection model)        │
│  Append-only tables: runs, claims (versioned), evidence_chunks, sources     │
│  Observability tables: trace_events, llm_calls (secrets redacted at write)  │
│  Post-write table: syntheses (BLUF brief + SWOT + withheld-claims)         │
│  Separate read-only cache store: data/cache/cache.db                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## SQLite as source of truth

- Single Python process accesses the DB; FastAPI reads it via the same shared
  connection.
- A module-level `threading.Lock` (`_WRITE_LOCK` in `db.py`) serializes **all**
  accesses — reads and writes — on the single shared connection
  (`check_same_thread=False`). This is single-connection discipline, not true
  concurrent reads; per-thread connections are deferred / not yet implemented.
- Every claim insert is a new row with `version` incremented — **no UPDATE on
  claims**. A revised claim supersedes by version; the history is preserved.
- `source_mode TEXT` column on `sources`: `LIVE` or `CACHED`. This is the
  provenance badge the frontend renders.
- WAL mode + `busy_timeout=5000ms` prevents "database is locked" mid-demo.
- The cache store (`data/cache/cache.db`) is a separate, read-only-at-demo-time
  file; it is never written by the live graph (only by the pre-warm and offline
  cache ingest scripts).

## LLM client timeout

The OpenAI-compatible client (`llm.py`) is built with a **finite timeout**
(`llm_timeout_s`, default 90 s, from `MINGJING_LLM_TIMEOUT`). A stuck provider
raises `openai.APITimeoutError` instead of hanging the run for the SDK default
(~1800 s). The analyst node catches this exception, logs it, and skips the field
rather than crashing the run.

## Deep-collect pipeline

The Collector agent's live path (wired in `graph.py:make_default_collect_fn`)
runs a multi-stage pipeline per research task:

1. **Per-run depth tier** (`config.py`): `quick` (5 sub-queries, Bocha+Tavily+SearXNG+
   DuckDuckGo, top_k=8) or `detailed` (8 sub-queries, Bocha+Tavily+Brave+SearXNG+
   DuckDuckGo, top_k=12). Set via `MINGJING_DEPTH`. The deep-collect path runs every
   (query×engine) pair concurrently and merges; unkeyed engines return [] and drop out.
   博查 Bocha is the China-reachable CN-primary engine (tried first); see `docs/SEARCH.md`.
2. **LLM query expansion** (`collector/query_expansion.py`): the base query is
   expanded to N sub-queries via an LLM call; any LLM failure falls back silently
   to the base query only.
3. **Parallel multi-engine search** (`collector/search.py`): each sub-query fans
   out across the tier's configured engines concurrently; results are merged.
4. **Quality-biased dedupe** (`collector/dedupe.py`): collapses duplicate URLs,
   scores by authority weight (official > news > review), independence bonus
   (first URL per registrable domain), and applies a spam/typosquat penalty.
   Returns the top-K by quality score.
5. **Two-phase fetch** (`collector/fetch.py` + `collector/firecrawl_fetch.py`):
   plain `requests` fetch first (8 s timeout, SSRF guard, robots gate); if the
   result is a near-empty JS shell (< `min_source_chars`, default 100 chars), a
   Firecrawl JS-render call is attempted as a fallback (disabled when
   `FIRECRAWL_API_KEY` is empty). Every persisted source is tagged `LIVE` or
   `CACHED`.
6. **Thin-source gate** (`graph_nodes.py:collect`): fetches below `min_source_chars`
   are dropped before persistence so the analyst never cites an SPA loading shell.
7. **Per-run fetch budget** (`MINGJING_FETCH_BUDGET`, default 60 fetches): tracked
   in the `make_default_collect_fn` closure; budget-exhausted calls return `[]`
   and log a warning (the budget event is not written to `trace_events` because
   the collect_fn contract does not carry a db handle).

---

## Trust mechanics

### 3-tier evidence strength

A transparent, plain-language rule — no confidence decimals:

| Tier | Rule |
|---|---|
| **strong** | ≥ 2 distinct supporting domains AND ≥ 1 authoritative source type (`official`, `survey`) AND no unresolved contradiction |
| **moderate** | Exactly 1 distinct supporting domain; OR ≥ 2 but all from weak types (`news`, `forum`, `review`); OR otherwise-strong but contradiction present (contradiction *caps* at moderate, never lower) |
| **weak** | No `supports` evidence at all |

Supporting sources are deduped by registrable domain: a vendor's blog and its
pricing page on the same domain count as one independent voice.

### The projection invariant

The Writer is a **pure deterministic projection**: it templates claim rows from
the QA-passed set. Any `claim_id` not in that set is silently dropped. The report
can never contain an unbacked claim. This is enforced in code and unit-tested
(`tests/test_writer_projection.py`).

### Honest weak → strong (not withheld data)

The per-field source cap grows with the revision round (`1 + revision_round` in
`graph_nodes.py`). Round 1 collects up to 1 source and may produce a weak claim.
Round 2, after a QA rejection and RevisionTask, collects up to 2 sources —
genuinely new fetches, not data that was held back. The transparent rule
re-scores. Judges can ask "re-run it?" and get a consistent answer.

---

## Bounded live research + pre-warm + auto-downgrade

- **Live-first** (default): Collector tries a live fetch; on timeout (8 s), HTTP
  4xx/5xx, or any exception, falls back to the read-only cache. Every artifact is
  tagged `LIVE` or `CACHED` in the DB; the frontend renders a provenance badge.
- **cache_first** (auto-downgrade): Set `MINGJING_MODE=cache_first` to skip the
  live attempt entirely. Triggered at the D0 spike if outbound web is blocked.
- **Pre-warm** (`prewarm.prewarm_all`): At demo start, a bounded
  `ThreadPoolExecutor` (max 4 workers) pre-fetches every
  `(competitor × field)` URL into the cache store so the first judge-selected run
  hits warm compute. Fetch errors for individual URLs are captured and logged but
  never abort the whole warm-up.
