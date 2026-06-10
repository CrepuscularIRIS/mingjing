# Deep-Collect: Multi-Source Research Depth (LDR-level) — Design

**Date:** 2026-06-03
**Status:** Approved (design) — pending spec review → implementation plan
**Author:** AutoPilot session

## Goal

Raise MingJing's evidence collection from a single web query per field (1–3 sources)
to LDR-`quick_research`/`detailed_research`-level depth (dozens of deduped, ranked,
full-content sources per field) — **without** adopting any of LDR's free-text
synthesis. Gathered sources flow through the **unchanged** analyst→QA→route spine,
so more/better sources produce more claims that survive the deterministic grounding
gate. This directly addresses "内容太少" (reports too thin) and is the root remedy
behind the Feishu failure (shallow collection + unscrapable SPA pages).

## Why now (evidence)

- A live Feishu run gathered only 1–3 sources/field; most were JS-rendered SPA shells
  (`feishu.cn` → ~8 chars). 0 claims passed grounding.
- The just-shipped thin-source gate took that run 0 → 2 passing claims, groundedness
  1.0, repair_delta +0.562 — confirming the bottleneck is **collection depth + source
  quality**, not the verification spine.
- LDR (MIT, `/home/lingxufeng/cli/local-deep-research`) reaches high SimpleQA/DeepSearch
  scores via iterative query expansion + parallel multi-engine search + two-phase
  preview→fetch. We replicate that *source-gathering* layer natively.

## The reuse boundary (the moat — non-negotiable)

MingJing's differentiation is **deterministic, evidence-admissible verdicts**: the LLM
proposes, deterministic code renders truth, the report is a projection of a verified
ledger. Therefore we adopt LDR's source-gathering depth but **must NOT** adopt:

- `report_generator` / `IntegratedReportGenerator` (free-text section synthesis)
- `citation_handler` (LLM citation formatting)
- `CrossEngineFilter` (LLM relevance filtering) — we use deterministic dedup/rank
- any confidence-decimal scoring or free-text "findings"

**The only new LLM use is query expansion** (generating sub-queries from a field +
competitor). That is query *generation*, not synthesis — it produces search strings,
never claims or prose that reach the report. It is non-fatal: on any LLM failure we
fall back to the existing single template query.

## Architecture

Replace the single-query `_default_collect_fn` with a 5-stage per-task pipeline inside
the collector. The `collect_node` contract (returns `{"sources": [...]}` of
`{source_id, field, competitor}`, persists via `append_source`/`append_evidence_chunk`)
is unchanged — only the gathering behind `collect_fn` deepens. The existing
thin-source gate (`Settings.min_source_chars`) and round-aware behavior remain.

```
field task (competitor, field, base query)
  │
  1. QUERY EXPANSION   query_expansion.py
  │     MiniMax generates N sub-queries (N per depth tier) for (competitor, field).
  │     Cached per (run, competitor, field). Non-fatal: on failure → [base query].
  │
  2. PARALLEL SEARCH   collector/search.py (extended)
  │     For each sub-query × engine in the tier's chain, run preview search in
  │     parallel (ThreadPoolExecutor, bounded workers). Each engine obeys the
  │     existing never-raise contract (failure → [] + warning). Returns preview
  │     rows: {url, title, snippet, engine}.
  │
  3. DEDUP + RANK      collector/dedupe.py
  │     Normalize URL; drop exact-URL dups; dedup/limit by registrable domain
  │     (reuse independence.registrable_domain) with a per-domain cap to preserve
  │     source diversity. RANK by a deterministic quality score (NO LLM), highest
  │     first, then select top-K (K per tier):
  │       quality = authority_weight(source_type) + independence_bonus
  │                 + cross_engine_agreement − spam_penalty
  │     reusing existing primitives:
  │       - claim_builder.infer_source_type(url, competitor) → source_type, scored
  │         via the active domain's source_weights / Admiralty grade (official/news
  │         high, review/forum/web low). This directly lifts the 0%-strong ceiling:
  │         "strong" needs ≥2 independent + ≥1 authoritative source, so the fetch
  │         set must be biased toward authoritative + independent BEFORE fetch.
  │       - registrable-domain diversity (already used downstream by scoring +
  │         contradiction) → an independence_bonus for new registrable domains.
  │       - a spam_penalty for near-duplicate / typo-squat hosts (e.g. the
  │         feiishu.com.cn clones seen in the Feishu run): penalize hosts whose
  │         registrable domain is an edit-distance-near variant of a competitor's
  │         official domain, or that repeat near-identical titles.
  │     This is the cure for "low-quality, narrow sources": breadth (stage 1-2) +
  │     quality-biased selection here, all deterministic.
  │
  4. TWO-PHASE FETCH   collector/fetch.py (+ firecrawl_fetch.py)
  │     Fetch full content for the top-K survivors via fetch_with_fallback.
  │     If extracted text < min_source_chars, retry that URL via Firecrawl
  │     (firecrawl_fetch.py) to render JS pages (feishu.cn SPA fix). The thin-source
  │     gate still applies AFTER Firecrawl: if even rendered text is thin, skip
  │     (source_skipped trace). Bounded by a per-run fetch budget.
  │
  5. → collect_node → append_source / append_evidence_chunk → analyst
        (prompt tightened — see "Analyst verbatim-evidence prompt" below)
```

## Analyst verbatim-evidence prompt (cut QA rounds, raise groundedness)

Borrowed from LongSeeker/OpenSeeker `visit.py` (`{rational, evidence, summary}`,
where `evidence` is the ORIGINAL quoted text, never a paraphrase). Today's analyst
cites `source_id`s; it does not have to quote the exact span its value came from, so
the deterministic grounding check (`qa/groundedness.py`, `qa/rules.py value_unsupported`)
often can't find the value in the cited text → reject → another QA round. That is a
direct driver of the 897s / 6-round / 80%-reject profile.

Change (prompt-config only, in `agents/analyst.py`): require each proposed claim to
carry, per cited source, a **verbatim snippet copied from that source's `raw_text`**
that contains the claim's value. The QA gate already verifies grounding; feeding it a
model-supplied verbatim quote means a claim either cites text that truly contains its
value (passes round 0) or is honestly rejected — fewer revise loops, higher
round-0 groundedness. No schema/architecture change: the snippet rides in the existing
`evidence_json` `snippet` field that `claim_builder` and the QA verifier already read.
This is the "LLM-indexed prompt configuration" polish; it stays inside the moat
(extraction discipline, not free-text synthesis).

## Depth tiers

A per-run `depth` parameter (default from env `MINGJING_DEPTH`, default `quick`),
surfaced on `POST /runs` (`CreateRunRequest.depth`). Tier maps to config knobs:

| Tier | sub-queries/field | engine chain | top-K fetch/field |
|------|-------------------|--------------|-------------------|
| `quick` (default) | 3 | `tavily, duckduckgo` | 5 |
| `detailed` | 5 | `tavily, brave, duckduckgo, searxng` | 10 |

Depth tiers differ by candidate BREADTH (sub-queries, engines, top-K), not by fetched-source count per round — per-round fetch depth is the graph's source_cap = 1 + revision_round weak→strong loop.

`quick` keeps live-demo latency manageable; `detailed` maximizes depth. Both are fully
config-overridable. The mapping lives in `config.py` as a frozen tier table; unknown
`depth` values fall back to `quick` with a warning.

## Configuration (config.py / env)

New `Settings` fields (env-driven, with defaults):
- `depth: str` — `MINGJING_DEPTH` (default `"quick"`).
- `deep_collect_workers: int` — `MINGJING_DEEP_WORKERS` (default `8`) — ThreadPool cap.
- `fetch_budget_per_run: int` — `MINGJING_FETCH_BUDGET` (default `60` quick / honored as a hard cap across the run).
- `firecrawl_api_key: str` — `FIRECRAWL_API_KEY` (default `""`; empty disables Firecrawl).
- `firecrawl_base_url: str` — `FIRECRAWL_BASE_URL` (default the public API).
- Tier knobs resolved from a `DEPTH_TIERS` table keyed by `depth`.

Existing engine keys read from env (already present in `.env`): `TAVILY_API_KEY`,
`BRAVE_API_KEY`, optionally `SEARXNG_URL`. Missing key → that engine is skipped (chain
degrades gracefully to whatever is configured, never crashes).

All new direct `Settings(...)` constructors in tests must be updated (frozen dataclass,
no defaults on required fields) — same discipline as `min_source_chars`.

## New / changed components

| File | Responsibility | Pure? |
|------|----------------|-------|
| `collector/query_expansion.py` (new) | `expand_queries(competitor, field, base_query, n, llm) -> list[str]`. MiniMax sub-query generation; cached; non-fatal fallback to `[base_query]`. | no (LLM) |
| `collector/search.py` (extend) | Add `_tavily_search`, `_brave_search` providers (never-raise). Add `parallel_search(queries, engines, workers) -> list[preview]`. | no (I/O) |
| `collector/dedupe.py` (new) | `dedupe_and_rank(previews, top_k, per_domain_cap, competitor) -> list[preview]`. URL/domain dedup, diversity cap, and quality-biased rank: authority (infer_source_type + source_weights), registrable-domain independence bonus, cross-engine agreement, typo-squat/near-dup spam penalty. | yes |
| `collector/firecrawl_fetch.py` (new) | `firecrawl_fetch(url, api_key, base_url, timeout) -> FetchResult \| None`. JS-render fallback; never raises. | no (I/O) |
| `collector/fetch.py` (extend) | `fetch_with_fallback` gains an optional Firecrawl retry when extracted text < `min_chars`. | no (I/O) |
| `agents/collector.py` (extend) | Orchestrate the 5 stages behind `collect(...)`, honoring tier + fetch budget. | no |
| `agents/analyst.py` (extend) | Tighten the analyst prompt to require a verbatim snippet (copied from each cited source's raw_text) carrying the claim's value, written into the existing `evidence_json.snippet`. Prompt-config only; raises round-0 groundedness, cuts revise rounds. | no (LLM) |
| `config.py` (extend) | New fields + `DEPTH_TIERS` table + `tier_for(depth)`. | yes |
| `api.py` (extend) | `CreateRunRequest.depth` (optional, default from settings); thread into the executor/run. | no |
| `graph.py` (extend) | Add `make_default_collect_fn(settings) -> collect_fn` — a closure over Settings that resolves the depth tier (engines/top_k/workers/firecrawl) and runs the pipeline. The bare `_default_collect_fn` stays as the no-settings fallback. **The `collect_node → collect_fn(query, *, cache, source_cap, mode)` CALL CONTRACT is unchanged** — settings ride in the closure, NOT a new call kwarg (adding one would break every offline DI fake, which is exactly `(query, *, cache, source_cap, mode)`). | no |
| `runner.py` (extend) | When no test `collect_fn` override is given, set `deps.collect_fn = make_default_collect_fn(active_settings)` so production collection sees the run's depth/engines/firecrawl. | no |

> **Runtime-contract note (verified against code):** `collect()` is currently
> `collect(query, cache, *, max_results=5, source_cap=3, timeout=8.0, mode, fetch_robots=None)`
> — deep-collect params (engines, top_k, workers, firecrawl) are added keyword-only with
> defaults so existing callers/tests are unaffected. `independence.registrable_domain(source)`
> takes the source/url object (not a bare `url: str` keyword). `qa/groundedness.score_groundedness`
> is keyword-only `(*, value, cited_source_text)`. The analyst `evidence_json` `snippet` field
> is already read by `qa/rules.py` and written by `claim_builder.py` — #3 needs no schema change.
> `domains/*.json source_weights` (Admiralty letters B/C/D/E) + `admiralty.grade` already exist —
> #2's authority_weight reuses them.

## Data flow & state

- `collect_node` still returns `{"sources": [...]}`; the `sources` reducer
  (`operator.add`, append-only) accumulates across rounds. Deeper gathering simply
  appends more rows per round. The weak→strong round mechanism is preserved (round 2
  in `detailed` re-expands from round-1 snippets, naturally fetching MORE).
- Per-run fetch budget lives in the `make_default_collect_fn(settings)` **closure** (a
  captured counter shared across that run's collect calls) — NOT in `RunState`, because
  `collect_fn` has no `RunState` access (its contract is `(query, *, cache, source_cap,
  mode)`). When exhausted, collection stops adding sources and the loop proceeds with
  what it has (honest partial, never a crash); a `fetch_budget_exhausted` trace is emitted.

## Error handling

- Every engine + Firecrawl + the LLM expansion follow the **never-raise** contract:
  failure logs a warning and degrades (empty results / template-query fallback / plain
  fetch). A collection step can never crash a run.
- Firecrawl disabled (no key) → step is a no-op; thin pages are simply dropped by the
  existing gate.
- Budget exhaustion and every thin-source drop emit trace events
  (`source_skipped`, and a new `fetch_budget_exhausted`) — no silent truncation.

## Testing (TDD, all offline via DI / mocked HTTP — no network, no key)

1. `query_expansion`: fake LLM returns N queries; assert N + dedup; LLM raises →
   fallback `[base_query]`; cache hit avoids second LLM call.
2. `search` providers: mock Tavily/Brave HTTP → correct preview shape; HTTP error →
   `[]` (never raises); `parallel_search` merges all engines and tags `engine`.
3. `dedupe_and_rank`: exact-URL dedup; per-domain cap; quality ranking — an
   authoritative source (official) ranks above a forum/web source; a new
   registrable domain gets the independence bonus; a URL surfaced by 2 engines ranks
   above 1; a typo-squat host near the competitor's official domain (e.g.
   `feiishu.com.cn` vs `feishu.cn`) is penalized below a genuine independent source;
   top-K truncation; stable/deterministic order.
4. `firecrawl_fetch`: mock Firecrawl success → FetchResult; API error/no key → None
   (never raises).
4b. `analyst` verbatim-evidence prompt: given a fake LLM, the built prompt instructs a
   verbatim snippet per cited source; a claim whose snippet is copied from the source
   raw_text passes the existing grounding/value_unsupported checks at round 0, while a
   paraphrased/absent snippet is rejected (proves the prompt change feeds the gate,
   not bypasses it).
5. `fetch_with_fallback` Firecrawl path: plain fetch thin → Firecrawl invoked → rich
   text returned; Firecrawl also thin → still thin (gate drops downstream).
6. tier mapping: `tier_for("quick"|"detailed"|"bogus")` → expected knobs (+ warning on
   bogus).
7. `collect_node` integration (fake collect_fn replaced by the real pipeline with
   mocked engines/fetch): a field yields many deduped sources; per-domain diversity
   holds; fetch budget caps total.
8. Regression: existing collect/loop tests stay green (gate disabled when
   `settings=None`; deep-collect knobs only active with real Settings).

## Non-goals (explicit)

- No LLM synthesis of findings or report prose (writer stays a pure projection).
- No LLM cross-engine relevance filter (deterministic dedup/rank only).
- No confidence decimals; scoring.py (3-tier) is unchanged.
- No vendoring of LDR modules; no headless-browser dependency in-process (Firecrawl is
  a remote API).
- No change to the QA rules, route logic, schema registry, or scoring.

## Rollout / risk

- Default `depth=quick` keeps current demo latency roughly comparable while adding
  breadth; `detailed` is opt-in for thoroughness.
- Each engine/Firecrawl degrades independently — partial availability never breaks a run.
- Build incrementally (engines → expansion → dedup → fetch fallback → orchestration →
  API/tier wiring), each task TDD + reviewed, so the suite stays green throughout.
