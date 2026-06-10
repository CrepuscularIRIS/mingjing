# Deep-Collect: Multi-Source Research Depth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise MingJing collection from one query/field (1-3 sources, 0% strong, 897s/6 rounds) to LDR-`quick`/`detailed` depth — query expansion + parallel multi-engine search + quality-biased dedup + JS-render fetch + a verbatim-evidence analyst prompt — feeding the UNCHANGED analyst→QA→route spine.

**Architecture:** A 5-stage collector pipeline behind `collect_fn` (query-expand → parallel search → dedupe+quality-rank → two-phase fetch w/ Firecrawl → existing persist). Plus a prompt-config change in the analyst to emit a verbatim evidence snippet. No change to QA rules, route, scoring, or schema. Source: `docs/superpowers/specs/2026-06-03-deep-collect-multi-source-design.md`.

**Tech Stack:** Python 3.12 + uv + pytest; `requests`/`bs4` (existing); MiniMax via OpenAI SDK (existing); Tavily/Brave/Firecrawl via REST (keys already in `.env`). All tests offline via DI / mocked HTTP — no network, no key.

**Reuse boundary (the moat):** query expansion is the only new LLM use and it generates search strings, not prose. No free-text synthesis, no LLM relevance filter, no confidence decimals.

---

## File structure

- Create: `src/mingjing/collector/query_expansion.py`, `src/mingjing/collector/dedupe.py`, `src/mingjing/collector/firecrawl_fetch.py`
- Modify: `src/mingjing/config.py`, `src/mingjing/collector/search.py`, `src/mingjing/collector/fetch.py`, `src/mingjing/agents/collector.py`, `src/mingjing/agents/analyst.py`, `src/mingjing/api.py`, `src/mingjing/graph.py`, `src/mingjing/runner.py`
- Tests: one `tests/test_*.py` per task (see each task)

---

### Task 1: Config — depth tiers + new Settings fields

**Files:**
- Modify: `src/mingjing/config.py`
- Test: `tests/test_deep_collect_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deep_collect_config.py
import os
from mingjing.config import tier_for, DEPTH_TIERS

def test_quick_tier_knobs():
    t = tier_for("quick")
    assert t.sub_queries == 3 and "duckduckgo" in t.engines and t.top_k == 5

def test_detailed_tier_is_deeper():
    q, d = tier_for("quick"), tier_for("detailed")
    assert d.sub_queries > q.sub_queries and d.top_k > q.top_k
    assert "brave" in d.engines

def test_unknown_depth_falls_back_to_quick():
    assert tier_for("bogus").sub_queries == tier_for("quick").sub_queries

def test_settings_load_reads_new_fields(monkeypatch):
    monkeypatch.setenv("MINGJING_RATE_LIMITING_ENABLED", "true")
    monkeypatch.setenv("MINGJING_DEPTH", "detailed")
    from mingjing.config import Settings
    s = Settings.load()
    assert s.depth == "detailed"
    assert s.deep_collect_workers >= 1
    assert s.fetch_budget_per_run >= 1
```

- [ ] **Step 2: Run — expect ImportError / AttributeError**

Run: `uv run pytest tests/test_deep_collect_config.py -q` → FAIL (`tier_for`/fields missing).

- [ ] **Step 3: Implement**

Add a frozen `DepthTier` dataclass (`sub_queries: int`, `engines: tuple[str,...]`, `top_k: int`, `gather_iterations: int`), a `DEPTH_TIERS: dict[str, DepthTier]` with `quick` and `detailed` per the spec table, and `tier_for(depth: str) -> DepthTier` (unknown → quick, log warning). Add `Settings` fields: `depth`, `deep_collect_workers`, `fetch_budget_per_run`, `firecrawl_api_key`, `firecrawl_base_url`, reading env `MINGJING_DEPTH` (default `"quick"`), `MINGJING_DEEP_WORKERS` (8), `MINGJING_FETCH_BUDGET` (60), `FIRECRAWL_API_KEY` (""), `FIRECRAWL_BASE_URL` (public default). Fields are required (no defaults) on the frozen dataclass.

- [ ] **Step 4: Update all direct `Settings(...)` constructors in tests** (same discipline as `min_source_chars`): `tests/test_demo_feedback_loop.py`, `tests/test_runner.py`, `tests/test_survey_lane_integration.py`, `tests/test_json_repair.py` — add the new fields (depth="quick", deep_collect_workers=8, fetch_budget_per_run=60, firecrawl_api_key="", firecrawl_base_url="").

- [ ] **Step 5: Run** `uv run pytest tests/test_deep_collect_config.py -q` → PASS, then `uv run pytest -q` → no regressions.

- [ ] **Step 6: Commit** — `feat(config): depth tiers + deep-collect settings`

---

### Task 2: Search providers — Tavily + Brave + parallel_search

**Files:**
- Modify: `src/mingjing/collector/search.py`
- Test: `tests/test_search_providers.py`

- [ ] **Step 1: Write failing tests** (mock `requests.get`/`post`; assert preview shape `{url,title,snippet,engine}`, HTTP error → `[]` never raises, `parallel_search` merges engines and tags `engine`).

```python
def test_tavily_returns_previews(monkeypatch): ...   # mock 200 JSON → list of {url,title,snippet,engine:'tavily'}
def test_tavily_http_error_returns_empty(monkeypatch): ...  # mock 500 → []
def test_brave_returns_previews(monkeypatch): ...
def test_parallel_search_merges_and_tags(monkeypatch): ...  # two engines, two queries → tagged, deduped per engine call
```

- [ ] **Step 2: Run** → FAIL (functions missing).
- [ ] **Step 3: Implement** `_tavily_search(query, max_results, api_key)` (POST `api.tavily.com/search`), `_brave_search(query, max_results, api_key)` (GET `api.search.brave.com/res/v1/web/search`, `X-Subscription-Token`), both lazy-import `requests`, never raise (warn + `[]`). Add `parallel_search(queries, engines, *, workers, cache, mode) -> list[dict]` using `ThreadPoolExecutor(max_workers=workers)` over (query × engine), tagging each result `engine`. Engine name → provider fn via a small registry; unknown/keyless engine skipped.
- [ ] **Step 4: Run** provider tests PASS; `uv run pytest -q` green.
- [ ] **Step 5: Commit** — `feat(collector): Tavily + Brave providers + parallel_search`

---

### Task 3: Query expansion

**Files:**
- Create: `src/mingjing/collector/query_expansion.py`
- Test: `tests/test_query_expansion.py`

- [ ] **Step 1: Write failing tests**

```python
def test_expands_to_n_queries(): ...        # fake llm returns 3 lines → 3 unique queries
def test_dedups_and_caps_at_n(): ...
def test_llm_failure_falls_back_to_base(): ...  # llm raises → [base_query]
def test_cache_hit_skips_second_llm_call(): ... # same (run,competitor,field) → llm called once
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `expand_queries(competitor, field, base_query, n, *, llm, cache=None) -> list[str]`. Prompt the LLM for `n` distinct CN/EN search queries for (competitor, field); parse lines; dedup; cap `n`; always include `base_query` as a guaranteed fallback if parsing yields nothing. Wrap LLM call in try/except → `[base_query]` (never raise). Optional in-memory cache keyed `(run_id, competitor, field)`.
- [ ] **Step 4: Run** PASS; full suite green.
- [ ] **Step 5: Commit** — `feat(collector): LLM query expansion (non-fatal, cached)`

---

### Task 4: Dedupe + quality rank (folds spec #2)

**Files:**
- Create: `src/mingjing/collector/dedupe.py`
- Test: `tests/test_dedupe_rank.py`

- [ ] **Step 1: Write failing tests**

```python
def test_exact_url_dedup(): ...
def test_per_domain_cap(): ...                       # >cap from one registrable domain → trimmed
def test_authoritative_ranks_above_forum(): ...      # official source_type ranks above web/forum
def test_new_registrable_domain_gets_independence_bonus(): ...
def test_cross_engine_agreement_breaks_ties(): ...   # url from 2 engines > url from 1
def test_typosquat_is_penalized_below_genuine_independent(): ...  # feiishu.com.cn vs feishu.cn
def test_top_k_truncation_and_stable_order(): ...
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `dedupe_and_rank(previews, *, top_k, per_domain_cap, competitor) -> list[dict]`. Pure. Steps: normalize+dedup URL; group by `independence.registrable_domain`; compute per-preview `quality = authority_weight(infer_source_type(url, competitor)) + independence_bonus(first-seen domain) + agreement(count of engines) - spam_penalty`. `authority_weight` maps source_type via the active domain `source_weights` / Admiralty grade (reuse `scoring`/domain config; official/news high, review/forum/web low). `spam_penalty`: registrable domain within small edit distance of the competitor's official domain, or near-identical title to a higher-ranked item. Apply `per_domain_cap`, sort by quality desc (stable), take `top_k`.
- [ ] **Step 4: Run** PASS; full suite green.
- [ ] **Step 5: Commit** — `feat(collector): quality-biased dedupe (authority+independence+anti-spam)`

---

### Task 5: Firecrawl fetch + fetch_with_fallback retry

**Files:**
- Create: `src/mingjing/collector/firecrawl_fetch.py`
- Modify: `src/mingjing/collector/fetch.py`
- Test: `tests/test_firecrawl_fetch.py`

- [ ] **Step 1: Write failing tests** (mock Firecrawl HTTP; success → `FetchResult`; error/no-key → `None`, never raises; `fetch_with_fallback` thin-plain → Firecrawl invoked → rich text; Firecrawl also thin → still thin).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `firecrawl_fetch(url, *, api_key, base_url, timeout) -> FetchResult | None` (POST `{base_url}/scrape`, returns rendered text; never raises; `None` when no key/error). In `fetch.py`, add an optional Firecrawl retry to `fetch_with_fallback(..., firecrawl=None, min_chars=0)`: if the plain/cache result text < `min_chars` and a firecrawl callable is provided, try it; keep the richer result. Default args keep existing callers unchanged.
- [ ] **Step 4: Run** PASS; full suite green.
- [ ] **Step 5: Commit** — `feat(collector): Firecrawl JS-render fallback for thin pages`

---

### Task 6: Collector orchestration + settings-closure wiring (fetch budget)

**Files:**
- Modify: `src/mingjing/agents/collector.py` (extend `collect` signature), `src/mingjing/graph.py` (add `make_default_collect_fn`), `src/mingjing/runner.py` (wire the closure)
- Test: `tests/test_deep_collect_orchestration.py`

**Runtime contract (verified):** `collect_node` calls `deps.collect_fn(query, cache=, source_cap=, mode=)` and offline DI fakes are exactly `(query, *, cache, source_cap, mode=...)`. Do NOT add a `settings=` kwarg to that call — it breaks every fake. Settings reach production via a closure.

- [ ] **Step 1: Write failing tests** — (a) `make_default_collect_fn(settings)` returns a callable with the contract `(query, *, cache, source_cap, mode)`; (b) drive it with mocked `parallel_search` (many previews across domains) + mocked fetch → returns many deduped sources, per-domain diversity holds, per-run fetch budget caps total fetches (emit `fetch_budget_exhausted` trace when hit); (c) the bare `_default_collect_fn` still works with no settings (fallback).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** —
  - Extend `collector.collect(query, cache, *, max_results=5, source_cap=3, timeout=8.0, mode, fetch_robots=None, engines=None, top_k=None, workers=1, firecrawl=None, competitor="", llm=None)` — new params keyword-only with defaults so existing callers/tests are unaffected. When `engines` is set, run the deep pipeline: expand_queries → parallel_search(engines) → dedupe_and_rank(top_k, competitor) → two-phase fetch (Firecrawl on thin) honoring a fetch-budget counter; else fall back to today's single-query path.
  - `graph.make_default_collect_fn(settings)` returns a closure `(query, *, cache, source_cap, mode)` that resolves `tier_for(settings.depth)` and calls `collect(...)` with the tier's engines/top_k/workers + a firecrawl callable built from settings. The bare `_default_collect_fn` stays as the GraphDeps default (no-settings fallback).
  - `runner.py`: when the caller passed no `collect_fn` override, set `deps_kwargs["collect_fn"] = make_default_collect_fn(active_settings)`.
  - Keep the `collect_fn` RETURN shape (`fetched`, `url`, `text`, `source_mode`, `content_hash`, `fetched_at`, `title`) so the live `collect_node` is unchanged.
- [ ] **Step 4: Run** PASS; `uv run pytest -q` green (offline loop tests inject their own `collect_fn`, so the closure only runs in production/its own test; the call contract is unchanged so fakes don't break).
- [ ] **Step 5: Commit** — `feat(collector): deep-collect orchestration + settings-closure wiring`

---

### Task 7: Analyst verbatim-evidence prompt (folds spec #3)

**Files:**
- Modify: `src/mingjing/agents/analyst.py`
- Test: `tests/test_analyst_verbatim_evidence.py`

- [ ] **Step 1: Write failing tests** — (a) the built prompt text instructs a verbatim snippet copied from each cited source; (b) with a fake LLM that returns a claim whose `evidence[].snippet` is copied from the source `raw_text`, the claim passes the existing grounding / `value_unsupported` checks at round 0; (c) a paraphrased/absent snippet is still rejected (the gate is fed, not bypassed).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — extend the analyst prompt to require, per cited source, a verbatim snippet (≤N chars copied from that source's provided text) that contains the claim's value, written into the existing `evidence_json.snippet` field. No schema change. Keep the `<UNTRUSTED>` injection envelope. Do not alter QA rules.
- [ ] **Step 4: Run** PASS; full suite green.
- [ ] **Step 5: Commit** — `feat(analyst): verbatim-evidence snippet prompt (raise round-0 groundedness)`

---

### Task 8: API depth param + run threading

**Files:**
- Modify: `src/mingjing/api.py` (and `runner.py` if the executor needs the depth)
- Test: `tests/test_api_depth.py`

- [ ] **Step 1: Write failing tests** — `POST /runs` accepts optional `depth` (`quick`/`detailed`), persists/threads it; omitted → settings default; invalid → 422 or coerced-to-quick (pick one; test it).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add `depth: str | None` to `CreateRunRequest`; thread into the executor so the collector tier resolves per-run (env default when None).
- [ ] **Step 4: Run** PASS; full suite green.
- [ ] **Step 5: Commit** — `feat(api): per-run depth (quick|detailed)`

---

### Task 9: Full verification

- [ ] **Step 1:** `uv run pytest -q` — paste output, 0 failures.
- [ ] **Step 2:** (optional, key-gated) one live `detailed` run on a high-coverage competitor; confirm more sources, ≥1 `strong` claim, fewer QA rounds than the 6-round baseline. Compare KPIs to the 20%-coverage/0%-strong/897s reference run.
- [ ] **Step 3:** Dispatch a final code-reviewer over the whole branch (superpowers:requesting-code-review).
- [ ] **Step 4:** `superpowers:finishing-a-development-branch`.

---

## Expected KPI impact (why this plan)

The reference run (coverage 20%, **strong 0%**, 897s, 6 rounds) is the signature of shallow undirected collection. Tasks 1-6 raise breadth + source quality so claims can reach the ≥2-independent-source "strong" bar; Task 7 raises round-0 groundedness so fewer claims bounce → fewer QA rounds → lower latency. The deterministic QA gate, scoring, and projection invariant are untouched — this lifts the *inputs*, not the verdicts.

## Self-review notes

- **Runtime contracts verified against code** (the contract conflict the stop-review caught):
  - `collect_fn` call contract is `(query, *, cache, source_cap, mode)` and offline DI fakes match it exactly → settings reach production via `make_default_collect_fn(settings)` closure (T6), NOT a new call kwarg. The call site is unchanged, so fakes don't break.
  - `collect(query, cache, *, max_results=5, source_cap=3, timeout=8.0, mode, fetch_robots=None)` — deep-collect params added keyword-only with defaults (T6).
  - `independence.registrable_domain(source)` takes the source/url object; `claim_builder.infer_source_type(url, competitor)`; `qa/groundedness.score_groundedness(*, value, cited_source_text)` (keyword-only).
  - `evidence_json.snippet` is already read by `qa/rules.py:134` and written by `claim_builder.py:273` → #3 (T7) needs no schema change.
  - `domains/*.json source_weights` (Admiralty B/C/D/E) + `admiralty.grade` exist → #2 (T4) authority_weight reuses them.
- Type consistency: `dedupe_and_rank(previews, *, top_k, per_domain_cap, competitor)` matches the spec components table and the T6 orchestration call.
- No placeholders: each task has concrete test names, signatures, and commit messages. Implementation bodies follow existing collector/agent patterns.
- Spec coverage: query expansion (T3), parallel multi-engine (T2), quality dedupe / spec #2 (T4), Firecrawl (T5), tiers/config (T1), orchestration + settings closure + budget (T6), verbatim-evidence / spec #3 (T7), API depth (T8), verification (T9). All spec sections map to a task.
