# Plan — Lightweight Discovery Mode (品类 → 自动发现竞品)

**Date:** 2026-06-08
**Branch:** feature/mingjing-0608
**Owner:** AutoPilot (Opus main loop)

## Why

The organizer's real usage scenario is "give a **category / market scope**, the
system **discovers** the competitors and analyzes them." Today `POST /runs`
**requires** a non-empty `competitors` list (`competitors_not_empty` validator in
`api_models.py:30`). That is the one real, high-leverage input gap (GAP-1): the
product can do the full task but does not fit the organizer's ideal input shape.

This plan adds a **bounded** Discovery Mode as a **pre-step** in the runner —
NOT a full recursive DeepResearch. The QA gate, evidence/provenance, scoring, and
the graph loop are **untouched**. Discovery only decides *which competitors* enter
the existing, proven pipeline.

## Dual entry (decided by input, not a mode flag)

- **Mode B — Directed (unchanged):** request carries `competitors` → run exactly
  as today. Zero behavior change. This is the regression guard.
- **Mode A — Discovery:** request carries `category` (+ optional `market_scope`,
  `seed_competitors`, `max_competitors`) and **empty** `competitors` → the runner
  runs `discover_competitors()` first, populates competitors, then proceeds.

`if competitors: directed  else: discover(category, ...)` — that single branch is
the whole contract.

## Hard constraints (inviolable)

1. **No full DeepResearch.** Discovery is one bounded pass: ≤ `max_queries`
   searches (default 4), small top-k each, NO recursion, NO follow-on crawl.
2. **Do not weaken QA / evidence / scoring / PII / robots / SSRF.** Discovery
   feeds names in; everything downstream is identical.
3. **Directed Mode is byte-for-byte unchanged** when `competitors` is provided.
4. **Honest.** Discovery emits real search-derived candidates + a transparent
   rationale (source count, official-page hit). The demo uses a **cached real**
   search fixture (same honesty bar as `demo/corpus/*.json`), never fabricated.
5. **Best-effort, never crash.** Discovery failure (empty search, network) is
   logged + traced; the run degrades honestly (it just has no/seed competitors),
   mirroring `_prewarm_best_effort` / `_seed_survey_lane_best_effort`.
6. **Locked artifacts untouched:** demo run 3775d21a; money-shot data-testids
   (`qa-moneyshot`, `pass1-badge`, `pass2-badge`, `qa-delta`, `strength-rule`,
   `claim-ledger`), `nav-*`, `domain-select`, `view-example-btn`.

## Tasks

### D2 — `src/mingjing/discovery.py` (PURE core + injected I/O) + `tests/test_discovery.py`

Pure, deterministic, dependency-injected (search via a `search_fn` param). No
network in the module's pure functions; only `discover_competitors` calls the
injected `search_fn`.

- `build_discovery_queries(category, *, market_scope=None, goal=None, max_queries=4) -> list[str]`
  PURE. Deterministic templates, e.g. (scope-prefixed when given):
  `"{scope}{category} 竞品有哪些"`, `"top {category} products {scope}"`,
  `"best {category} tools 2026 {scope}"`, `"{category} alternatives comparison"`.
  Deduped, clamped to `max_queries` (clamp 1..6). Scope words map:
  `china`→「中国」, `global`→「全球」, else the raw string.
- `extract_candidates(previews, *, category) -> list[Candidate]`
  PURE. From `{url,title,snippet}` previews, derive candidate product names:
  registrable-domain brand (e.g. `linear.app` → "Linear"), title head before
  separators (`| - – :`), and known stop-word filtering (category words,
  generic words like "best/top/2026/comparison/review/blog"). Count distinct
  registrable domains supporting each candidate (reuse independence logic if
  cheap; else a simple registrable-domain helper). `Candidate` =
  `{name, domains:set, source_count, has_official}` where `has_official` =
  a domain whose root matches the candidate slug.
- `rank_candidates(cands, *, max_competitors, seed_competitors=()) -> list[str]`
  PURE. Sort by `(has_official, source_count, -len(name))` desc; seeds always
  included first (deduped, case-insensitive); clamp to `max_competitors`
  (clamp 1..6). Returns clean display names.
- `discover_competitors(category, *, market_scope=None, goal=None, seed_competitors=(), max_competitors=4, max_queries=4, search_fn) -> DiscoveryResult`
  Orchestrate: queries → (bounded) `search_fn(q)` per query → flatten previews →
  `extract_candidates` → `rank_candidates`. `DiscoveryResult` =
  `{selected:list[str], candidates:list[dict], queries:list[str]}` (candidates
  carry name/source_count/has_official for the trace + UI panel). Never raises:
  on any search error returns seeds (or `[]`) with an empty-candidate result.

Tests (pure, no network): query templating + bound, candidate extraction from
fixture previews, ranking (seeds-first, official-boost, top-N clamp), discover
orchestration with a fake `search_fn` (asserts ≤max_queries calls, ≤max selected,
deterministic order, error→seeds fallback).

### D3 — `api_models.py` + `db.py` + `runner.py` + `api.py`

- **api_models.py:** `competitors: list[str] = []` (optional). Add
  `market_scope: str | None = None`, `max_competitors: int = 4`,
  `seed_competitors: list[str] = []`. Replace `competitors_not_empty` with a
  model validator: require `category.strip()` non-empty when `competitors`
  empty (Discovery needs a category); clamp `max_competitors` to 1..6.
- **db.py:** `update_run_competitors(run_id, competitors)` — UPDATE
  `runs.competitors_json` (runs table already mutates `status`; consistent).
- **runner.py:** in `run(run_id)`, after reading `run_row`, before building
  intake: if `competitors` empty → `_discover_competitors_best_effort(...)`:
  emit `discovery_started` trace (category, market_scope, queries), call
  `discover_fn` (new injectable param; default = real bounded wrapper over
  `collector.search.search` with small `max_results`), emit
  `competitors_discovered` trace (selected + candidates), persist via
  `db.update_run_competitors`, set local `competitors`. Best-effort wrapper:
  failure logs + emits `discovery_empty`, run proceeds honestly. `make_run_executor`
  gains `discover_fn: Callable | None = None` (tests inject deterministic).
- **api.py:** `POST /runs` passes `market_scope`/`max_competitors`/
  `seed_competitors` through to `create_run` (store market_scope/max via the run
  row OR thread through to the executor). Simplest: persist `competitors`
  (possibly empty) + stash `market_scope`/`max_competitors`/`seed_competitors`
  on the run row. **Decision:** add nullable `market_scope` column +
  reuse existing columns is heavy; instead pass discovery params to the executor
  via the run row's `goal`? No — add minimal columns `market_scope TEXT`,
  `max_competitors INTEGER`, `seed_competitors_json TEXT` to `runs` (idempotent
  `ALTER TABLE ... ADD COLUMN` in schema init, mirroring how `domain`/`depth`
  were added). `get_run` returns them; runner reads them.

Tests: api_models accepts empty competitors + category; rejects empty+empty;
clamps max_competitors. db round-trips new columns + update_run_competitors.
runner: directed (competitors set) → discover_fn NOT called; discovery
(competitors empty) → discover_fn called once, competitors persisted, traces
emitted; discovery error → run still completes (best-effort).

### D4 — Frontend dual-entry form + discovered-competitors panel

- **types.ts:** `CreateRunBody.competitors?` optional; add `market_scope?`,
  `max_competitors?`, `seed_competitors?`.
- **client.ts:** unchanged signature (body is the typed object).
- **App.tsx:** competitors input optional. Helper: "留空 = 自动发现竞品
  (Discovery Mode)". Add a **market-scope** `<select>` (全球 global / 中国 china
  / 自定义) — native select like `domain-select` for test-drivability,
  `data-testid="market-scope-select"`. Submit: require `category` + `goal`;
  competitors optional. When competitors empty show a small "Discovery Mode"
  badge. New **DiscoveredCompetitors** panel (`data-testid="discovered-competitors"`)
  rendered from the `competitors_discovered` trace event payload (selected +
  candidate chips with source counts). Keep ALL locked testids.
- **lib/trace.ts:** map `discovery_started`/`competitors_discovered`/
  `discovery_empty` to readable activity-feed labels (System role).

Tests (vitest): submit with empty competitors succeeds (Discovery); market-scope
select present + included in body; discovered-competitors panel renders from a
seeded trace event; directed submit (competitors filled) still works.

### D5 — Demo fixture + verify + Codex review + commit

- Cached real discovery fixture for "中国范围内 通用 AI Agent 竞品分析"
  (`demo/discovery/ai-agent-cn.json` — real captured search previews) + a
  `scripts/run_discovery_demo.py` (or extend `run_demo.py`) that runs Discovery
  Mode against the fixture so the closed loop is reproducible offline.
- Verify: `make test` (backend, expect 686 + new), `cd frontend && tsc -b`,
  `npx vitest run`, `make web-build`; Playwright live walkthrough of Discovery
  Mode (empty competitors → discovered panel → run). Zero console errors.
- Codex adversarial review of the full diff (`codex review --base <merge-base>`);
  fix Critical/Important; commit on feature/mingjing-0608 (no attribution).

## Out of scope (explicit)

- Recursive/iterative discovery, candidate disambiguation LLM calls, entity
  resolution beyond the cheap heuristics, a separate discovery graph node.
- Any change to QA rules, scoring, route, writer projection, or the loop.
