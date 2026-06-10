# 明镜 (MingJing) — AI 辅助开发说明 (AI-Assisted Development Evidence)

> 本文如实说明明镜的开发方法与 AI 协作痕迹。仓库侧可独立核验的证据 = git 历史 +
> `docs/superpowers/plans/` + `docs/qa/` 截图 + Codex review-gate 配置。
> TRAE / IDE 内的逐条交互记录属用户侧上下文，本文不内嵌伪造的工具截图。

---

## 1. 编排模型（方法本身）

明镜的产品打磨阶段采用一个**有纪律的 AI 编排流水线**，而非单个 agent 自由发挥：

- **主循环（Conductor）**：Claude Opus 作为编排者/规划者——把每个验收关卡（G 系列 GAP）
  拆成最小可发布切片（slice），持有目标账本（goal ledger），做 Tier-A 自主决策。
- **动态工作流 + 聚焦子 agent**：每个非平凡切片在实现前先跑一个 **Dynamic Workflow**，
  派发给单一职责子 agent（契约/API agent、设计/产品 agent、风险/回归 agent），各自产出
  **文件锚定**的可执行规划，主循环再综合、消解冲突、顺序实现并提交。
- **AutoPilot 三级决策**：Tier-A 自决 / Tier-B 交 Codex 裁定（可逆且在范围内）/
  Tier-C 升级给人（合规、账号、不可逆、超范围）。
- **独立复审门（Codex）**：每个切片在回合结束由 Codex 经 Stop hook 独立复审
  （`CODEX_REVIEW_GATE_GLOBAL=true` + openai-codex stop-review-gate-hook）；Codex 亦是
  Tier-B 歧义的裁判。这是**自动化第二意见 / 裁判门**，不是人类资深工程师签字。

## 2. 提交前必验（Verify-before-commit）

任何切片在以下全绿前不提交，且**命令与结果原样贴入提交信息体**，QA 截图存入 `docs/qa/`：

- 前端：`npx tsc -b`（references 构建，非 `--noEmit`）、`npm run lint`、`npx vitest run`、`npm run build`
- 后端（触及时）：`make test`、`ruff check`
- 浏览器实测：用 chrome-devtools 加载真实 run，检查 0 console error、所有端点 200、
  **真实数据**（无 mock），截图留证

每个提交映射到一个验收关卡 ID，并声明 “Contract preserved”（保留 testid/role/exact-text
公共契约）以证明无回归。证据先于断言（evidence-before-assertions）。

## 3. 节奏即证据（git 审计轨迹）

- 前端以 10 个有序、命名的 “Slice” 提交落地（Final Report → Evidence → QA Replay → DAG →
  Credibility/KPI → Schema → Observability → Survey → Correction），后端为原子 feat/fix 提交。
- 全部遵循 **Conventional Commits**（`feat(collector)` / `fix(qa)` / `style(frontend)` /
  `test(qa)` / `docs(mingjing)`），全部在 `feature/mingjing-w1-core` 分支。
- git 图本身即审计轨迹：**规划 → 实现 → 验证 → 复审 → 提交**，逐切片重复。
  典型本阶段提交：G20 多引擎采集、G5 snippet-QA 回归锁、Slice 2–10 前端重皮 + G6/G7/G9/G11/G12/G13/G14。

## 4. 人 vs AI 边界（诚实划分）

- 提交作者统一为 `AutoPilot`——如实表明工作树由 AI agent 在用户指导下产出。
  **不声称**每个提交由人手写。
- **人类拥有**：范围设定、验收关卡定义、合并/发布（ship）权限、Tier-C 决策（合规/账号/不可逆）。
- **AI 执行**：切片拆分、实现、自验证、子 agent 编排、Codex 复审回路。
- Codex 复审是 LLM 复审，定位为**自动化第二意见**，非人类签字。

## 5. 当前状态（不声称 100% 完成）

- 分支 `feature/mingjing-w1-core`，**尚未合并 main**，用户复审中。
- 已完成 GAP：G5、G6、G7、G9、G10、G11、G12、G13、G14、G20；10 个前端 hero 切片全部完成。
- 未决（如实）：Phase 0 豆包/Ark 切换（待组织方 key）、一处 ~5% 的既有 EvidenceAndQA 测试
  竞态（仅测试夹具层，活动应用已浏览器验证可用）、6 分钟录屏（人工，最后做）。

> 核验入口：`git log --oneline`（提交体含逐切片命令与结果）、`docs/qa/*.png`（浏览器证据）、
> `docs/superpowers/plans/`（规划契约）、Codex review-gate 配置。
