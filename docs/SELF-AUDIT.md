# MingJing 总审计报告 — Gap 汇总与当前完成度核对（2026-06-09）

> 本文件汇总并更新以下审计来源：
>
> - `/home/lingxufeng/Langgraph/mingjing/docs/GAP-AUDIT-2026-06-09-CURRENT.md`
> - `/home/lingxufeng/Langgraph/Gap-Audit-2026-06-08.md`
> - `/home/lingxufeng/Langgraph/mingjing/docs/GAP-AUDIT-2026-06-08-RUBRIC.md`
> - 当前代码、运行库、API、提交状态与新复核结果。
>
> 这不是原文拼接，而是面向提交/答辩的合并版：保留所有仍有效的 Gap、标出已完成项、剔除已修复的旧问题，并补入最新发现的展示弱、体验风险、工程风险。

> **【2026-06-10 终轮更新 — M 批（评委终评对账）】** 针对 82.7 分模拟评委终评的逐条响应，
> 全部 P1 代码项已修复并有回归测试：① 证据抽屉改为**列出全部引用来源**（真实来源排前、
> `survey:` 定位符渲染为不可点徽标，旧"单一最佳匹配"对中文 statement 退化为锁定模拟问卷行的
> 缺陷已消除）；② **0 条准入的 run 不再点亮任何印章/提速**（CredibilityPanel + KpiBar 双门控
> + 明示「0 条结论准入」披露）；③ P2 批：页面标题 → 明镜、QA 回放计数器不再出现 0 首帧、
> partial 横幅中文化、DAG 终态不再残留 running、近期运行加竞品+时间副标题。新增能力：
> **「范围与方法」段**（`scope.py` 确定性投影，报告/导出双渲染）、**QA 校准集**（43 例人工标注,
> admit/withhold P/R/acc = 1.00, `docs/qa/CALIBRATION.md`）、**全量逐字复核审计**
> （10/10 准入 claim · 39/39 snippet 100% 命中, `scripts/audit_verbatim.py`）。
> 评委指控对账：「dangling blob 可恢复泄露 key」经全对象库扫描 **0 命中,不成立**；两枚盘上
> 历史凭据实测 401 已作废（COMPLIANCE §七）；「SUBMISSION 测试数自相矛盾」为旧 HEAD 残影,
> 本文与 SUBMISSION 的测试数以本节日期的 fresh run 为准。Doubao：**完整 run 已验证**
> （`33835db0`,18 调用全官方 EP 指纹,1 准入强档+4 留存有码;盘上历史 key 401 已作废）。
>
> **【2026-06-09 深夜更新 — 旗舰 run 更替】** 下文多处引用的旗舰 `b1771f67`（7/10 准入、
> strong:4）**已退役删除**：复算证实其 4 条 strong 中 3 条依赖 fixture 问卷源在旧打分规则下
> 铸档（问卷源当时计为权威独立域）。修复后（fixture 源标记 `SIMULATED`，机制级排除于一切
> 可信度计算，commit `b84cc95`/`360e02d`），在新门禁下重跑产生**新默认旗舰
> `4fff4227`**：6/10 准入（强1·中5，强档全部来自真实来源）、repair_delta **+42%** 且真闭环
> 印章点亮、弱→中 + 中→强双弧线、4 条留存全披露。下文出现的 `b1771f67` 段落为当日历史
> 审计记录，按其落笔时点理解；最新口径见 `DEFENSE-NARRATIVE.md` §0 八项验收清单。

---

## 0. 一句话结论

MingJing 当前已经达到“代码能编译、测试门通过、核心多 Agent 可信闭环真实存在”的工程基线。后端、前端、API、DB、QA gate、证据溯源、HITL、trace/observability 都不是空壳。

但它还不能被描述为“最终提交无短板”。本批次（db 拆分、前端测试加固、judge-qa 答案、计数同步、corpus 补强、本审计刷新）已把多项旧风险关闭。当前残余的真实风险只剩人工项与 roadmap 项：

1. **演示视频缺失（人工项）**：录屏 harness `make record-demo` 存在，但尚未产出任何视频文件。
2. **Roadmap 延期项**：run-level 并发**调度器**、动态 schema 演化、投票式自评估、真 LangSmith deep link 仍未实现（search-level 并发已实现；run-level 并发**安全性**已由 `tests/test_concurrent_runs.py` 双 run 同跑验证）。

已在本批次/前序批次关闭的旧风险（不再算当前风险）：**Doubao/Ark 接入**（2026-06-10 完整 run `33835db0` 验证：18 调用全官方 EP 指纹，1 准入强档+4 留存有码，+20% 增益档位跃升——COMPLIANCE §八）、旗舰多竞品 run（历史 `b1771f67`，**已退役更替为 `4fff4227`**，见顶部 2026-06-09 更替注）、默认示例偏单竞品（RC2 `pickExample` tier-1 优先多竞品）、README `InsightCard` 过期（GB2）、工作树未跟踪大文件/gitignore（GB1）、`db.py`>800（F1 拆为 mixin 包）、React `act()` warnings（F2/F3）、bundle 体积（RC4 code-split）、测试计数文档漂移（F5）、judge-qa TRAE 答案（F4）。

---

## 1. 当前验收证据

### Fresh verification

以下命令已在当前工作区重新执行：

| 验证项 | 当前结果 | 判断 |
|---|---:|---|
| 后端测试 `make test` | `883 passed, 1 warning`（pre-existing StarletteDeprecationWarning，与本项目无关），exit 0（2026-06-10 fresh，含 43 例 QA 校准集与 scope 套件） | 通过 |
| Python lint `uv run ruff check .` | `All checks passed!` | 通过 |
| 前端测试 `vitest` | `314 passed / 31 files`；0 个 React `act(...)` warnings（曾 47，现已清零）（2026-06-10 fresh） | 通过 |
| 前端 typecheck `npx tsc -b` | exit 0 | 通过 |
| 前端 lint `eslint` | exit 0，无错误输出 | 通过 |
| 前端 build `npm run build` | exit 0；主 chunk `index.js` 461.73 kB（gzip 143.59 kB），已 code-split 为 lazy chunks（Observability 368.77 kB + ExecutionTrace 139.62 kB） | 通过 |
| API health | `{"status":"ok"}` | 通过 |

### Git / worktree

| 项 | 当前状态 |
|---|---|
| 分支 | `feature/mingjing-0608` |
| 与远端差异 | 本批次（db 拆分、前端测试加固、judge-qa 答案、计数同步、corpus 补强、本审计刷新）已推送 `origin/feature/mingjing-0608`，分支同步（0 ahead / 0 behind，2026-06-09） |
| PDF 材料 | `mingjing/docs/presentation/deck.pdf`、`cover.pdf` 已 tracked |
| 多竞品 launcher | `mingjing/scripts/run_demo_multi.py` 已 tracked |
| 演示视频 | 未发现（人工项，见 §4 P0） |
| 未跟踪大文件风险 | 已解决（GB1）：根目录 scratch 图片、`UI/`、`.playwright-mcp/`、`node_modules/`、`.gstack/`、缓存、runtime DB 均已被 `.gitignore` 排除 |

---

## 2. 官方评分维度对照

官方 5 维权重：

| 维度 | 权重 | 当前判断 |
|---|---:|---|
| D1 多 Agent 协作与输出可信度 | 35% | 核心强；单竞品深度 + 多竞品矩阵双 run 叙事已具备 |
| D2 技术深度与工程完整度 | 25% | 工程门过；run-level 并发/动态 schema 等明确标记为 roadmap 延期加分项（不 overclaim） |
| D3 业务价值与产品体验 | 20% | 主体验完成；旗舰多竞品 run 为 `4fff4227`（中文报告，6/10 准入，强1·中5；历史 `b1771f67` 已退役） |
| D4 代码质量与文档 | 10% | 代码/测试强；README/计数口径已同步（GB2/F5），db 已拆为 mixin 包（F1） |
| D5 合规、材料与答辩 | 10% | 合规代码有，PDF 有，**Doubao 完整 run 已验证**（`33835db0`）；视频仍为人工项 |

---

## 3. 已完成项

### D1：多 Agent、反馈闭环、Schema、溯源

| 要求 | 当前状态 | 证据/说明 |
|---|---|---|
| 3-4 个专职 Agent | 已完成 | Collector / Analyst / QA / Writer 分层清晰 |
| LangGraph 编排 | 已完成 | `intake -> plan -> collect -> analyze -> qa -> route -> revise/write -> synthesis` |
| 反馈闭环真实可触发 | 已完成 | QA reject 后能回 collect/analyze；存在真实 weak/moderate/strong 改善轨迹 |
| 结构化 Schema | 已完成 | default / ai_agent / hr domain schema |
| 信息溯源 | 已完成 | claim 带 evidence source ids，source 可查 raw text/content hash |
| QA gate 控制报告准入 | 已完成 | Writer 只投影 QA-passed claims |
| `is_tier_upgrade` 诚实旗标 | 已完成 | badge 不再只凭 repair_delta 虚报弱升强 |
| claim history 返回 note | 已完成 | HITL note 可 round-trip |
| trace 断言 | 已完成 | `revise_done`、`synthesis_start/done` 已有测试断言 |

### D2：工程完整度、可靠性、可观测

| 要求 | 当前状态 | 证据/说明 |
|---|---|---|
| 端到端链路 | 已完成 | DB / API / frontend / graph / agents 均连通 |
| LLM 调用记录 | 已完成 | `llm_calls` 记录 prompt/output/tokens/model |
| trace events | 已完成 | 前端 Execution Trace 可读 |
| 幻觉抑制 | 已完成 | `HALLUCINATED_SNIPPET`、`VALUE_UNSUPPORTED`、schema/value grounding |
| `recursion_limit` 防御上限 | 已完成 | live graph `recursion_limit=40` |
| `run_error` 终态 | 已完成 | 硬错误不再让报告页永久 Waiting |
| 前端 lint warning 清理 | 已完成 | 旧 `record-money-shot.mjs` unused-disable warnings 已消失 |
| 删除死代码 | 已完成 | `InsightCard.tsx` / `insight.ts` 已从 tracked 文件删除 |
| React `act(...)` warnings 清零 | 已完成（F2/F3） | 前端测试 0 个 act warning（曾 47） |
| db 模块拆分 <800 行 | 已完成（F1） | `db.py` 拆为 `src/mingjing/db/` mixin 包，最大文件 259 行（`_base.py`） |
| 源码 <800 行 | 已达成 | 所有 `src/`/前端源码 ≤800 行；**例外为测试文件** `tests/test_api.py`（1521）、`tests/test_qa_rules.py`（905）——穷举式端点/QA-规则套件，拆分属 roadmap 清理，不影响正确性（诚实披露，非 0 行违规） |
| bundle code-split | 已完成（RC4） | 主 chunk 461.73 kB（gzip 143.59 kB），Observability/ExecutionTrace 拆为 lazy chunk |

### D3：产品体验与业务闭环

| 要求 | 当前状态 | 证据/说明 |
|---|---|---|
| 报告查看 | 已完成 | Final Report + deterministic ledger |
| 证据抽屉/溯源 | 已完成 | EvidenceDrawer 可查 source |
| QA Replay | 已完成 | view/test 存在，loading skeleton 与正向一次通过文案已修 |
| HITL 修正 | 已完成 | accept/reject/edit + note 输入 |
| live-run 护栏 | 已完成 | 发起实时分析前 confirm，提示 3-5 分钟与结果可能偏薄 |
| clipboard feedback | 已完成 | 不再静默失败 |
| Activity 去重 | 已完成 | 重复 collector 事件不再像卡死 |
| stale running/error 清理 | 已完成 | 演示 DB 现 15 runs 全为 `partial`，0 error run（3 个 stale error run 经 `Database.delete_run` 清理） |

### D4：代码质量与文档

| 要求 | 当前状态 | 证据/说明 |
|---|---|---|
| 后端测试 | 已完成 | 883 passed, 1 warning（无关 StarletteDeprecationWarning；2026-06-10） |
| 前端测试 | 已完成 | 314 passed / 31 files，0 act warnings（2026-06-10） |
| ruff / eslint / tsc -b | 已完成 | 当前全部通过 |
| PDF 材料 | 已完成 | `deck.pdf`、`cover.pdf` 已生成并 tracked |
| README 测试数 | 已完成（F5，M 批再刷新） | 已同步到当前真实数（883/314，2026-06-10） |
| remote 文档错误 | 已完成 | `ROADMAP.md` 已改为 remote exists |
| native tool-call 口径 | 已完成 | `agent-protocol.md` 已写明无 native tool/function-calling |

### D5：合规

| 要求 | 当前状态 | 证据/说明 |
|---|---|---|
| robots / SSRF | 已完成 | collector/fetch/robots 相关实现与测试 |
| PII scrub | 已完成 | survey/interview ingest 有脱敏 |
| repo-side key scrub | 已完成 | 当前 tracked 文件中只命中测试假 key；赛题材料未 tracked |
| account-side key rotation | 未完成 | 仍是人工外部项 |

---

## 4. 未完成 / 仍有风险项

### P0：提交前必须处理

| Gap | 当前事实 | 影响 | 建议 |
|---|---|---|---|
| 演示视频缺失（人工项，仍开放） | 未发现任何视频文件；录屏 harness `make record-demo` 存在但未产出 | D5 提交材料直接扣分 | 录制 demo；单 run 全程脚本见 DEFENSE-NARRATIVE §4（默认旗舰 `4fff4227`，+42% 双弧线，无需切 run） |

> 以下 P0 旧项已在本批次/前序批次关闭，不再算当前风险：
> - **Doubao/Ark 完整 run** — 已解决（2026-06-10 `33835db0`：18 调用全官方 EP 指纹，1 准入强档（逐字 100%）+4 留存有码，+20% 增益；SUBMISSION §7 / COMPLIANCE §八）。
> - **旗舰多竞品 run** — 已解决（`b1771f67` 存在：Notion vs Linear 中文报告，全 5 字段覆盖 coverage 1.0，7/10 admitted，矩阵渲染 strong:4/moderate:3（2 个 full 行 + 3 个 partial 行）；`pickExample` tier-1 选它）。
> - **默认 money-shot 偏单竞品** — 已解决（RC2 `pickExample` tier-1 优先多竞品 run）。
> - **工作树未跟踪大文件风险** — 已解决（GB1：scratch 图片 / `UI/` / `.playwright-mcp/` / `node_modules/` / `.gstack/` / 缓存 / runtime DB 已 `.gitignore`）。
> - **README 过期叙事（InsightCard）** — 已解决（GB2：README 改为当前 BLUF/FinalReport 叙事）。

### P1：高 ROI 收尾

| Gap | 当前事实 | 建议 |
|---|---|---|
| Discovery label 仍写 “N 来源” | tooltip 已澄清，但 label 本身仍 overloaded | 改为 “N 信号域” / “N 提及域” |
| LangSmith | 前端默认显示“可接入”，无真实 deep link（roadmap 延期） | 可以保留，但不要口头说已接入真实 trace 控制台 |

> 以下 P1 旧项已关闭，不再算当前风险：
> - **synthesis_done 诚实性** — 已解决（GB3：synthesis 无 payload 时发 `synthesis_empty`，不再误导）。
> - **React `act(...)` warnings** — 已解决（F2/F3：前端测试 0 act warning，曾 47）。
> - **Vite bundle warning** — 已解决（RC4：主 chunk 461.73 kB / gzip 143.59 kB，已 code-split）。
> - **stale running run** — 已解决（DB 现 15 runs 全为 partial，0 error；3 个 stale error run 经 `Database.delete_run` 清理）。
> - **TRAE 证据答辩口径** — 已解决（F4：judge-qa 已写明用其他 AI 工具，有 coding record；TRAE IDE 截图本身仍无，答辩诚实说明）。

### P2：可延期但不能 overclaim

| 项 | 当前状态 |
|---|---|
| run-level worker-pool 并发 | 未实现；search-level 并发已实现 |
| 动态 schema 演化 | 未实现；当前是 config-driven domain schema |
| Agent 投票式自评估 / self-consistency | 未实现；当前是 deterministic rule gate |
| NER 级 PII 脱敏 | 未实现；当前为 regex/fixture 级 |
| 真 LangSmith deep link | 未实现；后端 env-gated tracing 有，默认离线 demo 无 |
| 跨 run 趋势视图 | 未实现；当前指标 per-run |

---

## 5. 当前 Demo Run 审查

> 注：旧报告引用的多竞品 run `ae3044219bf2...` 已被替换、不再存在。以下改为审查当前两条 canonical run。演示 DB（`data/mingjing.db`，已 gitignored）现有 15 runs，全部 `partial`，0 error run（3 个 stale error run 经 `Database.delete_run` 清理）。

### `b1771f67` — 多竞品矩阵 run（Notion vs Linear）

| 属性 | 值 |
|---|---|
| status | `partial` |
| competitors | Notion vs Linear |
| 报告语言 | 中文（statements + synthesis BLUF/建议/SWOT 均为简体中文；价格/数值保持来源原文以保证 QA grounding） |
| 字段覆盖 | coverage 1.0（全 5 字段均有 ≥1 竞品覆盖，uncovered_fields 为空） |
| QA 采信 | 7/10 claims admitted（claim_admission_rate 0.7），3 条诚实 withheld |
| strength tally | strong 4 / moderate 3 / weak 0 |
| 对比矩阵 | 2 个 full 行（两竞品都有）= `pricing_model` + `user_persona`；外加 3 个 partial 行（user_sentiment 仅 Notion、feature_tree 仅 Linear、swot 仅 Linear） |
| tier 升级 | 有真实 is_tier_upgrade（如 Notion 用户画像 moderate→weak→strong；Notion 定价/SWOT/用户口碑 moderate→strong） |
| 选用 | 这是当前的旗舰多竞品 run；`pickExample` tier-1 选它 |

结论：用作“多竞品对比”叙事的旗舰样例。它证明系统能跑多竞品、能输出中文综合报告、全 5 字段均有覆盖、能渲染对比矩阵（2 full + 3 partial 行），并在严格 QA 下完成真实 tier 升级（7/10 admitted）。诚实 caveat：部分单元格仍是空的（如 Linear 用户口碑、Notion 功能树/SWOT 由 partial 行体现），这是按竞品维度的真实覆盖差异，不是 bug。

### `3775d21a` — 单竞品深度 run（Notion）

| 属性 | 值 |
|---|---|
| status | `partial` |
| competitor | Notion |
| 闭环 | 真实 weak->strong 闭环 |
| repair_delta | ~0.376（+38% paired per-claim groundedness 提升） |
| 选用 | “验证深度 / 诚实治理”叙事主线 |

结论：用作“验证深度 / 诚实治理”叙事的主线样例。它证明真实的 QA 打回与 weak->strong 再采集闭环（source cap = 1 + revision_round），repair_delta 是 paired per-claim 口径，不是事实正确率。

推荐 demo 叙事（双 run）：

1. 主线用 `3775d21a` 讲“可信闭环 / +38% repair / 单竞品深度治理”。
2. 补充用 `b1771f67` 讲“多竞品矩阵已接通：中文综合报告、全 5 字段覆盖、7/10 admitted、strong:4/moderate:3、2 full + 3 partial 矩阵行、真实 tier 升级”。
3. 主动说明：partial 行（如 Linear 用户口碑、Notion 功能树/SWOT 留空）是按竞品维度的真实覆盖差异，宁可诚实留空也不造假结论。

---

## 6. 按用户质量标准复核

### 代码能编译成功不报错

判断：**满足**。

证据：

- 后端 883 tests passed（1 个无关 StarletteDeprecationWarning；2026-06-10 fresh，含校准集/scope 新增）。
- `ruff check` passed。
- 前端 314 tests passed / 31 files，0 个 `act(...)` warning（2026-06-10 fresh）。
- `npx tsc -b` exit 0。
- `npm run build` 成功，主 chunk 461.73 kB（gzip 143.59 kB），已 code-split。

残余：

- 无编译/测试残余告警；旧 `act(...)` warning 与 Vite 大包 warning 均已关闭（F2/F3、RC4）。

### 代码能真正实现功能

判断：**核心满足，demo 展示弱**。

已真实实现：

- 多 Agent LangGraph loop。
- Collector/Analyst/QA/Writer 分工。
- QA gate 打回。
- 证据溯源。
- 报告只展示 passed claims。
- HITL append-only 修正。
- Trace/observability。
- Metrics/credibility。

展示弱点：

- 旗舰多竞品 run `b1771f67` 已是“多竞品 + 全 5 字段覆盖（coverage 1.0）+ 中文综合报告”的 canonical run（7/10 admitted，strong:4/moderate:3，2 full + 3 partial 矩阵行，真实 tier 升级）。
- 残余诚实 caveat：部分单元格仍按竞品维度留空（如 Linear 用户口碑、Notion 功能树/SWOT，由 partial 行体现），这是真实覆盖差异而非满字段全闭环。

### 代码能模块化、完整度高

判断：**满足**。

后端模块分层：

- `graph.py` / `graph_nodes.py`：编排。
- `agents/`：角色 agent。
- `qa/`：确定性规则、route、credibility。
- `db/`：SQLite WAL + append-only tables（已拆为 mixin 包，最大文件 259 行）。
- `api.py` / `api_helpers.py`：FastAPI read views。
- `metrics.py` / `synthesis.py`：指标与综合。

前端模块分层：

- `views/`：FinalReport、QAReplay、ExecutionTrace、Observability、SchemaMatrix 等。
- `components/`：EvidenceDrawer、ClaimRow、CredibilityPanel、ComparisonMatrix、CorrectionControls 等。
- `api/`：typed API client。
- `lib/`：trace、qaReplay、markdown、withheld 等。

完整度评价：

- 核心工作流完整。
- 加分项如 run-level 并发、动态 schema、自评估未实现，属于不能 overclaim 的边界。

### 代码能实现业务功能

判断：**部分强，最终业务展示仍弱**。

业务功能已实现：

- 竞品信息采集。
- 结构化字段抽取。
- 定价/功能/画像/SWOT schema。
- 报告与证据。
- QA 拒绝与修正。
- 人工修正。
- 可换竞品、可换领域。
- 业务 KPI：coverage、citation_rate、strong_rate、human_correction_rate、repair_delta 等。

业务展示风险：

- 默认示例是单竞品。
- 多竞品 run 覆盖太窄。
- strong_rate / repair_delta 等指标必须解释为证据强度 proxy，不是事实正确率。
- 没有 gold-standard 人工基线对照。

### 前端设计、交互、后端对接

判断：**基本满足，有体验风险**。

完成：

- UI 已有完整工作台结构。
- 6 个核心视图可切换。
- API 对接正常。
- 数据从后端 trace/report/credibility/withheld/synthesis/source/history 流向前端。
- FinalReport、QAReplay、EvidenceDrawer、ComparisonMatrix、Observability 都有测试。
- live-run confirm、防误点、clipboard feedback、stale running label 已做。

体验风险：

- 旗舰多竞品 run `b1771f67` 已全 5 字段覆盖、BLUF/SWOT/建议均有中文内容；残余仅部分单元格按竞品维度留空（如 Linear 用户口碑、Notion 功能树/SWOT 的 partial 行，非 bug）。
- Discovery 候选 “来源” 标签容易和 QA 采信证据混淆。

（已关闭：默认示例偏单竞品 → RC2 `pickExample` tier-1 优先多竞品；React act warnings → F2/F3 清零；README InsightCard 过期 → GB2 已改。）

### 后端性能、存储、并发、接口交互

判断：**稳定性满足，并发不要 overclaim**。

完成：

- SQLite WAL + busy timeout + single-writer lock。
- append-only claims，版本历史可查。
- FastAPI endpoints 与前端对接正常。
- SSRF/robots/PII 相关防护有实现与测试。
- LLM timeout、cache fallback、partial report、run_error 等可靠性机制存在。
- search-level 并发存在。

风险/边界：

- run-level worker-pool 并发未实现（roadmap 延期）。
- SQLite 单文件适合 demo/单机，不应宣传为高吞吐生产集群。
- synthesis 失败是 non-fatal；`synthesis_done` 对“无 payload”的诚实性已修（GB3：改发 `synthesis_empty`）。

---

## 7. ClaudeCode 日志逐条复核

| ClaudeCode 陈述 | 当前复核 |
|---|---|
| GA1-GA12 全部完成 | 大体属实；代码/文档/PDF 多数落地 |
| commit 计数 | 本批次已推送，分支与远端同步（0/0）；不硬编码 ahead-by-N |
| 后端 774 passed | 已过期；当前 883 passed（2026-06-10），已 fresh 复现 |
| ruff clean | 属实 |
| 前端 278 passed | 已过期；当前 314 passed / 31 files（2026-06-10），已 fresh 复现 |
| lint 0/0 | 属实 |
| build 0 error | 属实；主 chunk 已 code-split 至 461.73 kB，无大包 warning |
| `ae304421` still running | 已过期；该 run 已被替换、不再存在 |
| 多竞品 run 验证矩阵/覆盖 | 当前多竞品 run 为 `4fff4227`：中文报告，6/10 admitted（强1·中5），覆盖 80%（swot 诚实留空）；历史 `b1771f67` 段落见顶部更替注 |
| 视频/Ark/TRAE 为人工项 | 基本属实；TRAE 可用 AI-assisted 文档和 Git 记录部分缓解（F4 已写入答辩口径） |
| Hold 不推 | 已解除；本批次经用户确认后已 push 到 origin（0/0 同步） |

---

## 8. 加分项单独评分

| 加分项 | 当前状态 | 可讲程度 |
|---|---|---|
| 一键溯源/原文查看 | 已完成 | 可以重点讲 |
| QA Replay 闭环 | 已完成 | 可以重点讲，但选对 run |
| Observability prompt/output/token | 已完成 | 可以重点讲 |
| 问卷/访谈 evidence lane | 已有实现与测试 | demo 弱，不能当主线 |
| Discovery Mode | 已完成 | 只能说发现候选竞品，不能说候选已 QA verified |
| 多领域 Schema | 已完成 | 可以展示 default/ai_agent/hr |
| 业务 KPI | 已完成 | 必须强调 proxy |
| AI-assisted / TRAE 痕迹 | 部分完成 | 有 Superpowers/Codex/Claude 证据，无 TRAE 截图 |
| 可复现录屏脚本 | 部分完成 | 脚本/材料有，视频未生成 |
| 并发处理 | 部分完成 | search-level 有，run-level 无 |
| 动态 schema 演化 | 未完成 | 只能讲 roadmap |
| Agent 自评估/投票 | 未完成 | 只能讲 deterministic QA gate 替代 |

---

## 9. 当前最可能被评委追问的问题

### 1. 你们用了官方 Doubao 吗？

诚实答案：

> 用了，且可审计：完整 Doubao run `33835db0`（2026-06-10）全链路跑在官方 Doubao-Seed-2.0-lite EP 上，可观测页的 18 条 LLM 调用模型列全部是 `ep-20260514111325-xjmj7`。门禁在官方模型下同样严格（5 提议→1 准入强档+4 留存有码）。默认演示主线仍是 MiniMax-M2.7——刻意的高幻觉压力测试：同一确定性门禁在两套模型下行为一致，这正是 provider-agnostic 的实证。

### 2. 为什么多竞品报告只有 pricing？

诚实答案：

> 因为 QA gate 拒绝了无法被原文支持的字段。我们宁可 sparse，也不把用户画像/SWOT 这种未被证据支撑的内容写进报告。这正是 MingJing 的差异：它不是生成得越满越好，而是只让可审计的结论进入报告。

### 3. strong_rate 是准确率吗？

诚实答案：

> 不是。strong_rate 是证据强度 proxy，表示有多少通过结论具备强证据链，不等于事实真值准确率。事实正确性仍需人工抽检或 gold-standard 数据集。

### 4. 你们的并发能力怎么样？

诚实答案：

> 当前实现了 search-level 并发和单机稳定运行。run-level worker-pool 不是本次提交的主能力，后续可以扩展为队列/worker 架构。

### 5. 你们用了 TRAE 吗？

诚实答案：

> 项目有清晰 AI-assisted 开发痕迹，包括 Superpowers 规划、Codex review-gate、Claude/Codex 协作、Git commit 记录。TRAE IDE 内部截图目前未纳入仓库，不能伪造；如果答辩需要，可以现场补充展示真实工具记录。

---

## 10. 提交前执行顺序

### 必做（仍开放，均为人工项）

1. 录制演示视频（`make record-demo` harness 已就绪，尚未产出文件）。

> 以下旧“必做”已关闭：未跟踪大文件清理（GB1 `.gitignore`）、README InsightCard（GB2）、固定 demo 策略（RC2 `pickExample` tier-1 选多竞品 `b1771f67`）。

### 高 ROI（仍开放）

3. 改 Discovery “来源”为“信号域/提及域”。

> 以下旧“高 ROI”已关闭：synthesis 空结果 trace 语义（GB3 `synthesis_empty`）、stale running 清理（DB 现 15 runs 全 partial、0 error）、React act warnings（F2/F3 清零）、canonical multi-competitor run（`b1771f67` 已存在）。

### 可延期（roadmap，不 overclaim）

4. 真 LangSmith deep link。
5. run-level 并发 worker。
6. dynamic schema evolution。
7. agent self-evaluation / voting。

> code-splitting 已完成（RC4，主 chunk 461.73 kB）。

---

## 11. 最终状态判断

### 可以对外宣称

- MingJing 是一个基于 LangGraph 的多 Agent 竞品分析 runtime。
- 它有 Collector / Analyst / QA / Writer 分工。
- 它能用 deterministic QA gate 拒绝弱证据 claim。
- 它能把不合格 claim 打回并保留版本历史。
- 它支持证据溯源、报告、QA Replay、Observability、HITL。
- 它有可验证测试门：后端 883 passed、前端 314 passed（0 act warnings；2026-06-10）。
- 它支持多领域 schema 与多竞品 run（`b1771f67` 多竞品矩阵：中文报告、全 5 字段覆盖、strong:4/moderate:3 + `3775d21a` 单竞品深度闭环）。

### 不能对外宣称

- 不能说"全部 run 跑在豆包上"——已真实接入并验证（`33835db0`），但默认演示主线仍是 MiniMax 压测；两套口径都要讲清。
- 不能说 `b1771f67` 是每个竞品每个字段都填满的完整业务闭环（部分单元格按竞品维度诚实留空，由 3 个 partial 矩阵行体现）。
- 不能说 strong_rate 等于准确率。
- 不能说已支持 run-level 高并发。
- 不能说已实现动态 schema 演化。
- 不能说 Discovery 发现的候选已被 QA 采信。
- 不能说有真实 LangSmith deep link，除非配置并验证。

### 总评

当前 MingJing 的工程底座已经过线，代码质量和核心可信闭环是强项。短板集中在提交材料、演示样例和诚实口径。如果把当前状态直接提交，技术维度会比较强，但 D3/D5 会被 demo 和材料拖分。

最优策略不是再扩大量功能，而是把当前系统包装成一个诚实的证据治理产品：

> “MingJing 的价值不是生成一份看起来很满的报告，而是让每条进入报告的结论都能被追溯、被复核、被拒绝，并留下为什么拒绝的证据链。”

这个叙事成立，但必须用正确 demo 支撑：单竞品深度闭环作为主线，多竞品 sparse matrix 作为补充，主动说明 strict QA 下的覆盖缺口。
