# AGENTS.md — MingJing 明镜 Design & Theory

This is the single, comprehensive reference for **how MingJing is designed and *why***.
It is written for two audiences: contributors (human or AI) working in this repo, and
reviewers who want the intellectual case behind the system. Practical build/run commands
live in [README.md](README.md) and [docs/deployment.md](docs/deployment.md); per-field code
conventions live in [CLAUDE.md](CLAUDE.md). This file is the *thinking*.

---

## 0. One sentence

> **MingJing is an evidence-*admissible* competitive-analysis runtime: the LLM proposes,
> deterministic code adjudicates, and evidence decides what is allowed into the report.**

The soul sentence we defend it with: **"它知道自己什么时候不该自信"** — *it knows when it
should not be confident.* A conclusion only reaches the report if it can be traced, verbatim,
to a source that cleared a non-LLM admissibility bar. Everything below is in service of that.

---

## 1. The central design stance

**The LLM proposes, deterministic code adjudicates, evidence decides.**

No conclusion enters the report unless it clears an *admissibility* bar enforced entirely in
non-LLM code (`src/mingjing/qa/rules.py`). The verdict can never be talked-into by a
hallucinating model, because the gate reads **only the source text and the claim structure**
— never the model's self-assessment.

Three consequences fall directly out of this stance:

1. **The gate is the moat, not the model.** Because admissibility is provider-agnostic by
   construction, swapping the LLM cannot change what passes. We run the high-hallucination
   stress model **MiniMax-M2.7** as the default *precisely to prove this*, and verified the
   identical gate behaviour on the contest's **Doubao-Seed-2.0-lite** (full run `33835db0`,
   18 `llm_calls` all on the official endpoint). Same admission semantics, two models.
2. **Sparse-but-true beats full-but-fabricated.** The Writer is a pure projection of
   QA-passed claims. A thin report with four defensible conclusions is the *correct* output;
   a full-looking report with one fabricated number is a failure.
3. **Defensibility is a property, not a slide.** Tiers are plain-language rules with no
   confidence decimals, so a judge can ask *"re-run it?"* and get a consistent answer.

---

## 2. Architecture at a glance

### 2.1 The graph loop (LangGraph `StateGraph`, `src/mingjing/graph.py`)

```
(discover) → intake → plan → collect → analyze → qa → route ─┬→ write → synthesis → END
                        ↑                                     │
                        └──────── revise (collect | analyze) ─┘
```

- **Reject path:** `route → revise → back to collect or analyze`, bounded by a round cap.
- **Two build modes:** `build_graph()` is a compile-only skeleton for tests (terminates at
  `write → END`); `build_graph(deps=GraphDeps(...))` is the live loop with real agents (adds
  the `synthesis` node).
- **Dual entry:** **Directed Mode** (competitors supplied → straight to `intake`) and
  **Discovery Mode** (empty competitors + a `category` → a bounded `discover` pre-step in
  `discovery.py` that selects *which* competitors enter the loop, and **never feeds search
  previews into evidence or claims**).

### 2.2 The four scored agents (`src/mingjing/agents/`)

| Agent | Role | Pure? |
|-------|------|-------|
| **Collector** | web search → robots check → SSRF-guarded fetch → evidence chunks | no (I/O) |
| **Analyst** | one LLM call per (competitor, field); `<UNTRUSTED>` prompt-injection envelope | no (LLM) |
| **QA** | 7 deterministic verifier check families → 6 IssueCodes (no LLM) | **yes** |
| **Writer** | pure projection of QA-passed claims into the report template | **yes** |

There are **exactly four scored agents.** Orchestration/post-processing nodes
(`discover`, `intake`, `plan`, `route`, `revise`, `synthesis`) are deliberately *not* counted
among them. This separation is load-bearing: the multi-agent collaboration axis is judged on
real specialised agents, not on a node count inflated with plumbing.

### 2.3 State & dependency injection

- **`RunState`** (`graph.py`) — a field-keyed, append-only `TypedDict`. List fields (`tasks`,
  `sources`, `claims`, `qc_reports`) use LangGraph additive `operator.add` reducers
  (concurrent-safe deltas); scalars are last-write-wins. It stays serializable.
- **`GraphDeps`** — a dependency-injection carrier (`db`, `cache`, `settings`, `collect_fn`,
  `analyze_fn`). Live nodes close over it; tests inject fakes (no network, no API key). This
  is what makes the full suite runnable offline.

---

## 3. The trust mechanics (the invariants that make it honest)

These are not features; they are *guarantees enforced in code and pinned by tests.*

### 3.1 Evidence-admissible gate
The admissibility bar in `qa/rules.py`. Seven deterministic check families emit six
`IssueCode` values:

| IssueCode | Detects |
|---|---|
| `SCHEMA_GAP` | a required sub-field is missing (also reused for inference-lineage gaps) |
| `WEAK_EVIDENCE` | too few independent registrable domains / no authoritative source |
| `CONTRADICTION` | cited sources disagree (surfaced, never silenced) |
| `HALLUCINATED_SNIPPET` | a cited snippet is **not** a verbatim substring of its source |
| `LOW_COVERAGE` | not enough of the schema's required fields are covered |
| `VALUE_UNSUPPORTED` | a structured value's leaf is not present in the cited source text |

`WEAK_EVIDENCE` / `CONTRADICTION` verdicts derive **only** from structured metadata
(registrable domains, authoritative source types, per-source stance enums, JSON signatures).
The gate never asks an LLM for a free-text conclusion, so an injected instruction cannot flip
a verdict.

### 3.2 Projection invariant
`render_report()` (Writer) is pure and deterministic — *no LLM call*. It templates rows only
from the QA-passed set; any `claim_id` not in that set is silently dropped. **The report can
never contain an unbacked claim.** Unit-tested in `tests/test_writer_projection.py`.

### 3.3 Honest weak→strong
The per-field source cap grows with the revision round: **`source_cap = 1 + revision_round`**
(`graph_nodes.py`). Round 1 collects up to 1 source and may produce a *weak* claim. After a QA
rejection and a `RevisionTask`, round 2 collects up to 2 — **genuinely new fetches, not data
that was held back** — and the transparent tier rule re-scores. weak→strong is a real
re-collection loop, never a staged reveal.

### 3.4 Verbatim-or-reject (citation soundness)
`claim_builder.snippet_for` returns the analyst's candidate snippet **unchanged**; the
`HALLUCINATED_SNIPPET` gate (verbatim substring of `raw_text`, whitespace-normalized, no
lowercasing) is the **sole arbiter**. *Span-grounding* — substituting a non-verbatim snippet
with a best-overlap source span — was proposed and **rejected twice as unsound** (both
BLOCKING in review; removed in commit `4bcb1ec`). The reasoning: token-overlap cannot
distinguish a genuine reworded paraphrase (which may share as little as the competitor name)
from an outright fabrication — both sit in the same low-overlap region, so any substitution
either masks fabrications behind real source text or false-rejects honest paraphrases. There
is no safe threshold. The honest invariant: **citations are real source text, or they are
rejected and re-collected.** This directly targets the well-documented Deep-Research weakness:
citation *link* validity >94% but citation *fact* accuracy only 39–77%.

### 3.5 QA routing on evidence-gap
The mechanism that makes the live weak→strong loop actually work (commit `18211c8`). Because
`source_cap` only grows when a rejection routes to the **Collector**, an evidence-gap routed
to the *analyst* would just re-run on the same insufficient evidence and stall. So:
- `SCHEMA_GAP` / `VALUE_UNSUPPORTED` / `WEAK_EVIDENCE` / `CONTRADICTION` / `LOW_COVERAGE`
  → **Collector** (an evidence gap → fetch *more* evidence).
- `HALLUCINATED_SNIPPET` → **Analyst** (a real fabrication, not an evidence gap).

The verdict stays metadata-computed (injection-proof); only routing changed; bounded by
`route()`'s `round >= cap` check (no infinite loop). Impact: the live MiniMax demo went from
1/5 → 4/5 fields passing, coverage 0.2 → 0.8.

### 3.6 Abstention over fabrication
When evidence is insufficient, a claim is **explicitly withheld** (`VALUE_UNSUPPORTED`, kept
as a draft and disclosed) rather than fabricated — Anthropic's *"give the LLM a way out"*
principle, which roughly halves hallucination (arXiv 2404.10960). Withheld claims appear in
the UI with their issue code; nothing is silently deleted.

### 3.7 Simulated data buys no credibility
Simulated survey/interview rows are badged `SIMULATED` and `scoring.contributes_to_tier`
**excludes them from all credibility math** — tiering, corroboration counts, contradiction
detection. An integration test pins that a conclusion supported *only* by simulated data is
rejected. *"Rather a weaker tier from real evidence than a strong tier bought with synthetic
data."*

### 3.8 Append-only persistence
Claims are **never `UPDATE`d.** Each revision is a new row with `version++`; a revised claim
supersedes by version and the full history is preserved. The human-correction channel writes
into the *same* append-only chain (`produced_by = human:correction`).

### 3.9 `repair_delta` + the real-closed-loop seal
`repair_delta` is the paired-comparison groundedness gain from reject→re-collect (e.g. **+42%**
on flagship `4fff4227`). The *真闭环确认 / tier-upgrade* seal lights **only** when
`repair_delta ≥ 5%` AND a tier upgrade actually occurred; if **0 claims are admitted, the seal
and the speedup UI extinguish** (a reverse-honesty invariant). It is deterministic QA/scoring
output, never model self-grading.

---

## 4. The theory layer (intellectual lineage)

MingJing's design is deliberately grounded in established Competitive-Intelligence (CI) and
intelligence-analysis practice. The framing below is the *design basis* — the principled
answer to "why is it shaped this way"; where the running code is a simpler, transparent
projection of a concept, that is stated plainly (we don't claim machinery we didn't build).

### 4.1 Modeling thesis — a *CI-trained AI analyst team*
The product is framed not as "AI that writes competitor reports" but as **a team of AI
analysts trained in Competitive Intelligence.** The deliberate consequence: **depth lives in
domain semantics, not in orchestration.** There is no added concurrency, no dynamic DAG, no
heavier runtime — the original LangGraph skeleton is preserved on purpose. This is the correct
reading of *"process complexity should match task complexity"*: the sophistication is in how
evidence and claims are modeled, judged, and graded — not in how the agents are wired.

### 4.2 Source grading — dual-axis (Admiralty Code / ICD-203 lineage)
Evidence strength is conceived as two axes — **source reliability** (independent registrable
domains, official/survey/authoritative types) and **information credibility** (verbatim
grounding, cross-source corroboration vs contradiction) — the same split codified by the NATO
Admiralty Code (STANAG 2511) and ICD-203. *Implemented* as the transparent three-tier rule
(**strong / moderate / weak**) with **no confidence decimals**: we show bands, never fake
precision, and we grade over evidentiary lineages rather than raw document counts. (We do not
claim the full A-F/1-6 letter-code machinery; the disciplined two-axis *idea* is what shapes
the rule.)

### 4.3 Claim ontology — Toulmin model + typed claims
Claims carry a **`claim_type` of `fact` or `inference`**, in the spirit of the Toulmin
argument model (claim / grounds / warrant / qualifier / rebuttal). Synthesis claims cite the
claims they rest on via a `based_on[]` link, so a derived conclusion inherits a traceable
basis from its supporting evidence rather than being asserted flat. This split is also the
*honest ceiling* (see §4.6).

### 4.4 QA as a Quality-of-Information check
The QA stage is modeled as a **Quality-of-Information** check, not a generic LLM grader: a
relevance + sufficiency judgment that detects source-independence/circular-reporting groups
and **surfaces** contradictions (a contradiction lowers confidence *and* is shown — never
hidden). This squarely addresses the Multi-Agent System Taxonomy (MAST) finding that
*verification* is a first-class failure domain, and the LangChain/Google-Cloud consensus that
*"judging only the final output misses bad reasoning"* — hence trajectory-level **QA Replay**.

### 4.5 Analytic output conventions
The analyst output follows intelligence-community conventions: a **BLUF** (Bottom Line Up
Front) brief, explicit *"so what"* recommendations tied to decisions, **intelligence-gap**
statements that name what is *not* known, and a Key-Assumptions posture. Confidence is
communicated in plain bands, never decimals.

### 4.6 The positioning theory — *verification-for-governance*
- **Verifier's Law** (Jason Wei, 2025 — the asymmetry of verification): verification is
  fundamentally easier than generation. MingJing's deterministic admission gate sits on the
  correct side of this law — reframing the gate from "a conservative engineering choice" into
  "standing on a recognized law."
- **Verification-for-GOVERNANCE vs verification-for-IMPROVEMENT (the moat).** The entire
  2025–26 frontier uses verifiers to make agents *score higher* (verification-for-improvement).
  MingJing uses a verifier as an auditable **admission gate** for trustworthy delivery —
  verification-for-**governance**. Same principle (Verifier's Law), opposite purpose. The
  precise blank nobody else fills: welding together (1) information-asymmetric blind
  verification, (2) claim-typing (fact → hard gate / inference → confidence label),
  (3) verdict-by-deterministic-code, and (4) a quantified repair-delta, into a demoable
  enterprise CI workbench. RAG-QA does (1)(3) but single-turn, untyped; commercial CI does
  citation (贴源) not verification (盲验+准入); academia has the principle but serves *score*,
  not governance.
- **The honest ceiling — fact/inference asymmetry as a feature.** Verification-asymmetry only
  holds for easily-verifiable **fact** claims. Inference claims (e.g. *"the pricing reflects
  down-market ambition"*) are genuinely unverifiable, so the system **labels their confidence
  and never fake-verifies them.** Knowing this boundary is precisely what stops MingJing from
  becoming a new *伪闭环* (fake closed loop).

### 4.7 Information-asymmetric adjudication
QA sees only the **evidence text and the claim structure** — never the analyst's reasoning.
If the evidence doesn't stand, it is bounced — rather than accepting a re-worded explanation.
This blindness is the root of why the closed loop is *real* and not theatrical.

---

## 5. Subsystems

- **Scoring** (`scoring.py`) — transparent 3-tier (strong/moderate/weak) from distinct
  registrable domains + authoritative source types + a contradiction flag. No confidence
  decimals. `contributes_to_tier()` is the single chokepoint that excludes simulated data.
- **Schema / domains** (`schema_registry.py`, `domains/`) — a **schema-as-domain-profile**: the
  domain JSON encodes both the fields a competitor must be analysed on *and* source-type
  weights. "可换行业" (generalize to a new industry) is answered as **supplying a new profile,
  not re-coding the engine.** Selected per-run via a `ContextVar` (`use_domain()`), so analyst
  and QA both read the active domain. Default 5 fields: `feature_tree`, `pricing_model`,
  `user_persona`, `user_sentiment`, `swot`.
- **Persistence** (`db/` package) — single-file SQLite, **WAL + `busy_timeout=5000ms`**, with a
  module-level `_WRITE_LOCK` that serializes *all* access on one shared connection
  (`check_same_thread=False`). This is single-writer discipline, not concurrent reads;
  per-thread connections are a deliberate roadmap item, not a claim. Append-only tables.
- **Collector internals** (`collector/`) — `search` (keyless/trusted providers, all failures
  non-fatal), `fetch` (`is_safe_url()` SSRF guard re-validated on every redirect hop; thin
  sources dropped), `robots` (pre-fetch `robots.is_allowed`, disallowed URLs never fetched),
  `independence` (registrable-domain dedupe), `cache` (always re-tags `CACHED`, never disguised
  as live).
- **Observability** (`trace.py`, `trace_events.py`) — typed `trace_events` (node_enter,
  collect/analyze start/done, `qa_pass`, `qa_fail` (one per issue), revise start/done,
  run_complete/partial, synthesis start/done) streamed via `GET /runs/{id}/trace?since=N`
  (2-s poll); plus an `llm_calls` table (model, prompt, output, tokens — **API key redacted at
  write time**) exposed at `GET /runs/{id}/llm_calls`. This is the observability requirement,
  satisfied at the trajectory level.
- **Bounded live research** — live-first by default with automatic, transparent downgrade to
  read-only cache on timeout/HTTP-error/exception; `prewarm.prewarm_all` warms every
  (competitor × field) URL so the first judge-selected run hits warm compute. Finite
  `llm_timeout_s` so a stuck provider raises instead of hanging the run.

---

## 6. Honest boundaries (deliberately *not* built)

Stated plainly, because honesty is the product:

- **No RAG / vector DB.** Grounding is whitespace-normalized verbatim substring containment +
  exact-token `Decimal` matching — deliberately avoiding the approximation/hallucination
  surface of embedding similarity.
- **Metrics are proxies, not truth.** `strong_rate` / `repair_delta` / `coverage` are
  *evidence-strength* proxies, explicitly **not** factual accuracy. Factual correctness still
  needs human spot-check or gold data. We never claim "true," only "traceable and verifiable."
- **Run-level concurrency scheduler** — deferred (search-level concurrency exists; run-level
  safety is tested, a worker-pool scheduler is roadmap).
- **Dynamic schema evolution, voting/self-eval, real LangSmith deep-link** — all deferred and
  *not claimed as built.*
- **"Supported by sources verbatim" ≠ "true about the world."** Sources can be wrong; that is
  why strength is graded on two axes and cross-source contradictions are detected and flagged.

---

## 7. Repo map

```
src/mingjing/
├── graph.py / graph_nodes.py   # LangGraph wiring + live node factories
├── runner.py                   # production run executor + discovery pre-step
├── discovery.py                # Discovery-Mode competitor selection (bounded)
├── config.py                   # Settings (Pydantic, frozen, from env)
├── schemas.py / schema_registry.py   # domain models + per-run domain switching
├── scoring.py                  # 3-tier evidence strength + contributes_to_tier
├── llm.py                      # OpenAI-compatible client + JSON repair
├── api.py                      # FastAPI (read-only views + POST /runs)
├── agents/{collector,analyst,qa,writer}.py
├── collector/{search,fetch,robots,independence,cache}.py
├── qa/{rules,route}.py         # deterministic checks + pure router
├── trace.py / trace_events.py  # observability
├── survey.py / survey_seed.py  # 问卷/访谈 evidence lane (PII-scrubbed)
└── domains/                    # field schema definitions per industry
frontend/                       # React 19 + Vite + TS workbench
mingjing-video/                 # standalone Remotion demo-video project
```

---

## 8. Working in this repo (conventions for contributors & agents)

1. **Never weaken the gate to make a demo pass.** If a claim won't admit, that is the system
   working. Fix the evidence path, not the verdict.
2. **The QA verdict is metadata-computed and must stay LLM-free.** Do not introduce an LLM
   call into `qa/rules.py` — it would reopen the prompt-injection surface.
3. **Preserve the invariants:** projection (writer emits only passed claims), append-only
   (no `UPDATE` on claims), verbatim-or-reject (no span substitution), simulated-excluded
   (`contributes_to_tier`).
4. **Honesty over polish in docs.** If something is deferred or a proxy, say so. Stale claims
   that contradict reality are treated as bugs.
5. **Verify before commit:** `make test` (883 backend) + `cd frontend && npx vitest run`
   (314) + `npx tsc -b` (use `-b`, not `--noEmit`). No source file over 800 lines.
6. **Test offline by injecting fakes via `GraphDeps`** — never require a network or API key
   for the suite.

> See [docs/architecture.md](docs/architecture.md) and
> [docs/agent-protocol.md](docs/agent-protocol.md) for the wiring detail,
> [docs/COMPLIANCE.md](docs/COMPLIANCE.md) for the safety posture, and
> [docs/SELF-AUDIT.md](docs/SELF-AUDIT.md) for the honest gap-by-gap self-score.
