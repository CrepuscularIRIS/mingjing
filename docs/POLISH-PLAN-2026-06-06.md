# MingJing 打磨计划 / Polish Workflow

> Date: 2026-06-06 · Branch: `feature/mingjing-w1-core` (not merged)
> Deadline: **submit 6/10** · 答辩 6/12–19
> Companion docs: `GAP-2026-06-06.md` (original gap audit), `SEARCH.md` (search layer).
> This file is the **execution workflow**: every GAP is a node with a severity, a
> scoring-axis rationale, file anchors, and a phase. Phases run top-to-bottom;
> tracks inside a phase can run in parallel.

---

## 0. Session status snapshot (what is already DONE)

| Area | State |
|---|---|
| Live web search | ✅ FIXED. Was 0 results; now Bocha + SearXNG(Bing) return on-topic sources. |
| Query expansion | ✅ FIXED reasoning leak (`<think>` was parsed as queries) + widened (5/8 sub-queries, top_k 8/12) + bilingual source-type prompt. |
| Retrieval relevance | ✅ ADDED query-token relevance bonus in `dedupe_and_rank` (on-topic now beats authoritative-irrelevant). |
| Snippet-as-evidence | ✅ Candidate pool decoupled from fetch cap; ranked tail becomes evidence via search snippet (no fetch). Budget-safe even when fetches fail. |
| SearXNG | ✅ Up via Docker on `:8888` (`deploy/searxng`), CN backends (Bing/Baidu). |
| Test suite | ✅ 664 passed, ruff clean. |

Everything below is **still open**.

---

## 1. GAP inventory

Severity: 🔴 blocking · 🟠 high (scores points) · 🟡 medium · ⚪ low/polish.
Owner: **U** = needs the user (keys, recording, decisions) · **A** = I can do it.

| ID | GAP | Sev | Axis | Owner | Files / anchor |
|----|-----|-----|------|-------|----------------|
| G1 | **LLM provider = MiniMax, competition mandates Doubao-Seed-2.0-lite** | 🔴 | ⑤合规 | U+A | `config.py:87-89`, `.env` |
| G2 | **6-min 演示录屏 not recorded** (the demo vehicle) | 🔴 | ⑤材料 | U | — |
| G3 | **Demo run must force ≥1 reject→revise** so `repair_delta` lights up green | 🔴 | ⑤+① | U+A | run selection / seed |
| G4 | **Frontend rebuild** (Vite + shadcn/ui), preserve 10 hero experiences | 🟠 | ②+③ | A | `frontend/` |
| G5 | Snippet-as-evidence QA tuning: short snippets may over-trip `VALUE_UNSUPPORTED` | 🟠 | ①+② | A | `qa/rules.py`, scoring |
| G6 | KPIs reframed to **"verified claims gained"** (not source count) | 🟠 | ③ | A | `KpiBar.tsx`, metrics |
| G7 | Quantified **human-analyst baseline** (16–40h → X min; 准确率/覆盖率/人工修正率) | 🟠 | ③ | U+A | docs + metrics |
| G8 | Live **end-to-end rehearsal** with Doubao, ≤6 min wall-clock | 🟠 | ② | U+A | `make demo-*` |
| G9 | Mount `Observability` view (built, tested, **unreachable**) | 🟡 | ② | A | `App.tsx:37` |
| G10 | DAG missing `synthesis` node (graph is `write→synthesis→END`) | 🟡 | ①口径 | A | `ExecutionTrace.tsx` |
| G11 | QA-Replay **numeric before→after delta** (evidence_strength/groundedness) | 🟡 | ① | A | `QAReplayFlow.tsx` |
| G12 | Source provenance badge: **SNIPPET vs FETCHED** (new, from this session) | 🟡 | ①溯源 | A | `SourceProvenanceTag.tsx`, drawer |
| G13 | Contradiction **global** count badge (not only per-selected claim) | 🟡 | ① | A | `EvidenceAndQA.tsx` |
| G14 | 问卷/访谈 lane more **visible** + labeled demo-data | 🟡 | ①题目 | A | survey card, FinalReport |
| G15 | Docs lag code: `architecture.md`/`agent-protocol.md`/`ROADMAP.md` | 🟡 | ④ | A | `docs/` |
| G16 | Required deliverables: 架构图, Agent 协议文档, 部署说明 | 🟡 | ④ | A | `docs/` |
| G17 | Doubao **key rotation** (account-side, with organizers) | 🟡 | ⑤ | U | — |
| G18 | PII free-text names not NER-removed; add robots/合规声明 | ⚪ | ⑤ | A | `ingest.py`, docs |
| G19 | TRAE / AI-coding 使用痕迹 captured/framed | ⚪ | ④ | U | git/TRAE |
| G20 | SearXNG flaky engines (brave/baidu timeout); Volcengine engine deferred | ⚪ | ② | A | `deploy/searxng/settings.yml`, `search.py` |

---

## 2. Execution workflow

```
PHASE 0  Compliance-blocking      (G1, G17)            ── must finish first
   │
PHASE 1  Backend correctness      (G5, G20)  ║  PHASE 1' Frontend rebuild (G4 → G9–G14)
   │      + live rehearsal (G8)              ║          (starts when templates arrive)
   │
PHASE 2  Business narrative       (G6, G7)
   │
PHASE 3  Docs & materials         (G15, G16, G18, G19)
   │
PHASE 4  Demo capture             (G3, G2)  ── must finish last (records the result)
```

Backend (Phase 0–2) and Frontend (Phase 1') are **parallel tracks**. The 录屏
(Phase 4) is gated on everything because it films the finished product.

### PHASE 0 — Compliance-blocking (do first)
- **G1 Doubao switch.** Point `MINGJING_LLM_BASE_URL` at Volcengine Ark, set the Doubao model id + key. Re-verify the live JSON/`<think>` path (`llm.py`), then a live `POST /runs`. ~0.5 day. *Blocks G8, G3, G2.*
- **G17 Key rotation.** User action with organizers (repo scrub already done).
- **Gate:** a live run completes on Doubao with real tokens logged.

### PHASE 1 — Backend correctness (parallel with Frontend)
- **G5 Snippet QA tuning.** Snippets are short (90–800 ch); confirm `VALUE_UNSUPPORTED` / `HALLUCINATED_SNIPPET` don't over-reject snippet-grounded claims (raw_text == snippet keeps substring honest, but value-leaf checks may bite). Add a test; relax only if it over-rejects.
- **G20 Search robustness.** Disable flaky SearXNG engines (brave/baidu) in `settings.yml`, keep Bing; (optional) wire Volcengine once you paste an Ark 联网内容插件 sample.
- **G8 Live rehearsal.** `MINGJING_DEPTH=detailed` run on Doubao, measure wall-clock ≤6 min, pre-warm demo competitors.
- **Gate:** a detailed live run yields 大量 on-topic sources, terminal status, ≤6 min.

### PHASE 1' — Frontend rebuild (parallel; starts when reference pages arrive)
See §3. Rebuild on **Vite + shadcn/ui**, preserve every hero experience, then fold in G9–G14 as part of the rebuild (they're cheap once the shell is good).
- **Gate:** the demo journey is legible end-to-end (report → claim → evidence → QA reject→repair delta → DAG → domain switch).

### PHASE 2 — Business narrative
- **G6** Reframe KPI headline to "原 1/5 通过 → 打回后 4/5 通过 / verified claims gained".
- **G7** Add the human-baseline number + 准确率/覆盖率/人工修正率 tiles. Confirm HITL 人工修正 actually feeds back into a run (real reverse-channel, not just UI).
- **Gate:** KpiBar tells a quantified efficiency story, not raw counts.

### PHASE 3 — Docs & materials
- **G15** Sync `architecture.md` (add synthesis/Evidence-Admissible/domain), `agent-protocol.md` (`VALUE_UNSUPPORTED`), `ROADMAP.md` (views are not stubs).
- **G16** Write 架构图 + Agent 角色与协议文档 + 部署说明 (incl. the new search/SearXNG setup).
- **G18** PII NER pass + a one-line robots/服务条款 合规声明.
- **G19** Capture TRAE / AI-pairing records; frame git history as AI-assisted.
- **Gate:** rubric ④/⑤ document checklist complete.

### PHASE 4 — Demo capture (last)
- **G3** Pick/seed a run that gets ≥1 claim rejected then repaired (else `repair_delta = +0%` and "真闭环确认" stays dark).
- **G2** Record the 6-min 录屏 on the finished product + a single-cut 采集 segment.
- **Gate:** a clean 6-min video exists, closed-loop number lights up green.

---

## 3. Frontend rebuild detail (G4) — Vite + shadcn/ui

**Decision locked:** stay Vite SPA, add **shadcn/ui (Radix + Tailwind)**. Do NOT copy
DeerFlow (Next.js chat console — wrong IA). Target a **data-dense analyst/BI workbench**
template (single left sidebar, top command bar, card+table density, drawer, flow canvas).

**Hero experiences the rebuild MUST preserve** (all backend endpoints already exist):

| Experience | Endpoint | Axis |
|---|---|---|
| Final Report: BLUF→SWOT→comparison→recommendations→gaps, every sentence `[c1]`-cited | `/runs/{id}/report`, `…/synthesis` | 35%+20% |
| Evidence & 溯源: click claim → drawer → highlighted snippet → LIVE/CACHED/**SNIPPET** badge + 可靠性 | `/sources/{id}` | 35% |
| QA Replay (money shot): reject → re-collect → strengthen, **numeric before→after** | `/runs/{id}/claims/{cid}/history` | 35% |
| Execution Trace DAG incl. **synthesis** node + per-node LLM/token | `/runs/{id}/trace` | 25% |
| Schema Matrix: competitor×field, strength-colored, domain-switchable | report + `getSchemas()` | 题目+20% |
| Observability: token/latency/budget per node (**mount it**) | trace + `llm_calls` | 25% |
| Credibility: `repair_delta` headline + "真闭环确认" banner | `/runs/{id}/credibility` | 35% |
| KPI bar: "verified claims gained" | metrics | 20% |
| 问卷/访谈 design card + survey-source chips | `/runs/{id}/survey-design` | 题目 |
| Correction controls (人工修正 HITL) | existing | 20% |

**IA fixes to bake in:** one left sidebar (run controls + nav merged); ledger
default-open; animate trace arrivals to feel streaming; single language (CN) for
labels; SNIPPET vs FETCHED provenance badge in the evidence drawer.

API client to keep: `createRun, getTrace, getReport, getSynthesis, getCredibility,
getClaimHistory, getSource, getSchemas, getSurveyDesign` (`api/client.ts`).

---

## 3a. Reference libraries (the visual bar: 无与伦比 / world-class)

The rebuild's look is sourced from two vendored libraries in `/home/lingxufeng/Langgraph/UI`
(both React + Tailwind + Framer Motion → drop-in on the Vite + shadcn/ui base):

- **Magic UI** (`UI/magicui`) — `border-beam, magic-card, bento-grid, animated-beam,
  animated-list, number-ticker, shine-border, blur-fade, text-animate, marquee,
  terminal, shimmer-button, dock, animated-gradient-text, dot-pattern,
  flickering-grid, particles, ripple, scroll-progress`.
- **React Bits** (`UI/react-bits`, use the **`ts-tailwind`** variant) —
  `Animations / Backgrounds / Components / TextAnimations`.

**Bar:** every screen must look intentionally designed, not admin-template. Motion
on state change, depth/elevation, a real type system, zero "AI slop". Polished
enough that a judge's first impression is "this is a product," before they read a
word.

### Component → hero-experience mapping (concrete, not decorative)

| Hero experience | Magic UI / React Bits component | Why |
|---|---|---|
| App shell / dashboard | `bento-grid`, `dot-pattern`/`flickering-grid` bg | dense, intentional layout |
| Final Report BLUF + cited sentences | `text-animate`, `blur-fade`, `highlighter` | report reads as it resolves; citations pop |
| KPI bar ("verified claims gained") | `number-ticker`, `animated-gradient-text` | quantified story animates, not static |
| Credibility "真闭环确认" banner | `shine-border` / `border-beam` (green) | the 35% money moment glows when repair_delta>0 |
| Execution Trace DAG | `animated-beam` between nodes, `animated-list` feed | multi-agent orchestration feels alive/streaming |
| Evidence drawer + provenance | `magic-card`, badges (LIVE/CACHED/**SNIPPET**) | each claim's evidence as a crafted card |
| QA Replay before→after delta | `number-ticker` (strength), `shine-border` on pass | the reject→repair→pass moment is unmistakable |
| Schema matrix | `magic-card` cells, strength color ramp | competitor×field grid, premium feel |
| Observability charts | shadcn charts + `scroll-progress` | token/latency/budget, mounted at last |
| CTA / run button | `shimmer-button` / `interactive-hover-button` | the one primary action stands out |
| Activity feed | `animated-list`, `marquee` (recent runs) | live trace arrivals animate in |

Use motion with restraint: animate on **state change and arrival**, never idle
loops behind text. Keep it fast (the 25% observability axis is about responsiveness).

---

## 3b. Build workflow — drive to product-grade (Opus 4.8 + gstack + superpowers, Codex acceptance)

> The user will issue a `/workflow`-style command to execute this. This section is
> the contract that run must honor. Model: **Opus 4.8 throughout.**

**Loop per frontend slice (one hero experience at a time):**

1. **Plan** — `superpowers:brainstorming` + `superpowers:writing-plans` to scope the
   slice against §3 (data contract) and §3a (visual bar). No code before the plan.
2. **Build** — implement on Vite + shadcn/ui, composing the §3a components. Wire to
   the real API client (no mock data). `superpowers:test-driven-development` for logic;
   Vitest for components.
3. **Self-QA (live)** — `gstack` headless browser: navigate the slice, screenshot,
   diff before/after, check console/network, responsive. `design-review` for visual
   polish (spacing, hierarchy, slop, slow interactions).
4. **Verify** — `superpowers:verification-before-completion`: run the app, observe the
   real behavior, capture evidence. Backend stays green (`make test`).
5. **Acceptance (Codex)** — the configured **stop hook calls Codex CLI** to review the
   slice. Treat findings with `superpowers:receiving-code-review` (verify, don't
   blind-comply). Fix, re-run, until Codex passes.
6. **Commit** — Conventional Commits, one slice per commit.

**Order of slices** (each shippable on its own): App shell/IA → Final Report →
Evidence & 溯源 → QA Replay (delta) → Execution Trace DAG → Credibility/KPI →
Schema Matrix → Observability (mount) → 问卷/访谈 card → Correction (HITL).

**Definition of done (per slice):** real data wired · §3a visual bar met · gstack
screenshot attached · Vitest + `make test` green · Codex acceptance passed.

**Guardrails:** no mock data in the demo path; never lose a hero experience from §3;
keep `tsc -b` clean (verify the frontend with `tsc -b`, NOT `tsc --noEmit`); don't
weaken backend QA invariants to make a screen look richer.

---

## 3c. Stylish Effects — 无与伦比 bar, curated for a *credible* workbench

Source of effects: `/home/lingxufeng/Langgraph/UI` — **React Bits** (`ts-tailwind`
variant: `Animations/ Backgrounds/ Components/ TextAnimations`) and **Magic UI**
(`apps/www/registry/magicui`). Pull liberally from here so the UI feels world-class.

**The governing principle (read before adding any effect).** MingJing's whole pitch
is *可信度* (the 35% axis). The UI must look like a **premium intelligence /
BI workbench an analyst trusts** — Linear / Vercel / Bloomberg-terminal energy —
**not** a flashy landing page. A carnival of WebGL backgrounds would actively
*hurt* the score: it reads as a toy, not a system of record. So: maximal craft,
restrained motion. Every effect must reinforce "this is rigorous," never undercut it.

### Approved palette (use these — mapped to surface + the axis it serves)

| Surface | Effect (React Bits / Magic UI) | Axis it serves |
|---|---|---|
| Global background (very subtle, static-ish) | `DotGrid` / `dot-pattern`, or `Aurora`/`SoftAurora` at low opacity behind the shell only | 20% 体验 — depth without noise |
| Brand wordmark / hero title | `ShinyText`, `GradientText`/`aurora-text` (one accent, not rainbow) | 20% 体验 — first-impression polish |
| KPI numbers ("verified claims gained", repair_delta) | `CountUp` / `number-ticker` | 20% 体验 + 35% — the quantified story animates |
| 真闭环确认 credibility banner (repair_delta>0) | `StarBorder` / `border-beam` / `shine-border` in **green**, fired once on reveal | **35% — the money moment** |
| Final Report BLUF + cited sentences | `BlurText`/`SplitText`/`text-animate` on arrival, `highlighter` on citations | 35% 溯源 — report resolves, citations pop |
| Evidence / provenance cards | `SpotlightCard`/`magic-card`/`BorderGlow`, LIVE/CACHED/**SNIPPET** badges | 35% — each claim's evidence as a crafted card |
| Execution Trace DAG | `animated-beam` between nodes, `AnimatedList`/`animated-list` for the live feed | 35% 协作 — orchestration looks alive |
| QA Replay weak→strong | `CountUp` on strength delta + green `shine-border` on pass | 35% — reject→repair→pass is unmistakable |
| Schema matrix cells | `magic-card`/`PixelCard` (subtle), strength color ramp | 25%/20% — premium grid |
| Primary run CTA | `shimmer-button`/`StarBorder`/`interactive-hover-button` (exactly one) | 20% — the one action stands out |
| Observability charts | shadcn charts + `scroll-progress`, `AnimatedContent` reveal | 25% — responsiveness reads as engineering depth |
| Empty / loading states | `FadeContent`, `AnimatedContent`, skeletons | 20% — no dead/blank screens |

### Blacklist (do NOT use — they break the credibility thesis)

`Balatro, Ballpit, Galaxy, Hyperspeed, LiquidChrome, LiquidEther, Plasma,
PrismaticBurst, MetaBalls, Ferrofluid, Lightning, Iridescence, Dither, Orb,
Ribbons, SplashCursor, BlobCursor, GhostCursor, ImageTrail, Cubes, Lanyard,
ModelViewer`, and every cursor-follower / game-physics background. Reason: they
scream "demo toy," tank perf on a 录屏, and contradict "trustworthy analyst tool."

### Restraint rules (non-negotiable)

- Motion on **state change & arrival only** — never idle loops running behind data.
- Honor `prefers-reduced-motion`; effects degrade to a clean static state.
- One "wow" per screen, max. The 真闭环确认 glow is the protagonist; everything
  else supports it.
- 60fps on the demo machine; if an effect janks the 录屏, cut it. Responsiveness
  is itself the 25% observability signal.
- Background effects sit **behind** content at low opacity and never reduce text
  contrast below WCAG AA.

---

## 3d. 最终产品打磨 — 中文输出 + 内在质量 (intrinsic quality)

### 中文优先 (judges are Chinese — the artifact must read like a 中文 analyst wrote it)

- **All LLM-facing prompts that produce user-visible content output 简体中文** —
  the analyst field extraction, the synthesis (BLUF / SWOT / 对比 / 建议 / 情报缺口),
  QA rejection rationales, withheld-claim explanations. The final report a judge
  reads must be fluent, professional Chinese — this is 硬伤#2 (the artifact must
  look like a pro report). English-in, Chinese-out is fine; the *deliverable* is 中文.
- **Keep English** for: code identifiers, schema field keys (`pricing_model`…),
  log/trace internals, API contracts, commit messages. Don't translate machinery.
- UI chrome stays bilingual as today (中文 primary labels, English sublabels) — it
  already reads well; don't regress it.
- When editing a prompt, re-run a live sample and eyeball the Chinese for AI-slop
  (启动 writing-anti-ai mindset): no "值得注意的是", no robotic hedging, BLUF-first.

### 内在质量 (the 10% 代码质量 axis + general craft — judged on reading the repo)

- **Code:** files 200–400 lines (800 hard max); types on all signatures; no dead
  code / unused exports; factory/registry where it fits; explicit error handling;
  no `console.log` / `print` debug; small focused modules.
- **Tests:** keep the suite green every commit (frontend Vitest + `tsc -b` + eslint;
  backend `make test`); add tests for new logic, not just UI.
- **History:** one Conventional Commit per slice, message explains the *why*; every
  commit shippable.
- **Docs:** README + 架构图 + Agent 协议 + 部署说明 kept in sync (G15/G16); the repo
  should be legible to a judge skimming it in 5 minutes.
- **Output quality is product quality:** a polished screen wrapping a thin/garbled
  report still loses. The report's *content* (grounded, cited, honest weak→strong)
  is the real deliverable — never trade it for visual richness.

---

## 4. Minimal critical path (if time runs short)

If only a few things get done, do these — they protect the score floor:
1. **G1** Doubao (else 合规 fail + wrong answer live).
2. **G3 + G2** a 录屏 where the closed-loop number lights up (the 35% proof, on camera).
3. **G4** frontend rebuild — at minimum the Final Report + Evidence + QA-Replay tabs.
4. **G6** KPI reframed to verified-claims-gained.

Everything else is additive.

---

## 5. AutoPilot mode — decide without blocking the user (Codex as tiebreaker)

Default posture going forward: **keep moving; do not stop to ask the user.** When a
decision is genuinely ambiguous, hand it to **Codex** for a ruling and proceed —
only a narrow class of actions escalates to the human. Three tiers:

**Tier A — decide yourself (most decisions).** Anything resolvable from the plan,
the codebase, the rubric, or a sensible default. Pick the obvious option, state it
in one line, proceed. Don't manufacture questions.

**Tier B — let Codex decide (ambiguous, but reversible & in-scope).** Design/impl
trade-offs, which §3c effect fits, how to structure a component, scope reading
*within* this plan, resolving a Codex review finding you partly disagree with.
Mechanics:
- Invoke Codex (`codex exec` / the `codex-rescue` path) with the question + the
  relevant context + the options you see, and ask for a decision **with a reason**.
- Adopt its ruling **unless it violates a hard guardrail or this plan** (then note
  the conflict and override with justification). Record the decision in the commit
  body or a one-line note so it's auditable.
- This is the same Codex already wired as the stop-hook reviewer — here it's also
  the tiebreaker, so the loop stays unblocked.

**Tier C — escalate to the user (rare).** Only for things Codex must not unilaterally
do:
- **Compliance / account / external:** the G17 Doubao key rotation with organizers,
  anything needing real credentials, account changes, 答辩/提交 logistics.
- **Irreversible or outward-facing:** `git push`, deploys, deleting data, sending
  anything to an external service.
- **Scope/spend changes beyond this plan:** new features not in the GAP list, or
  abandoning a hero experience.

**Inviolable even in AutoPilot** (neither you nor Codex may relax these): no mock
data on the demo path; never weaken backend QA / evidence / PII / robots /
credibility invariants; honest weak→strong; `tsc -b` (not `--noEmit`); every commit
green + shippable. These are the spine — AutoPilot speeds up *how* we decide, never
*what* we're allowed to ship.

---

## 5. Post-launch QA findings (2026-06-06, live MiniMax + 飞书 case)

> Found while bringing up the live system and running a real **飞书** competitor case
> against MiniMax (run `1327ade10b30484b9181885404dbb8ac`). Recorded as new GAPs.
> Sev legend as above (🔴 blocking · 🟠 important · 🟡 polish · ⚪ minor · ✅ done).

| ID | Finding | Sev | Axis | Owner | Files / anchor |
| --- | --- | --- | --- | --- | --- |
| G21 | **Live-collection grounding gap → empty report on JS-gated / CN competitors.** A live 飞书 run completed the full pipeline (37 sources, 16 MiniMax calls, 72.8k tokens, intake→…→synthesis) but QA admitted **0 claims**: `claim_admission_rate 0.0`, empty report, `repair_delta -0.297`, `run_partial`. Dominant rejections: **HALLUCINATED_SNIPPET ×7** ("snippet not found in source") + **VALUE_UNSUPPORTED ×3** (e.g. pricing tiers `120元`/`企业版`/`旗舰版`/`企业邮箱…` not literally in cited sources). Cause = thin live evidence (飞书 sites are JS-gated SPAs / 403 to the default UA) **×** MiniMax analyst **paraphrasing / filling from memory** instead of quoting verbatim. **The QA gate is correct — this is the no-fabrication thesis, not a bug** — but it yields an unshowable empty report on live CN runs. | 🟠 | ①+② | A+U | `agents/analyst.py` (verbatim-quote prompt), `collector/*` (CN fetch), `qa/rules.py` |
| G21a | Mitigation — **analyst verbatim discipline**: tighten the analyst prompt so the cited `snippet` MUST be a verbatim span of the source `raw_text`, and structured `value` leaves MUST be literally present in cited sources (no memory-fill). Lowest-risk lever; helps every model. | 🟠 | ①+② | A | `agents/analyst.py` |
| G21b | Mitigation — **CN live collection quality**: make Bocha the CN-primary at higher candidate breadth, consider a headless/JS-render fetch path or UA handling for SPA/403 targets so live CN competitors return groundable text (no robots/SSRF weakening). | 🟡 | ② | A | `collector/search.py`, `collector/fetch.py` |
| G21c | Mitigation — **Doubao quotes more verbatim** than MiniMax in spot checks → would ground more on live runs. Ties to G1/G17 (Phase 0, blocked on Ark key). Re-run the 飞书 case on Doubao once unblocked before judging live-collection quality. | 🟡 | ⑤+① | U+A | `.env`, `config.py` |
| G22 | **`/runs/{id}` returned `status: None`** for a run created via `scripts/run_demo.py` (run-metadata/status not set on that path). No UI impact (frontend derives terminal state from `run_complete`/`run_partial` trace events), but the field should be consistent for API consumers. | ⚪ | ④ | A | `api.py` get-run, `runner.py`/`run_demo.py` |
| G23 | ✅ **DONE — trace-event duplicate React keys.** Observability + ExecutionTrace appended polled trace events raw (no dedup); React StrictMode double-invoked the poll effect → full event set appended twice → ~35 "two children with the same key" console errors in Observability's per-agent list. Fixed by routing both appends through `mergeTraceEvents` + regression test. Commit `4e8be34`. | ✅ | ②/③ | A | `views/Observability.tsx`, `views/ExecutionTrace.tsx`, `lib/trace.ts` |

**Not-a-bug notes (no action, recorded for 答辩 honesty):**
- Evidence drawer cited-chunk highlight (`<mark>`) is absent when the claim text isn't a
  substring of the source — intended 3-tier `findHighlight` fallback (raw text still shown), not a break.
- Pre-existing React Flow `nodeTypes`/`edgeTypes` dev **warning** (not an error) remains; benign, memoization-only.
- The ~5% EvidenceAndQA test-harness race is tracked separately (test stability, not demo path) — see the
  session task list `#16`; live Evidence view is browser-verified working.

**Verification reference (this session):** full 6-tab browser sweep + interactions = 0 console
errors after G23 fix; `npx tsc -b` / `npm run lint` clean; `npx vitest run` **201 passed**;
`npm run build` ok. Fresh `make demo-reliable` (Notion) = 18 real MiniMax-M2.7 calls,
repair_delta 0.3, real synthesis. Curated Notion run `969e744c…` = full 4/5 brief
(use it to showcase a populated report until G21 lands / Doubao unblocks the live CN path).
