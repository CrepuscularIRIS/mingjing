# MingJing — Frontend Workbench + Value-Add Plan (2026-05-31)

> **For agentic workers:** execute task-by-task via subagent-driven-development.
> Steps use checkbox (`- [ ]`) syntax. **Plan, then implement — get user approval first.**

**Goal:** Turn the test-proven backend (314 green) into a judge-facing **competitive-analysis
workbench** and complete the organizer-confirmed value-add items, so the 35% (可信度) and
20% (产品体验) axes become *visible and clickable*, not just test-passing.

**Authority for priorities:** the 开题答疑逐字记录 in `Competition.md` (organizer's own words),
not just the scoring table. Re-read 2026-05-31.

**Demo scenario (locked):** 竞品分析 of **通用 AI Agent 产品** (organizer's own example,
151/193 行) — e.g. comparing several general AI-agent products. Familiar data, public info,
judges know the space.

**Tech stack (locked, all already installed):** React + Vite + TS + Tailwind +
`reactflow` (DAG) + `recharts` (KPI/charts). 2s polling reading SQLite. **No SSE/WebSocket.
No chat-style templates (CopilotKit / Agent Chat UI). No shadcn.** Hand-built Tailwind components.

---

## Definition of Done — the ACCEPTANCE GATE (governs everything)

No new idea (concurrency / dynamic-DAG / anything not below) gets a line of code until EVERY
box here is green. Each box maps to a scoring weight; verify by tests/live-demo, not by feeling.

```
□ Frontend 5(or merged-4) tabs clickable, jump-to-source works, insights visible   ← 35% visibility
□ weak→strong + QA-打回 demoable live (judge picks the competitor, not a planted one)
□ 业务指标条 (覆盖率/引用率/人工修正率/耗时 vs 人工) on screen                        ← organizer-named
□ dynamic schema option-1 (config-driven 换领域) demoable
□ real survey N≈30 + 脱敏 ; one live collection at demo open
□ LangSmith connected + DAG 执行轨迹 tab
□ Doubao key ROTATED with organizers (rotation, not just purge — ROADMAP Task 0)
□ README / 架构图 / Agent 协议文档 / 部署文档 complete
□ full demo 录屏 recorded (organizer-endorsed stability insurance)
□ demo runs in offline/cache mode, 6 min no stutter
```

**Until all-green: dynamic DAG = forbidden (archive only); concurrency = forbidden except a
post-all-green lightweight "dual-run" demo. See `docs/ROADMAP.md` → Evolution path.**

---

## What is ALREADY done (do not rebuild)

- Backend: full LangGraph loop, 4 agents, QA gates, traceability, `llm_calls`, **314 tests green**,
  live E2E proven (298s < 360s), pluggable SearXNG search, value gate, retry, per-field queries.
- **Human-in-the-loop correction endpoint** `POST /runs/{id}/claims/{cid}/correct` — DONE (`2a8e65d`),
  reviewed-approved. Frontend button is part of Phase 1 below.
- Frontend shell: top-tab (report / qa-replay / observability), left run-form + ActivityFeed,
  `usePolling`, `api/client.ts`, components: `EvidenceDrawer`, `QAReplayFlow`, `StrengthTally`,
  `ClaimRow`, `InsightCard`, `SourceProvenanceTag`, `RevisionTaskChip`, `Badge`.
- Views: `FinalReport.tsx`, `QAReplay.tsx`, `Observability.tsx` (+ vitest for each).

## ARCHIVED — organizer's words killed these (mention as "演进路径" in 答辩 only)

- ❌ Dynamic/runtime DAG topology, AgentSwarm concurrency — "并发非强制, nice to have" (156/204 行).
- ❌ LLM-adaptive runtime field proposal — dynamic schema is config-driven only (154/197 行).
- ❌ The `_CLAIM_ROW_KEYS` DRY consolidation (rejected) — leave as-is; revisit only if it bites.

---

## Architecture: the Workbench

Left nav + top KPI bar + main area. Single page, polling. 5 tabs (③④ MAY merge if time-tight → 4):

```
┌────────────┬──────────────────────────────────────────────┐
│ 明镜工作台   │ KPI bar: 覆盖率 / 引用率 / 人工修正率 / 耗时vs人工 │
│ ▸ 分析报告  │ ┌──────────────────────────────────────────┐ │
│ ▸ Schema矩阵│ │           active tab main area             │ │
│ ▸ 证据&溯源 │ │                                            │ │
│ ▸ QA回放    │ │                                            │ │
│ ▸ 执行轨迹  │ └──────────────────────────────────────────┘ │
└────────────┴──────────────────────────────────────────────┘
(run-control + ActivityFeed move into a collapsible "运行" drawer/panel)
```

| Tab | Content | Hits | Priority |
|---|---|---|---|
| ① 分析报告 (facade) | 3–5 key insights; pricing/feature/persona/SWOT tables; **每条结论点击→跳源高亮**; v1/v2 switch; **人工修正按钮(accept/reject/edit)** | 20% + 35%溯源 | **P0** |
| ② Schema 矩阵 | rows=competitors × cols=schema fields; cell=strength badge / red gap; **"换领域"下拉** proves extensibility | 35% + 20%扩展 + 25% | **P0** |
| ③ 证据&溯源 | left claim / right evidence; source-type + relevance badges; jump-to-source; survey-evidence subpanel | 35% | P1 |
| ④ QA 回放 | timeline of each QA round: verdict/issues/RevisionTask/弱→强 | 35% (core loop) | P1 |
| ⑤ 执行轨迹 (eng view) | `reactflow` DAG, nodes colored by agent + status, revise red dashed back-edge; click node → prompt/IO/token; **LangSmith external link** | 25%/35% | P1 |

③④ merge option: one page, left claim-evidence + right that-claim's QA history (弱→强 in same screen).

---

## Phase 0 — Backend support endpoints (small, unblock the frontend)

### Task A: Business-loop metrics endpoint  *(was Task 26)*
**Files:** Create `src/mingjing/metrics.py` (pure compute) · Modify `src/mingjing/api.py` (add `GET /runs/{id}/metrics`) · Test `tests/test_metrics.py`
- [ ] Pure `compute_metrics(claims, llm_calls, sources, trace_events, intake)` returns:
  - `coverage` = passed_fields / required_fields
  - `citation_rate` = claims-with-≥1-supporting-evidence / total passed claims (引用率)
  - `human_correction_rate` = claims whose latest `produced_by == "human:correction"` / total claims
  - `strong_rate` = strong / passed (准确率 proxy, transparent)
  - `efficiency` = `{elapsed_s, source_count, llm_calls, total_tokens}` (耗时 vs 人工 baseline shown in UI as a static reference, not computed)
- [ ] Endpoint reads DB (latest_claims, llm_calls_for_run, sources, run row) and returns the dict; 404 if run missing.
- [ ] Tests: a seeded run with 1 human-corrected + N claims asserts each metric value.
**Acceptance:** `GET /runs/{id}/metrics` returns the 4 organizer-named metrics + efficiency; full suite green.

### Task B: Schema registry (config-driven 换领域)  *(dynamic schema, option 1)*
**Files:** Create `src/mingjing/schemas/registry.py` + `src/mingjing/schemas/domains/*.yaml` (or `.json`) · Refactor `schemas.py` `FIELD_SCHEMAS` to load from the active domain · `GET /schemas` + `GET /schemas/{domain}` endpoints · Test `tests/test_schema_registry.py`
- [ ] A domain file declares its field schemas (required/sub_fields). Ship 2: `ai_agent` (default, the demo
      domain — pricing_model/feature_tree/user_persona/user_sentiment/swot) and `hr` (人事 AI, organizer's
      example — e.g. integration_matrix/pricing_model/compliance/user_persona) to PROVE 换领域.
- [ ] `FIELD_SCHEMAS` resolves from `MINGJING_SCHEMA_DOMAIN` env (default `ai_agent`); existing code that
      imports `FIELD_SCHEMAS` keeps working (back-compat: default domain == today's 5 fields).
- [ ] Endpoint lists domains + returns a domain's schema (frontend 换领域 dropdown reads this).
- [ ] Tests: registry loads both domains; default domain byte-matches today's FIELD_SCHEMAS; unknown domain → clear error.
**Acceptance:** swapping `MINGJING_SCHEMA_DOMAIN=hr` changes the field set with zero code edits; suite green.
**Risk guard:** this touches the load-bearing `FIELD_SCHEMAS` — keep default identical; run the FULL suite.

### Task C: LangSmith trace integration (organizer-named)
**Files:** Modify `src/mingjing/graph.py` (no-op if env unset) · `.env.example` (+ `LANGCHAIN_*`) · `docs/OBSERVABILITY.md` · small `tests/test_langsmith_optional.py`
- [ ] LangGraph auto-traces to LangSmith when `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` +
      `LANGCHAIN_PROJECT` are set. Add a tiny `configure_tracing()` that reads env and is a NO-OP when
      unset (so offline/CI and the demo's air-gapped path are unaffected — our own `trace_events` stay
      the live-stable main).
- [ ] Doc: how to enable, and that LangSmith is the *endorsement* layer; the self-built DAG (tab ⑤) is the
      live-demo main. Capture a screenshot for 答辩 materials.
- [ ] Test: with env unset, the graph builds/invokes exactly as today (no import-time LangSmith requirement).
**Acceptance:** env set → runs appear in LangSmith; env unset → identical behavior; suite green.

### Task D: Survey design + anonymization (minimal real)  *(was Task 27, compliance-focused)*
**Files:** `src/mingjing/agents/collector.py` or new `src/mingjing/survey.py` (`design_survey`) · reuse `ingest.py` anonymization · `GET/POST` survey endpoint · `tests/test_survey_design.py`
- [ ] `design_survey(competitor, goal, n=8, settings)` → LLM-generated structured questionnaire matching the
      shape `ingest.py` already consumes; deterministic test mocks the LLM.
- [ ] Emphasis = **脱敏**: a real (synthetic N≈30) sample ingested through `anonymize_respondent_meta`;
      a test proves PII (names/email/phone) is stripped (10% compliance axis).
**Acceptance:** survey questions generate; ingested responses are anonymized; suite green.

---

## Phase 1 — Frontend Workbench (P0 first: 分析报告)

> Start here per organizer priority. Each task: add view/component + vitest. Match existing Tailwind style.

### Task E: Shell restructure — left nav + KPI bar
**Files:** `frontend/src/App.tsx` · new `frontend/src/components/KpiBar.tsx` · `frontend/src/api/client.ts` (+ `getMetrics`, `correctClaim`, `getSchemas`) · `frontend/src/api/types.ts`
- [ ] Convert top-tab → left-nav with 5 items; move run-form + ActivityFeed into a collapsible "运行" panel.
- [ ] `KpiBar` polls `/runs/{id}/metrics` (2s) → 覆盖率/引用率/人工修正率/耗时, with a static "vs 人工 baseline" caption.
- [ ] vitest: nav switches tabs; KpiBar renders metric values from a mocked client.

### Task F: ① 分析报告 facade (jump-to-source + insights + correction)  **← the single most important UI step**
**Files:** enhance `frontend/src/views/FinalReport.tsx` · reuse `EvidenceDrawer`, `InsightCard`, `StrengthTally`, `ClaimRow` · new `frontend/src/components/CorrectionControls.tsx`
- [ ] Top: 3–5 InsightCards (key takeaways). Below: per-field tables (pricing/feature/persona/SWOT).
- [ ] **Every claim row → click → EvidenceDrawer opens the cited source, highlights the snippet** (use
      `lib/highlight.ts`; consume the new `url#p:N` locator to scroll to paragraph if present).
- [ ] **CorrectionControls** (accept / reject / edit) call `correctClaim(...)`; on success refetch report
      (the human override appears as a new version; KpiBar's 人工修正率 ticks up).
- [ ] v1/v2 version switch per claim (claim-history endpoint already exists).
- [ ] vitest: clicking a claim opens the drawer with the right source id; correction calls the endpoint and
      refetches; edit submits statement+value.
**Acceptance:** a judge can read insights, click any conclusion to its source, and correct a claim — live.

### Task G: ② Schema 矩阵 (+ 换领域)
**Files:** new `frontend/src/views/SchemaMatrix.tsx` · uses `getSchemas` + report claims
- [ ] Grid rows=competitors × cols=active-domain fields; cell = strength badge (强/中/弱) or red "缺口".
- [ ] Top-right "换领域" dropdown (reads `/schemas`); switching shows the field set changing — the
      extensibility proof. (Switching domain for a *new run* uses `MINGJING_SCHEMA_DOMAIN`; in-UI it
      demonstrates the schema set, the headline 答辩 point.)
- [ ] vitest: matrix renders cells from mocked report + schema; gap cells flagged.

### Task H: ⑤ 执行轨迹 DAG (reactflow) + LangSmith link  (fold in Observability)
**Files:** new `frontend/src/views/ExecutionTrace.tsx` (reactflow) · reuse `Observability` content + `QAReplayFlow` patterns
- [ ] Static DAG (intake→plan→collect→analyze→qa→route→{revise↺|write}); nodes colored by agent, status
      from trace events; revise = red dashed back-edge. Click node → prompt/input/output/token (from
      `/llm_calls` + trace). External "Open in LangSmith" link (if configured).
- [ ] vitest: nodes render; clicking a node shows its llm_call detail from mocked data.

### Task I: ③+④ Evidence & QA (merged page acceptable)
**Files:** `frontend/src/views/QAReplay.tsx` (exists) + new `Evidence.tsx` OR a merged `EvidenceAndQA.tsx`
- [ ] Left: claim → its evidence (source-type + relevance badges, jump-to-source). Right: that claim's QA
      history (verdict/issues/RevisionTask, 弱→强). Same-screen "弱 claim 打回→补强" story.
- [ ] vitest: selecting a claim shows its evidence + QA history.

---

## Phase 2 — Demo materials (process, not code)

### Task J: 录屏 + 答辩 (organizer-endorsed stability insurance, 149/190 行)
- [ ] One clean full run recorded (cache_first safe path) as the submission video.
- [ ] Live demo script: key interactions + **one** live collection (organizer said "单独展示采集能力").
- [ ] 答辩 deck: architecture, the 5 visible proofs, LangSmith screenshot, "演进路径" (the archived items).
- [ ] **Doubao key rotation confirmed with organizers** (ROADMAP Task 0) BEFORE submission.
- [ ] MiniMax→Doubao config switch verified (rotated key) on the demo machine.

---

## Sequencing (ROI order, organizer-driven)

1. **Phase 0 Task A (metrics)** + **Task E (shell+KPI)** + **Task F (报告 facade)** — the visible core. ← do first
2. **Task B (schema registry / 换领域)** + **Task G (Schema 矩阵)** — extensibility proof.
3. **Task C (LangSmith)** — cheap endorsement.
4. **Task H (DAG tab)** + **Task I (evidence+QA)** — engineering + loop visibility.
5. **Task D (survey + 脱敏)** — compliance.
6. **Phase 2 (录屏/答辩/rotation)** — submission.

Each backend task: TDD + full-suite-green gate. Each frontend task: vitest + `tsc -b` + `vite build` clean.
After all: final review → finishing-a-development-branch (push to the private remote branch, not main).

## Open question for the user before execution
- Phase 1 frontend depth: confirmed **"功能可用、演示够用"** (functional, not pixel-polish)?
- ③④ merge into one page (saves a view), or keep separate?

---

# Engineering detail (LDR-researched, 2026-05-31)

Concrete, modeled spec per task. Sources: LDR deep-research (RAGAS/agent-eval, AI-agent &
HR-AI market, official LangSmith docs, reactflow v11/12 API, survey/PII methodology); where
live web returned nothing the subagents used training knowledge and said so.

## Task A — metrics.py (research-grounded formulas)
Compute 5 MVP metrics, all from EXISTING data (no gold labels):

| Metric (CN/EN) | Formula | Source fields | "Good" |
|---|---|---|---|
| 覆盖率 Coverage | `passed_fields / required_fields` | latest claims status=pass vs intake.fields | ≥0.90 |
| 引用率 Citation/grounding | `claims_with_≥1_evidence_source / passed_claims` (≈ RAGAS faithfulness, claim-level) | evidence_json source_ids | ≥0.85 |
| 强证据率 Strong-evidence (准确率 PROXY) | `strong_claims / claims_with_any_evidence` | evidence_strength tier | ≥0.60 |
| 人工修正率 Human-edit | `claims latest produced_by=="human:correction" / total claims` | produced_by | ≤0.10 |
| 效率 Efficiency | `{elapsed_s, source_count, llm_calls, total_tokens}` + static manual baseline | run row, sources, llm_calls | — |

- **Accuracy proxy honest caveat (MUST render in UI + report):** "强证据率 is necessary-not-
  sufficient for factual accuracy — it measures each claim has a strong evidence link, not that
  the evidence is correct. Supplement with a human spot-check of ≥20 sampled claims." (Do NOT
  claim it as 准确率 outright; label it 强证据率(准确率代理).)
- **Efficiency framing (static caption, cited as estimate):** manual multi-competitor analysis ≈
  16–40h (senior CI analyst; Crayon/Klue practitioner benchmarks) → "5 竞品 × N 维度 < N 分钟 vs
  人工约 16–40 小时 (≈60–160× 提速)". Present as an *estimate*, not a measured claim.
- `compute_metrics(...)` is PURE (no I/O); endpoint `GET /runs/{id}/metrics` reads DB and calls it.

## Task B — schema registry (back-compat-safe)
- **Default domain stays the current 5 fields** (name it `saas`/`default`) so all 314 tests pass
  byte-identically (the load-bearing constraint). `ai_agent` + `hr` are ADDITIONAL domains.
- **`ai_agent` (demo domain)** — 8 fields, agent-specific (the 前瞻性 differentiator):
  `pricing_model`(req: tiers, billing_unit — per-seat vs per-task vs outcome),
  `autonomy_level`(req: autonomy_tier [Copilot→Autopilot], hitl_requirement),
  `capability_matrix`(req: primary_task_domains, benchmark_scores [SWE-bench/GAIA/WebArena]),
  `integration_ecosystem`(req: protocol_support [MCP/A2A], native_connectors),
  `model_backbone`(req: primary_llm, context_window_tokens),
  `safety_guardrails`(req: prompt_injection_defense, audit_logging),
  `user_sentiment`(req: overall), `swot`(req: strengths, weaknesses).
- **`hr` domain** — 5 fields: `integration_matrix`(req: supported_hris_platforms, sync_type),
  `compliance_certifications`(req: security_certifications, ai_regulatory_status [EU AI Act / NYC LL144]),
  `pricing_model`(req: primary_billing_unit [PEPM], tiers), `deployment_model`(req: available_topologies,
  default_topology), `user_persona`(req: primary_personas, buyer_persona).
- **CRITICAL design guard:** keep each field's `required` list to **1–2 robustly-extractable
  sub-fields** (the full rich `sub_fields` are optional). The VALUE_UNSUPPORTED gate + SCHEMA_GAP
  only check `required`; an over-long required list would make live AI-agent runs over-reject to
  partial. Rich sub_fields = aspiration, required = the demo-safe floor.
- `FIELD_SCHEMAS` resolves from `MINGJING_SCHEMA_DOMAIN` (default = the 5-field domain). Run FULL suite.

## Task C — LangSmith (exact, env-gated no-op)
- **Current env vars:** `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`,
  `LANGSMITH_ENDPOINT` (EU). (`LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_PROJECT` are
  deprecated-but-working.) Unset ⇒ fully silent, zero overhead.
- **Our reality:** plain-function StateGraph + DIRECT `openai` SDK calls do NOT auto-appear as
  spans. Fix = ONE line in `llm.py`: `client = wrap_openai(openai.OpenAI(...))` (from
  `langsmith.wrappers`), guarded so when tracing env is unset it's a no-op (wrap_openai itself is
  a no-op then, but keep import lazy/guarded for the air-gapped path). Optionally `@traceable` on
  `call_llm`/nodes for named child spans.
- Judges see: run tree rooted at `graph.invoke`, per-node latency, per-LLM-call model/tokens/cost/
  messages. Use as the endorsement layer + 答辩 screenshot; our reactflow DAG stays the live main.
- Test: env unset ⇒ graph builds/invokes identically (no LangSmith import requirement at import time).

## Task D — survey + anonymization (concrete)
- **`design_survey` → 10-Q template** (dims): Q1 qualification(single), Q2 satisfaction(Likert5),
  Q3 feature-sat(Likert5), Q4 NPS(0-10), Q5 NPS-rationale(open, pii_scrub), Q6 feature-gaps(multi),
  Q7 switching-intent(single), Q8 willingness-to-pay(single, CNY), Q9 switching-barrier(single),
  Q10 open-feedback(open, pii_scrub). JSON: `{survey_id,competitor,questions:[{id,dimension,type,
  text,options?,scale?}],response_schema}`.
- **Anonymization (no heavy NER):** regex email `\S+@\S+\.\S+`→[EMAIL]; CN+intl phone
  `1[3-9]\d{9}`/`0\d{2,3}-\d{7,8}`→[PHONE]; CN ID `\d{17}[\dXx]`→[ID]; name = trigger-phrase
  (`我叫|我是|my name is|I'm`)+context + ~150 common CN surname denylist + titles→[NAME]; 6-digit
  postal→[ZIP]; age `(\d{1,3})\s*(岁|years old)`→bucket. k=3 check on (role,industry,size) for the
  N≈30 set. Only scrub the open-text fields (Q5,Q10); structured meta already via `anonymize_respondent_meta`.
- **Compliance proof test:** inject a canary response with known PII; assert (1) no email substring,
  (2) no phone substring, (3) no name substring, (4) `pii_tokens_redacted>=3`, (5) placeholder tokens present.

## Task H — execution-trace DAG (reactflow, concrete)
- `nodeTypes={agentNode,orchNode}` defined OUTSIDE the component (Gotcha 1). Node `data`:
  `{label, role, agentColor, status:'pending'|'running'|'done'|'flagged', visitCount, llmCallId}`.
- Manual layout (8 nodes, fixed topology — no dagre): intake(300,0) plan(300,100) collect(300,200)
  analyze(300,300) qa(300,400) route(300,500) revise(100,400 — left of spine) write(500,500).
- Back-edge revise→collect: `type:'smoothstep', pathOptions:{offset:-80}, markerEnd:ArrowClosed,
  strokeDasharray:'5,3', label:'↺ revise'`.
- `onNodeClick`→side panel fetching `/llm_calls` detail. `fitView({padding:0.2})` once on mount.
- Gotchas: (1) stable `nodeTypes` ref; (2) poll updates via `setNodes(prev=>prev.map(... {...n,data:{...n.data,status}}))` — never mutate in place; (3) `fitView` only on mount, never per-poll-tick.
- Fold the existing `Observability` (llm_calls/token view) content into this tab's detail panel.

## Sequencing note
Phase 0 (A,B,C,D backend) can run before/in parallel with Phase 1 frontend, but the frontend
KPI bar (E) needs A's endpoint, Schema Matrix (G) needs B's `/schemas`, DAG tab (H) needs C's
LangSmith link. Build order within Phase 0: A → B → C → D (D is independent, can slot anywhere).
