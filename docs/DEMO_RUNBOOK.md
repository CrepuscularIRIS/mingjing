# Demo Runbook

How to run the MingJing competitive-analysis demo reliably, and how to narrate it.

## A. Scored demo (deterministic corpus + real LLM)

The scored demo uses a curated, fetch-friendly source corpus (`demo/corpus/notion.json`,
verbatim spans of real server-rendered pages) so collection is reproducible, plus the
REAL analyst LLM so the reasoning/QA loop is genuine.

1. Start the backend (reads `MINGJING_DB`, serves the run to the frontend):

   **Against MiniMax (current testing model — the default in `.env.example`/`config.py`)** —
   set the MiniMax LLM env explicitly (these are also the shipped defaults):
   ```bash
   cd mingjing
   set -a; . ./.env
   MINGJING_LLM_BASE_URL=https://api.minimaxi.com/v1
   MINIMAX_MODEL=MiniMax-M2.7
   MINIMAX_API_KEY=$(grep -E '^MINIMAX_API_KEY=' ../.env | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')
   set +a
   uv run uvicorn mingjing.api:app --port 8000
   ```
   **Against the contest Doubao model** (practice/final smoke, 2026-06-10 key smoke
   verified): keep the key out of git and out of screenshots. Use a throwaway shell or
   a gitignored `.env` with placeholders only in docs:
   ```bash
   cd mingjing
   export MINGJING_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
   export MINIMAX_MODEL=ep-20260514111325-xjmj7
   export MINIMAX_API_KEY='<ARK_API_KEY from private contest channel; never commit>'
   uv run uvicorn mingjing.api:app --port 8000
   ```
   The smoke call returned HTTP 200 and model `doubao-seed-2-0-lite-260428`.
   **VERIFIED FULL RUN (2026-06-10): `33835db0e51b4f2586c092e37efbf13f`** — the whole
   pipeline on the contest EP (18 llm_calls all `ep-20260514111325-xjmj7`): 5 proposed →
   1 admitted at **strong** (user_persona, 4 sources, verbatim audit 100%), 4 withheld
   (VALUE_UNSUPPORTED ×2 / HALLUCINATED_SNIPPET ×2 / SCHEMA_GAP ×1), repair_delta +20%
   with tier upgrade, 4 QA rounds, 602 s / 53,987 tokens. The gate is equally strict
   under the official model — 答辩可指着 Observability 的模型列说"这是豆包跑出来的"。
   **历史盘上凭据已作废**（2026-06-10 实测：开题材料内两枚候选 key 对 Ark 均返回
   `401 The API key doesn't exist`，且 git 对象库全量扫描 0 命中）——跑完整 Doubao run
   必须使用私下渠道的现行 key，临时 export，不落盘。
   Ark may report `reasoning_tokens` and may or may not emit visible `<think>` blocks;
   treat chain-of-thought as provider-private test behavior. MingJing already strips
   `<think>...</think>` spans before JSON parsing/display, and the demo should show only
   final answers, source snippets, QA verdicts, and token counts.

2. Frontend: `make web` (Vite on :5173 or :5174; both proxy to :8000).

3. Drive the demo run (same LLM env exported as in step 1), then open the printed run in the frontend:
   ```bash
   MINGJING_MODE=cache_first uv run python scripts/run_demo.py Notion
   # prints: run_id=<id> ... done run_id=<id>
   ```
   (`make demo-reliable COMPETITOR=Notion` does this sourcing `mingjing/.env` as-is.
   To force Doubao, export the Ark env above in the same shell; to force MiniMax,
   export the MiniMax env above. Do not paste the Ark key into terminal history that
   will be shared in screenshots or recordings.)

4. On the frontend, select the run and walk the narrative:
   - **执行轨迹 (DAG):** collect → analyze → qa (reject) → revise → **collect again** → analyze → qa (pass) → write. The re-collect step is the key: a rejected claim with an evidence gap goes back to the Collector for more sources.
   - **QA 回放:** show a field that moved fail → pass after re-collection (e.g. `pricing_model`: round-0 thin source → SCHEMA_GAP → re-collect → round-1 authoritative pricing page → tiers extracted → pass).
   - **证据&溯源:** click a claim → its cited source (LIVE/CACHED badge).
   - **业务指标:** coverage / citation_rate / strong_rate / tokens.

### Verified result (MiniMax, cache_first, 2026-05-31)
4/5 fields pass (pricing_model, user_sentiment, feature_tree, user_persona — all moderate),
**coverage 0.8**, citation 1.0, ~34k tokens. This is after the QA routing fix (commit
18211c8) that routes evidence-gap rejections (SCHEMA_GAP/VALUE_UNSUPPORTED) to re-collection.

### Known limits (state honestly; don't oversell)
- **`swot` may not pass** (the 5th field): its sources don't yield a QA-passing structured value reliably. 4/5 is the expected demo state.
- **`strong` count is usually 0 in the passed set.** Scoring requires ≥2 *distinct supporting* domains for "strong"; the curated corpus mostly has one authoritative source per field, so claims land at "moderate". To show a "strong" claim, add a 2nd independent corroborating source for one field (corpus enhancement) — deferred.
- `revise_round_cap` = 2, so re-collection has 2 chances to close a gap before the run writes a partial report.

## B. 30-second LIVE segment (real network fetch, LIVE badge)

To show real collection (organizers endorsed showing collection capability separately):
run one fully-live fetch on a server-rendered target and show the LIVE badge.

- Trigger a normal `POST /runs` (no corpus) against a fetch-friendly competitor, or run the
  collector path live on a single server-rendered URL.
- **Caveat:** the default `python-requests` UA gets 403 from Wikipedia and many review sites
  (G2/Capterra/etc.), and vendor SPAs return JS-gate placeholders. Pick a server-rendered,
  UA-tolerant target (e.g. dbpedia, vendor docs/pricing pages) for the live segment, or keep
  it short and let the cached scored run carry the full report.

## C. 6-min 录屏 walkthrough script (6-tab ink/mirror UI)

> The frontend is a **6-tab BI workbench**. Drive it via deep-link
> `http://localhost:5173/?run=<id>`. Verified demo runs — real web evidence (cached
> verbatim spans of real pages); SIMULATED survey rows are badged and excluded from tiers:
> - `4fff4227cdce4661a654603566a0385e` — **the DEFAULT landing run** (`pickExample` auto-selects it).
>   **中文** report, Notion vs Linear, **6/10 admitted** (strong:1/moderate:5, 4 withheld with issue
>   codes), **repair_delta +42%** with the 真闭环确认 seal LIT, TWO arcs on one run (用户口碑
>   弱2源→中4源; Linear 定价 中2源→强4源), coverage 80% (swot honestly uncovered), 3 `qa_pass`
>   affirmative verdicts in trace, per-claim QA✓ stamps. Generated under the simulated-survey
>   exclusion — strong tiers from real sources only.
> - `3775d21a9b634b5a86854c613c3187c8` — EN repair-depth archive: weak→moderate, **+38%**,
>   1→5 sources, 4 admitted (强0·中4). Predates Chinese output and the SIMULATED split.
> - `969e744c45dc4f5a936930e529abc5fe` — alt fuller synthesis brief, repair_delta **+22%**.
>
> **The canonical 6-min single-run script (no run switching) lives in
> [DEFENSE-NARRATIVE.md §4](DEFENSE-NARRATIVE.md) — run it entirely on the default `4fff4227…`.
> RECORD FROM THAT SCRIPT, not the table below.**
>
> **录屏脱敏警告:画面中不得出现 `Race/Competition.md` 或开题原始材料(内含共享账号
> EP/APIKEY,未脱敏)。引用赛题要求时使用脱敏后的转述版本。**

### 附录(旧版,勿照此录制主片):EN 史料 run `3775d21a…` 的走查表

| Time | Tab | Say / show |
|------|-----|------------|
| 0:00–0:40 | (open `?run=3775d21a…`, top bar) | KPI 条: **已验证结论 4 条 / 覆盖率 80% / 引用率 100% / 证据强度构成 强0·中4·弱0**（成果型口径，不再显示易误读的“强证据率 0%”）；信誉条 **修正增益 +38% ↑ 真闭环确认**（绿色印章）+ 平均溯源度 100% + QA 轮次 4。一句话立论：“确定性 QA 闭环，LLM 不裁定真值。” |
| 0:40–1:50 | **分析报告** | BLUF 核心结论（衬线大字）→ 建议 → SWOT 2×2 → 对比 → 情报缺口。点任意句末 **引用 chip** → 就地打开证据抽屉、高亮原文。强调“每句话可溯源”。 |
| 1:50–2:50 | **QA 回放** | 自动选中被打回的结论 `4c892067`（PRICING_MODEL）。**始终可见的静态横向流**（非画布、无需平移缩放，判定 ≤10s 可读）：**PASS 1·初判 弱(1)**「No pricing information…」→ `打回·证据偏弱` → `重新取证 +4 来源` → `复核通过·已升级` → **PASS 2·复核 中(5)**（Notion 分层定价）。**升级幅度** tile：`1 来源 → 5 来源 · 弱 → 中`（真实数据，不写死）+ 规则：中 = 2+ 相互独立来源印证。这是 弱→中 可信度升级的钱镜头。 |
| 2:50–3:40 | **证据&溯源** | 左列选结论 → 中列来源卡：**LIVE / CACHED / 快照(SNIPPET)** 出处徽标 + content_hash + 查看原文（高亮 cited chunk）。若有冲突，右上 **N 处冲突** 徽标 + ContradictionCard。 |
| 3:40–4:30 | **执行轨迹** | 9 节点 DAG：采集→分析→质检→**打回重采(回边)**→撰写→**综合**。节点按 agent 角色着色 + 每节点 **N 次 · M tok** 徽标。点节点 → 右栏该 agent 的 LLM 调用/Prompt/输出/Token。 |
| 4:30–5:10 | **可观测** | Agent 列表 + **Token 用量柱状图**（recharts，prompt/completion）；点 agent 看其 Prompt/输出（密钥已脱敏）。证明“给我看你的工作”。 |
| 5:10–5:40 | **Schema 矩阵** | 竞品 × 字段网格，按证据强度着色；**换领域**下拉演示 config-driven 可扩展性（前瞻性）。缺口以 weak 色 + “缺口”标注（非红色报警）。 |
| 5:40–6:00 | **分析报告 → 人工修正** | 选一条结论 → 右栏 **人工修正**（采纳/驳回/编辑）→ 演示 HITL 反向通道（写回 produced_by=human:correction，更新人工修正率）。收尾回到立论：可信、可溯源、人在闭环。 |

### Pre-recording checklist
- [ ] Backend up: `curl -s localhost:8000/health` → `{"status":"ok"}`; frontend up: `curl -s -o /dev/null -w '%{http_code}' localhost:5173` → 200.
- [ ] Default flagship live: `curl -s localhost:8000/runs/4fff4227cdce4661a654603566a0385e/credibility` → repair_delta 0.423, is_tier_upgrade true.
- [ ] EN archive live: `curl -s localhost:8000/runs/3775d21a9b634b5a86854c613c3187c8/credibility` → repair_delta 0.376.
- [ ] Browser: 0 console errors on each tab; all endpoints 200; web evidence real (cached real pages); any SIMULATED survey row shows its 「模拟问卷数据·不参与分档」 badge. (Verified 2026-06-07 on `3775d21a`: 6/6 tabs render, 145/145 网络 200, 0 errors; 1 benign React Flow perf `warn` from 执行轨迹 only.)
- [ ] **QA 回放** money-shot renders visibly (regression guard): PASS 1 弱(1) → +4 来源 → PASS 2 中(5), 升级幅度 `1→5 来源 · 弱→中`. (Was an empty canvas before the 2026-06-07 static-flow fix.)
- [ ] **分析报告** KPI strip shows `证据强度构成 强0·中4·弱0` (not a bare “强证据率 0%”), and 情报缺口 panel points to the ledger (“综合简报暂未生成…账本（共 4 条）”), never “暂无达到可信门槛的结论” while claims exist.
- [ ] `prefers-reduced-motion` OFF on the recording machine so the §3c arrival motion + 真闭环 seal play.
- [ ] Desktop viewport (the demo target); window restored (not maximized-locked) for clean capture.
- [ ] Have `969e744c…` open in a second tab as the fuller-brief fallback.

### Tier-C (human) — the actual recording
The 6-minute screen recording itself is a **manual/human step** (not automatable here). Everything
up to it — verified runs, the 6-tab script, talking points, checklist — is prepared above.

## Honesty note for 答辩
The scored run uses a curated cached corpus for reproducibility (organizers endorsed 录屏 /
showing collection separately). The improvement (fail → pass) and the strength scoring are
produced by the REAL QA/scoring/write logic, not scripted — proven offline by
`tests/test_demo_feedback_loop.py` (a claim genuinely moves weak → pass through the loop with
honest citations). Keep one fully-live run on record showing the same convergence.
