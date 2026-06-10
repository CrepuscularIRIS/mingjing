# MingJing 夺奖打磨研究报告 (Award-Level Polish Strategy)

> Cited research synthesis. Date 2026-06-06. Branch feature/mingjing-w1-core.
> Method note: a deep-research fan-out surfaced 25 sourced claims across 7 angles; the
> harness's automated 3-vote verify step failed to emit structured verdicts (a tooling
> bug, not genuine refutation), so this report grounds each recommendation in the cited
> sources + direct knowledge of the MingJing codebase rather than the tool's
> auto-verified output. Sources are listed inline as [S#] and collected at the end.
> Every recommendation is tagged with the scoring axis it serves:
> **[35]** trustworthy multi-agent & credibility · **[25]** engineering completeness ·
> **[20]** business/product value · **[10D]** docs/code quality · **[10C]** compliance/materials.

---

## 1. Executive summary

The judges are scoring **trust first** (35% credibility + closed loop). The research
converges on one theme: *a credible agent product wins by making its work inspectable and
its corrections grounded in external evidence, not by looking flashy.* Three evidence-backed
levers matter most for MingJing:

1. **Evidence coverage is the headline metric, not a vanity KPI.** A 2026 release-gate
   study found *evidence coverage* was the single most predictive signal for catching severe
   regressions — removing it would have shipped both severe-failure builds [S3]. MingJing's
   deterministic QA gate + "verified claims gained / coverage" KPIs are exactly the right
   spine; lead the demo with them. **[35][20]**
2. **Grounded self-correction is the moat.** Intrinsic (model-only) self-critique is
   unreliable and can *degrade* output because generator and evaluator share error modes;
   real gains come from correction anchored in external verification (execution-grounded
   self-correction hit 70.3% in one study) [S4]. MingJing's reject→recollect→re-verify loop
   is the academically-correct design — say this out loud in 答辩. **[35][25]**
3. **Provenance must be granular AND low-friction.** Claim-to-evidence provenance (vs flat
   document citations) lets users verify specific assertions [S2], and citations should point
   to *exact passages/timestamps*, not whole documents [S6]. But the same research warns
   granular provenance can *clutter* the UI and even *lower* trust if it adds cognitive load
   [S2][S6]. So: keep the click-to-snippet drilldown, but default to a clean brief and reveal
   provenance on demand. **[35][20]**

The product is already 90% there (6-tab workbench, honest weak→strong, full provenance). The
remaining award-level gap is **demo legibility + the one live closed-loop money-shot**, plus
closing the live-collection grounding gap (G21) so a live run isn't empty.

---

## 2. Award-winning polish strategy (priority-ordered)

| # | Move | Why (cited) | Axis |
|---|------|-------------|------|
| P1 | **Lead every view with the closed-loop proof.** Make repair_delta + 真闭环确认 + "verified claims gained" the first thing on screen; treat evidence-coverage as the hero metric. | Evidence coverage is the most regression-predictive metric [S3]; provenance/citation raises perceived authority [S9]. | [35][20] |
| P2 | **Ship the one real reject→revise→pass run** (G3) so QA-Replay shows a numeric weak→strong delta on live data. Do NOT fake it. | Grounded, externally-verified correction is where real gains live [S4]; faked loops are the #1 credibility risk. | [35] |
| P3 | **Decision provenance end-to-end:** every claim → its sources → the exact highlighted snippet, every agent step → its trace span (duration, tokens, status). | Decision provenance is a named observability capability [S7]; spans w/ duration+tokens+status enable post-mortem [S8]; citations should point to exact passages [S6]. | [35][25] |
| P4 | **Observability that localizes failure + attributes cost.** Per-node token/latency, handoffs, and the revise back-edge must be visible. | Observability must capture handoffs + full graph because failures cascade across agent boundaries [S1]; its 3 benefits are localize-failure, traces→regression-tests, cost/latency attribution [S1]. | [35][25] |
| P5 | **Audience-specific, inverted-pyramid layout.** Status/targets on top, trends/comparison middle, raw evidence on demand. Answer the judge's top 2 questions in ~10s. | Inverted-pyramid hierarchy + the "10-second / top-2-questions" test [S5][S6]; dashboards must be built per audience [S5]. | [20] |
| P6 | **Close the live grounding gap (G21):** force the analyst to quote verbatim spans + only emit values literally present in sources; strengthen CN collection (Bocha-primary). | Otherwise live CN runs (e.g. 飞书) gate out every claim → empty report. The gate is correct; the inputs are thin. | [35][25] |
| P7 | **Professional 简体中文 report**, BLUF-first, source-cited each sentence. Kill any英文 leakage / AI-slop phrasing in the generated brief. | Reports presented as factual must cite exact passages [S6]; CN judges read the brief directly. | [20][10C] |

---

## 3. Judge-perspective product evaluation rubric (use as a self-scoring gate)

Score each 0–5; anything ≤3 is a polish target. Maps to the official 35/25/20/10/10.

**A. Trust & closed loop (35%)**
- A1 Can a judge click any conclusion → see its exact source snippet in ≤2 clicks? [S6]
- A2 Is there a *visible numeric* weak→strong improvement on a *real* run (repair_delta, source-count, tier)? [S4]
- A3 Does the QA gate visibly *reject* something and route it back (not just pass everything)? [S4]
- A4 Is "no fabrication" demonstrable — does an ungrounded claim get withheld rather than shown? [S3]
- A5 Are LIVE/CACHED/SNIPPET provenance + contradiction surfaced honestly?

**B. Engineering completeness (25%)**
- B1 Full agent DAG with the revise back-edge + synthesis node, lit by live status [S1][S7].
- B2 Per-node/agent token + latency + status spans [S8].
- B3 Traces could become regression tests (deterministic gate) [S1][S3].
- B4 Structured per-domain schema, switchable (前瞻性).

**C. Business/product value (20%)**
- C1 KPIs framed as outcomes (verified claims gained, coverage, accuracy proxy, manual-correction rate), not raw counts.
- C2 Human-analyst baseline contrast (machine seconds vs 16–40h estimate, labeled 估算).
- C3 10-second comprehension: top 2 questions answered immediately [S5].
- C4 HITL correction path that re-feeds the run.

**D. Docs/code quality (10%)** — architecture.md / agent-protocol / ROADMAP current; tests green; clean commits.
**E. Compliance/materials (10%)** — 合规声明 (robots/SSRF/PII honest), AI-assisted-dev evidence, Doubao mandate met, 6-min 录屏.

---

## 4. ClaudeCode Dynamic Workflow plan (final polish sprint)

Orchestration that matches the toolchain. One slice = plan → build → verify-in-browser → Codex gate → commit.

```
Per slice (dynamic workflow, focused subagents):
  1. Gstack /spec or superpowers:writing-plans  → a file-anchored slice plan
  2. 3-agent planning fan-out (contract / design / risk) → synthesize
  3. Implement sequentially in main session (subagent-driven where independent)
  4. Frontend Design + Figma MCP for any net-new visual surface (tokens, not pixels)
  5. VERIFY IN THE REAL APP: Playwright/Chrome DevTools drive the run, assert behavior,
     capture screenshots + console + network (NOT just tsc/tests) [S10][S11]
  6. End turn → Codex stop-hook review gate (GPT-5.5) → receiving-code-review (verify, don't blind-comply)
  7. One Conventional Commit; AgentMemory records the decision
Loop until the judge-rubric (§3) self-score has no ≤3.
```

Tool-to-job mapping (do not add a new agent framework — none of these need one):
- **Superpowers SDD** = the per-slice discipline (plan→tests→implement→verify-before-completion). [25][10D]
- **Gstack** = spec/plan + /design-review (AI-slop, spacing, slow motion) + /qa. [20][10D]
- **Playwright + Chrome DevTools MCP** = the judge-loop: actually use the app, read live DOM/console/network [S10][S11]. [35][25]
- **Figma MCP + Frontend Design** = consistent token-driven surfaces, not flashy one-offs. [20]
- **Codex review hook (GPT-5.5)** = independent second-opinion gate + Tier-B tiebreaker (already wired). [10D]
- **AgentMemory** = carries decisions/quirks across slices + shared with Codex. [10D]

---

## 5. Playwright / Chrome DevTools product-testing checklist (the judge loop)

Make the agent USE the product, not read code. Per the visual-feedback research, code-only review misses visual/UX defects; pair every check with a screenshot + live browser state (console/DOM/network) via MCP [S10][S11]. Drive a *real* run (no mock).

For each of the 6 tabs, on a real run id:
- [ ] Loads with **0 console errors**, all API calls **200**, **real data** (no mock).
- [ ] 分析报告: BLUF renders; click a citation chip → evidence drawer opens with the **exact highlighted snippet** [S6].
- [ ] 证据&溯源: claim → source rows → 查看原文 → LIVE/CACHED/SNIPPET badge + provenance; contradiction badge if any.
- [ ] QA 回放: a real claim shows weak→strong with a **numeric** before→after delta [S4].
- [ ] 执行轨迹: DAG shows采集→分析→质检→**打回重采(回边)**→撰写→综合; per-node token badge; click node → its LLM calls [S1][S8].
- [ ] 可观测: per-agent token chart + prompt/output with **secrets redacted** [S7].
- [ ] 人工修正: 采纳/驳回/编辑 re-feeds the run (produced_by=human:correction).
- [ ] Run-switch + reset: prior run's data never leaks under a new id.
- [ ] Reduced-motion honored; 60fps; no idle-looping animation behind text.
- [ ] Snapshot+refs interaction is robust (accessibility-tree refs, not fragile CSS) [S10].
- [ ] Capture mode discipline: verbose traces for debugging, quiet for the demo [S12].

---

## 6. Frontend rebuild / credibility checklist (BI workbench, not landing page)

- [ ] **Simplicity & consistency** — no clutter; every element earns its place [S5]. One type scale, one spacing scale, ink/mirror tokens only.
- [ ] **Inverted-pyramid hierarchy** per view — status/targets top, trends/compare middle, detail on demand [S6].
- [ ] **10-second test** — the top 2 questions ("is it trustworthy? what did it conclude?") answered immediately [S6].
- [ ] **Chart-to-intent** — line=trend-over-time, bar=compare-categories; no misleading dual axes / 3D / pie-for-trend [S6].
- [ ] **Provenance on demand** — granular claim-evidence available but not cluttering the default brief (it can lower trust / usability under time pressure) [S2][S6].
- [ ] **Calm credibility palette** — strength ramp (strong/moderate/weak), green only for the 真闭环 seal; no game-like WebGL / cursor-followers (they undercut the credibility thesis).
- [ ] **Professional 简体中文** throughout the generated brief; no英文 leakage, no AI-slop.
- [ ] Motion only on arrival/state-change; honor prefers-reduced-motion.
- [ ] Loading / empty / error / partial states are all deliberate (never blank).

---

## 7. Final 6-minute demo storyboard

| Time | Beat | Says (the trust thesis) | Axis |
|------|------|--------------------------|------|
| 0:00–0:30 | **Hook + KPI bar** | "明镜是可信的竞品情报分析师团队。每条结论可溯源，LLM 不裁定真值。" Point at 已验证结论 / 覆盖率 / 真闭环 +43%. | [35][20] |
| 0:30–1:45 | **分析报告 (BLUF→SWOT→建议)** | Read the bottom-line; click a sentence's citation chip → exact source snippet. "每句话可追溯。" [S6] | [35][20] |
| 1:45–2:50 | **QA 回放 money-shot** | Show a claim QA **rejected** → recollect → **pass**, with 来源 N→M · 弱→强 numeric delta. "这是真闭环，不是伪闭环。" [S4] | [35] |
| 2:50–3:40 | **证据&溯源** | LIVE/CACHED/SNIPPET provenance + contradiction. "我们诚实标注证据强度与冲突。" [S6] | [35] |
| 3:40–4:30 | **执行轨迹 DAG** | 9-node graph with the 打回重采 back-edge + synthesis; per-node tokens. "失败可定位到具体步骤。" [S1][S8] | [25] |
| 4:30–5:10 | **可观测** | Per-agent token chart; prompt/output (redacted). "成本/延迟归因到子任务。" [S1][S7] | [25] |
| 5:10–5:40 | **Schema 矩阵 + 人工修正** | 换领域 = 可扩展性; 采纳/驳回/编辑 = 人在闭环. | [20][25] |
| 5:40–6:00 | **Close** | Machine seconds vs 人工 16–40h（估算）; 合规声明 + Doubao. "可信、可溯源、可扩展、合规。" | [20][10C] |

Pre-record checklist: real run seeded (G3), 0 console errors, reduced-motion off, desktop viewport, Doubao live for the 30s live segment.

---

## 8. Risk register

| Risk | Sev | Detection | Mitigation |
|------|-----|-----------|------------|
| Live CN run gates out all claims → empty report (G21) | 🔴 | run with claim_admission_rate 0; HALLUCINATED_SNIPPET dominant | Analyst verbatim-quote prompt (G21a); Bocha-primary CN collection (G21b); Doubao quotes more (G21c). Demo on a seeded run if live is thin. |
| Doubao not wired (mandate + better grounding) | 🔴 | DOUBAO/ARK key absent | Phase 0 config switch on key arrival (Tier-C, organizer). |
| Faked/scripted closed loop | 🔴 | reviewer asks "is this live?" | Never fake; use the real reject→revise→pass run; tests prove the loop offline. |
| Provenance clutter lowers trust/usability [S2][S6] | 🟠 | judges overwhelmed in 10s test | Clean BLUF default; provenance on demand; inverted pyramid. |
| "Compiles but feels bad" (AI polish loop) | 🟠 | code green yet UX confusing/slow | Judge-loop via Playwright/Chrome DevTools (§5), not code-reading [S10][S11]; /design-review. |
| Citations backfire (authority on a wrong summary) [S9] | 🟠 | a cited sentence is subtly unsupported | QA value-grounding gate already guards; keep VALUE_UNSUPPORTED strict. |
| AI-slop / 英文 leakage in CN report | 🟠 | read the brief aloud | writing-anti-ai pass; CN-first prompt; manual read. |
| Demo-time perf jank / animation behind text | 🟡 | Chrome DevTools perf trace | motion on arrival only; reduced-motion; 60fps check. |
| Test-harness flake (#16) misread as product bug | 🟡 | ~5% vitest flake | documented; live app verified; fix as its own task. |

---

## 9. Paste-ready ClaudeCode command package

```text
/effort ultracode
/goal Using /mingjing-polish, run a final award-polish sprint mapped to the judge rubric in
docs/POLISH-RESEARCH-2026-06-06.md §3. Work one verified, committed slice at a time; for each
non-trivial slice run a dynamic workflow (contract / design / risk) BEFORE implementing, then
VERIFY IN THE REAL APP with Playwright/Chrome DevTools on a real run id (0 console errors, all
endpoints 200, real data — no mock), capture screenshots, then end the turn for the Codex review
gate. Priority order: (1) G21a analyst verbatim-quote discipline so live runs ground claims;
(2) G3 seed one real reject→revise→pass run and make QA-Replay show a numeric weak→strong delta;
(3) self-score every tab against the §3 rubric and fix any axis ≤3; (4) tighten the 简体中文 brief
(BLUF-first, cited, no AI-slop, no 英文 leakage). Forbidden: mock demo data on the demo path;
weakening QA/evidence/PII/robots/credibility invariants; faking the closed loop, screenshots,
tests, or Codex review; flashy effects that hurt credibility. Keep going until tsc -b, npm run
lint, vitest, backend make test (when touched), browser evidence, Codex review, and clean git
status prove the rubric has no ≤3; or stop after N turns with a blocker report.
```

Targeted follow-ups:
```text
# Live grounding fix (G21a) — the highest-leverage credibility move
/investigate The analyst paraphrases instead of quoting verbatim, so live CN runs (飞书) trip
HALLUCINATED_SNIPPET/VALUE_UNSUPPORTED and the QA gate admits 0 claims. Root-cause in
agents/analyst.py + the prompt; make cited snippet a verbatim source span and value leaves
literally present in sources; add a test; re-run the 飞书 case on MiniMax and confirm
claim_admission_rate > 0 without weakening the QA gate.

# Judge dogfood loop
/qa Drive all 6 tabs on a real run via Playwright/Chrome DevTools; for each, assert 0 console
errors, all endpoints 200, real data, and the §5 checklist; file + fix any UX defect that code
review alone would miss.

# Pre-submission design pass
/design-review the 6-tab workbench for AI-slop, spacing, hierarchy, and slow/distracting motion;
fix to the BI-workbench bar (§6); keep ink/mirror tokens.
```

---

## Sources

- [S1] LangChain — Agent observability (handoffs, step visibility, localize/regression/cost benefits): https://www.langchain.com/articles/agent-observability
- [S2] arXiv — Claim-evidence provenance vs flat citations; trust/usability nuance (26-expert study): https://arxiv.org/pdf/2602.21045
- [S3] arXiv — 5-dimension automated self-test release gate; evidence coverage most predictive: https://arxiv.org/html/2603.15676v1
- [S4] Grounded vs intrinsic self-correction (execution-grounded 70.3%): https://zylos.ai/research/2026-05-12-agent-self-correction-reflexion-to-prm
- [S5] BI dashboard design — simplicity, audience-specific KPIs: https://www.techtarget.com/searchbusinessanalytics/tip/Good-dashboard-design-8-tips-and-best-practices-for-BI-teams
- [S6] Dashboard design — inverted pyramid, 10-second/top-2-questions test, chart-to-intent: https://www.datacamp.com/tutorial/dashboard-design-tutorial
- [S7] Arthur.ai — Agentic AI observability playbook; decision provenance: https://www.arthur.ai/column/agentic-ai-observability-playbook-2026
- [S8] AgentEnsemble — multi-agent traces as span trees (duration/tokens/status); capture modes: https://dev.to/agentensemble/debugging-multi-agent-systems-traces-capture-mode-and-live-dashboards-4doh
- [S9] shapeof.ai — Citations pattern (authority + backfire; point to exact passages): https://www.shapeof.ai/patterns/citations
- [S10] Vercel agent-browser — snapshot+refs (accessibility-tree element refs, not CSS selectors): https://github.com/vercel-labs/agent-browser
- [S11] Tweag agentic-coding handbook — visual feedback + live browser state via MCP: https://tweag.github.io/agentic-coding-handbook/WORKFLOW_VISUAL_FEEDBACK/
- [S12] LangSmith/LangGraph observability — execution as traces/runs: https://docs.langchain.com/oss/python/langgraph/observability

> ⚠ Source-date caveat: a few surfaced URLs carry 2026 datestamps (arXiv ids, playbooks); treat
> their specific statistics as directional and re-verify any number you quote verbatim in 答辩.
