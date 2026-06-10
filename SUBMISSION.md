# MingJing 明镜 — Competition Submission Entry Point

> Evidence-Grounded Competitive-Analysis Multi-Agent Runtime (built on LangGraph).
> 一个会**自我纠错**的竞品情报分析系统:它搜索网络、由一个独立的 QA agent 当场打回证据不足的结论、
> 真实地重新取证、把结论从 **weak → strong** 升级——每条进报告的结论都能点开追溯到原始来源。

**一句话立论 (thesis):** **Evidence-admissible / verification-for-governance** —
LLM 负责提案,确定性代码负责裁定真值。证据强度只有透明的三档 (weak / moderate / strong),
没有可信度小数;writer 只投影 QA 通过的结论;weak→strong 通过**真实重新取证**实现
(source cap = 1 + revision_round,后续轮次取的是真正的新证据,不是预先藏好的)。

This file is the single judge-facing entry point. It does not duplicate the detailed docs —
it orients you and links to them.

---

## 1. 30-second orientation for judges (评委 30 秒上手)

**The money-shot path — open the frontend, click「查看示例分析」.**

The frontend auto-surfaces the strongest run via `pickExample`, landing on the **Chinese
multi-competitor flagship** below — you can watch a claim get rejected, re-collected, and
its evidence **tier-upgraded (中→强)** on screen.

Two canonical demo runs carry the headline narratives. Their web evidence is real
(verbatim spans of real pages via the cached corpus); each run also carries a few
**SIMULATED survey/interview rows** — clearly badged in the UI（「模拟问卷数据」）and
**excluded from evidence-tier counting** (`scoring.py` `contributes_to_tier`):

| Run id | Competitors | What it demonstrates |
|---|---|---|
| `4fff4227…` | Notion vs Linear (**matrix**, 中文) | **The default landing run.** Chinese multi-competitor comparison generated UNDER the simulated-survey exclusion (strong tiers from real sources only): **6/10 claims QA-admitted** (strong:1 / moderate:5; 4 honestly withheld with issue codes), `repair_delta ≈ 0.423` (**+42%**, 真闭环确认 seal lit), TWO real arcs — 用户口碑 **弱(2源)→中(4源)** and Linear 定价 **中(2源)→强(4源)**, coverage 80% (swot honestly uncovered + self-disclosed in 情报缺口), citation 100%, 3 `qa_pass` affirmative-verdict events in trace. `pickExample` tier-1 selects it; the whole 6-min script runs on this ONE run. |
| `3775d21a…` | Notion (single, **depth**, EN) | Repair-depth archive: a real **weak→moderate** closed loop, `repair_delta ≈ 0.376` (**+38%**), sources `1 → 5`, 4 admitted (强0·中4). Predates Chinese output and the simulated-survey split — kept as history. |

Deep-link directly: `http://localhost:5173/?run=4fff4227cdce4661a654603566a0385e`
(switch the id to `3775d21a9b634b5a86854c613c3187c8` for the EN repair-depth archive).
Full narration script: [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) and the 答辩 main line
[docs/DEFENSE-NARRATIVE.md](docs/DEFENSE-NARRATIVE.md).

---

## 2. How to run (运行方式)

```bash
uv sync              # install Python deps (Python 3.12)
make test            # full offline test suite — NO API key required (DI fakes)
make api             # FastAPI backend on :8000 (loads .env)
make web             # Vite frontend dev server on :5173
```

Offline tests need **no** API key. Live runs need `MINIMAX_API_KEY` in `.env`
(`cp .env.example .env`). Full quickstart, Directed vs Discovery Mode, and the demo
timing harness: see [README.md](README.md) (Quickstart) and [docs/deployment.md](docs/deployment.md).

---

## 3. Verified status (可本地复现的门禁)

All numbers below are reproducible locally via the listed commands.

| Gate | Result | Command |
|---|---|---|
| Backend tests | **883 passed**, 1 warning (a pre-existing StarletteDeprecationWarning, unrelated), exit 0 — fresh run 2026-06-10 (incl. 43-case QA calibration suite & scope-methodology suite) | `make test` |
| Backend lint | ruff: All checks passed | `ruff check` |
| Frontend tests | **314 passed** across **31 files**; **0** React `act()` warnings — fresh run 2026-06-10 | `cd frontend && npx vitest run` |
| Frontend typecheck | `npx tsc -b` exit 0 (use `-b`, not `--noEmit`); eslint clean | `cd frontend && npx tsc -b` |
| Production build | exit 0; main chunk `index.js` **461.73 kB** (gzip 143.59 kB), code-split into lazy chunks Observability 368.77 kB + ExecutionTrace 139.62 kB | `make web-build` |
| File-size rule | **No source file exceeds 800 lines** (`db` is a mixin package, max module 259 lines; largest frontend test file 598 lines, `ExecutionTrace.test.tsx`). Two backend **test** files intentionally exceed it — `tests/test_api.py` (1521) and `tests/test_qa_rules.py` (905), exhaustive endpoint/QA-rule suites; splitting them is roadmap cleanup, not a correctness gap | — |
| Demo DB | `data/mingjing.db` (gitignored): **15 runs, all status=partial, 0 error runs** (3 stale error runs cleaned via `Database.delete_run`) | — |

---

## 4. Self-score vs official 5-dimension rubric (自评 · 非官方)

> Self-assessed engineering judgment, **not** an official score. Detailed gap-by-gap
> analysis: [docs/SELF-AUDIT.md](docs/SELF-AUDIT.md).

| Dim | Weight | Honest readiness |
|---|---|---|
| **D1** 多 Agent 协作 & 输出可信度 | 35% | Strong. 4-agent LangGraph loop with a deterministic, provider-agnostic QA gate; real tier-upgrade self-correction on the default run (`4fff4227` 弱→中 AND 中→强, +42% groundedness repair); every claim traceable to source with an explicit per-claim QA✓ verdict stamp; simulated survey data mechanically excluded from all credibility math. |
| **D2** 技术深度 & 工程完整度 | 25% | Strong. Full offline test suite green (counts in §3); append-only SQLite (WAL), SSRF/robots guards, code-split frontend, ≤800-line source files; run-level concurrent submissions (per-run worker threads, single-writer serialized commits — smoke-tested in `tests/test_concurrent_runs.py`) + search-level concurrency. |
| **D3** 业务价值 & 产品体验 | 20% | Solid. 6-tab BI workbench, tier-upgrade money-shot (弱→中 / 中→强) on ONE default run, KPI bar with human-baseline comparison + 一致性 mechanism tile, multi-competitor matrix (`4fff4227`, 中文), HITL correction channel. |
| **D4** 代码质量 & 文档 | 10% | Strong. ruff/eslint clean, conventional commits, full doc set (architecture, agent-protocol, deployment, compliance, roadmap). |
| **D5** 合规、材料 & 答辩 | 10% | Mostly ready. COMPLIANCE.md (robots+SSRF+PII), presentation PDFs, judge-qa, defense narrative prepared; **Doubao full run verified 2026-06-10** (run `33835db0`, see §7). **Open human item:** demo video not recorded. |

Self-assessed readiness is **high across D1–D4**, with the only material residual being the
two human-only D5 items in §7. No precise total is claimed.

---

## 5. Official requirement coverage (课题核心功能逐条对照)

> Mapped against the official 课题材料 §2「核心功能」. Each row: requirement → where it
> lives in the code → honest caveat. This is the box-checking view for judges.

| 官方核心功能 | 实现 / 证据 | 诚实边界 |
|---|---|---|
| **角色 Agent**（采集 / 分析师 / 撰写 / 质检，含问卷设计·问卷调研·用户访谈） | 4 个专职 agent（`src/mingjing/agents/{collector,analyst,qa,writer}.py`），职责边界互不重叠；问卷/访谈证据 lane = `survey.py` + `survey_seed.py`（PII 脱敏）；**真实问卷接入口 `POST /runs/{id}/survey/import`**（`ingest.ingest_survey`：入库前 PII 清洗、`survey:<id>/r<n>` 定位符使同一问卷全部回答按 1 个独立域计权、`INGESTED` 权威权重，API 测试钉死） | demo 问卷为 curated fixture，源行标记 `SIMULATED` 且 UI 明示「模拟问卷数据 · 不参与分档」——模拟数据**对证据分档/佐证计数/矛盾检测贡献为零**（`scoring.contributes_to_tier`）；演示不向标杆 run 注入自填回答（自编内容走真实门仍是合成数据——诚实边界） |
| **知识结构化**（竞品 Schema：功能树 / 定价模型 / 用户画像） | `schema_registry.py` + `src/mingjing/domains/`；默认 5 字段 `feature_tree`(功能树)·`pricing_model`(定价模型)·`user_persona`(用户画像)·`user_sentiment`·`swot`；Pydantic v2 强校验；前端 `SchemaMatrix` 按字段显示覆盖 | Schema 为静态注册 + 可换领域（`MINGJING_SCHEMA_DOMAIN`）；**动态自动演化 schema 属 roadmap，未宣称已建** |
| **协作与反馈闭环**（结构化消息 / 质检打回 / DAG 迭代） | LangGraph `StateGraph`（`graph.py`）；`qa/route.py` 纯路由：不通过 → 派回 collector/analyst 重做；真实自纠闭环（默认 run `4fff4227`：弱→中 + 中→强 双弧线，repair_delta ≈ +42%；`3775d21a` 弱→中 +38% 史料）；前端 `ExecutionTrace` 渲染 DAG；结构化契约见 `docs/agent-protocol.md` | 闭环为 evidence-gap re-collection（真实重取证），**非 reactive gap-repair 引擎**；重做后输出确有改善（非伪闭环，有 invariant 测试佐证） |
| **信息溯源**（每条结论标注来源，traceability） | 每条 claim → `evidence_json` → `sources` 表；前端 `EvidenceAndQA` 抽屉显示原文 / 高亮 / hash / URL，一键溯源 | writer 仅投影 QA-passed claim，未过准入的结论不进报告（projection invariant） |
| **可观测**（日志可查 / 每 Agent 决策与中间产物可追溯） | `trace_events` + `llm_calls` 表；前端 `Observability` 显示每 Agent 的 Prompt / 输入 / 输出 / token；`trace.py` | LangSmith 深链为 roadmap；本地 trace / observability 已完整可查 |

---

## 6. Deliverables map (交付物索引)

- **Architecture / 引擎** — [docs/architecture.md](docs/architecture.md) (loop diagram, agents, trust mechanics)
- **Agent protocol** — [docs/agent-protocol.md](docs/agent-protocol.md) (typed contracts, RunState, trace vocabulary)
- **Deployment** — [docs/deployment.md](docs/deployment.md) (env vars, live vs cache mode, SSRF/robots posture)
- **Compliance / 合规** — [docs/COMPLIANCE.md](docs/COMPLIANCE.md)
- **Judge Q&A / 预置问答** — [docs/judge-qa.md](docs/judge-qa.md)
- **Defense narrative / 答辩主线** — [docs/DEFENSE-NARRATIVE.md](docs/DEFENSE-NARRATIVE.md)
- **Demo runbook / 录屏脚本** — [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md)
- **Gap audit / 自评** — [docs/SELF-AUDIT.md](docs/SELF-AUDIT.md)
- **Presentation PDFs** — [docs/presentation/deck.pdf](docs/presentation/deck.pdf), [docs/presentation/cover.pdf](docs/presentation/cover.pdf)
- **QA screenshots** — [docs/qa/](docs/qa/) (slice1-report, slice1-trace, slice2-final-report, slice3-evidence, slice4-qa-replay, slice5-execution-trace, slice6-credibility-kpi, slice7-schema-matrix, slice8-observability, slice10-correction-hitl)
- **QA judge calibration / 校准集** — [docs/qa/CALIBRATION.md](docs/qa/CALIBRATION.md)
  (43 human-labeled cases; admit/withhold **P 1.00 / R 1.00 / acc 1.00**, 0 known gaps —
  a consistency proof over author-labeled cases, not a blind third-party benchmark;
  `tests/test_qa_calibration.py`, deterministic & re-runnable)
- **Verbatim re-verification audit / 逐字复核** — `scripts/audit_verbatim.py` (read-only):
  all **10 admitted claims / 39 cited snippets** across the two flagship runs re-verified
  against source raw_text, **100% hit** (measures verbatim source-support, not world-truth);
  the 5 withheld claims' issue codes accounted
- **AI-assisted dev** — [docs/AI-ASSISTED-DEV.md](docs/AI-ASSISTED-DEV.md)
- **README quickstart** — [README.md](README.md)

---

## 7. Honest known gaps (诚实披露 — 这是特性,不是道歉)

**Human-only — NOT done (must be completed by a human):**
- **Submission/demo VIDEO not recorded.** The recorder harness exists (`make record-demo`),
  but **no video file has been produced**.

**Closed since the judge review (2026-06-10):**
- **Doubao/Ark: FULL RUN VERIFIED.** Run `33835db0` executed the entire
  pipeline on the contest **Doubao-Seed-2.0-lite** EP — all **18 `llm_calls` rows
  fingerprint `ep-20260514111325-xjmj7`** (auditable in Observability). The
  deterministic gate behaved identically under the official model: 5 proposed →
  **1 admitted at STRONG** (user_persona, 4 sources, verbatim re-audit 4/4 = 100%),
  4 withheld with honest codes (VALUE_UNSUPPORTED ×2, HALLUCINATED_SNIPPET ×2,
  SCHEMA_GAP ×1); repair_delta +20% with a real tier upgrade across 4 QA rounds;
  602 s / 53,987 tokens. Honest scope: a single-competitor verification run — the
  canonical flagship narrative stays on the MiniMax high-hallucination stress test
  (provider-agnostic gate), with Doubao now proven, not just claimed. The key was
  used in-process only (never written to disk/git; prior leaked credentials remain
  deactivated — COMPLIANCE §七).

**Roadmap-deferred — deliberately out of scope (NOT claimed as built):**
- Run-level (multi-run) concurrency **scheduler** — *deferred*. (Search-level
  concurrency, a `ThreadPoolExecutor` across engines, **does** exist; and run-level
  concurrency SAFETY is proven by `tests/test_concurrent_runs.py` — two simultaneous
  full-graph runs persist correctly under WAL + single-writer lock.)
- Dynamic schema evolution — *deferred*.
- Voting / self-eval — *deferred* (the QA gate reads source text, never model self-scores).
- Real LangSmith deep-link — *deferred*.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full deferred list.

---

## 8. AI-assisted development (AI 辅助开发)

MingJing was built with a disciplined AI-orchestration pipeline (Claude Opus as conductor →
focused sub-agents per slice → Codex as an automated second-opinion review gate), with a
verify-before-commit rule (tests + lint + browser evidence) on every slice. The human owns
scope, acceptance gates, and ship/merge authority; AI executes implementation and
self-verification. The git history itself is the audit trail. We say this plainly and do
**not** embed fabricated tool screenshots. Full account:
[docs/AI-ASSISTED-DEV.md](docs/AI-ASSISTED-DEV.md); the prepared TRAE / AI-tooling answer is in
[docs/judge-qa.md](docs/judge-qa.md) ("你们用了 TRAE / AI 编码工具吗?").

---

> **Branch & push status:** `feature/mingjing-0608`. This finalization batch's commits
> (db split, frontend test hardening, judge-qa answer, count-sync, corpus enrichment, and
> this audit refresh) are **pushed to `origin/feature/mingjing-0608`** — branch in sync
> (0 ahead / 0 behind, verified 2026-06-09).
