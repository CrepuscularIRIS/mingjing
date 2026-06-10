# G3 + Judge-Dogfood Checkpoint — 2026-06-07

Closes the G21a / G3 checkpoint before any frontend rebuild. No new product-code
changes beyond resolving the Codex BLOCKING findings on G21a (below). Browser
verification done via Chrome DevTools (autoconnect) on the live frontend.

---

## 1. Live detailed CN run (G21a verification + G3 live attempt)

Two live MiniMax 飞书 runs were used to verify G21a and probe whether live CN can
produce a populated closed-loop demo.

| Run | depth | result |
|-----|-------|--------|
| `dbf1f27d…` | quick | 0 admitted; withheld = VALUE_UNSUPPORTED ×3 + SCHEMA_GAP ×1; **HALLUCINATED_SNIPPET ×0** (was ×7 pre-G21a) |
| `5f070e25dea646bdb4e2c39486238fdc` | detailed | ran real loops to round 2+ (10 `qa_fail`, 0 `qa_pass`); never reached synthesis within the timebox |

**Verdict:** the G21a snippet work eliminated the *snippet* false-rejects
(HALLUCINATED_SNIPPET → 0), but live CN 飞书 still admits **0 claims** because the
structured value leaves (pricing, etc.) are genuinely **not literally present** in
the thin live CN sources → VALUE_UNSUPPORTED fires correctly. This is honest QA
behavior, not a bug, and is NOT weakened. Live CN value-grounding is a deeper data
problem (tracked as G21b CN-collection / G21c Doubao), independent of the snippet fix.

**Consequence:** a populated reject→revise→pass demo cannot come from live thin-source
CN without faking evidence (forbidden). The canonical demo run is therefore a real
curated-corpus run (real LLM + real QA loop; only the source corpus is fetch-reliable,
which the organizers endorsed showing separately from live collection).

---

## 2. Codex stop-hook review of G21a — and the fix

Codex reviewed the original G21a commit `af9dac1` and found a **BLOCKING** hole, then a
second on the first fix. Both are now resolved (verbatim-or-reject); Codex final verdict
on `4bcb1ec`: **"No material findings."**

| Commit | what | Codex |
|--------|------|-------|
| `af9dac1` | original G21a: ground paraphrase → best-overlap source span | BLOCKING: a zero-overlap **fabrication** was masked by `raw[:200]` → passed HALLUCINATED_SNIPPET |
| `fa873b1` | score distinctive tokens; keep candidate when 0 overlap | BLOCKING: a fabrication sharing only the **competitor name** (1 token) still grounded → masked |
| `4bcb1ec` | **verbatim-or-reject**: remove span-grounding entirely; return analyst candidate unchanged; QA gate is sole arbiter | ✅ No material findings |

**Why verbatim-or-reject:** token-overlap grounding cannot separate a genuine reworded
paraphrase (which can share as little as the competitor name, or ~20 % of CJK bigrams)
from an outright fabrication — both sit in the same low-overlap region. Any substitution
either masks fabrications or false-rejects paraphrases. So snippet_for now returns the
analyst's candidate unchanged: a verbatim quote is admitted, anything else is rejected by
HALLUCINATED_SNIPPET and the claim is re-collected/revised. `qa/rules.py` untouched;
VALUE_UNSUPPORTED still strict. Full offline suite **674 passed**, ruff clean.

Codex repros now all behave correctly: `Phantom Platinum…` and `Acme Phantom Platinum…`
→ HALLUCINATED_SNIPPET; verbatim quote → admitted; fabricated value → VALUE_UNSUPPORTED;
non-string snippet/statement/raw_text → returns `str`, no crash.

---

## 3. Canonical G3 demo run — manifest

**run_id:** `3775d21a9b634b5a86854c613c3187c8` (curated corpus, competitor: Notion)

| metric | value |
|--------|-------|
| repair_delta | **0.433 (+43 %)** |
| claim_admission_rate | **0.80** |
| avg_groundedness | 1.0 |
| coverage | 0.80 |
| QA rounds | 4 |
| admitted claims | 4 (all moderate) |
| withheld | 1 (SCHEMA_GAP ×1, VALUE_UNSUPPORTED ×1) — disclosed honestly in UI |
| wall-clock | 277 s |

**QA Replay money-shot claim**

- claim id: `4c892067-4fac-474b-a4ba-7422f205ebed` (field PRICING_MODEL, Notion)
- versions: 4 — **v1 `weak` → v2 `moderate` → … → v4 `moderate`**
- source count: **1 → 5** (visible as "升级幅度 1 来源 → 5 来源, 弱 → 中" in QA Replay)
- real reject→revise→pass: QA flagged weak evidence → collector revised (new sources) →
  re-analyzed → re-QA'd → admitted at higher strength. Verified in the Activity Feed.

**Endpoints verified (HTTP 200 + correct shape)**

| endpoint | status |
|----------|--------|
| `/runs/{id}/report` | ✓ 4 sections, strength_tally {moderate:4} |
| `/runs/{id}/synthesis` | ✓ |
| `/runs/{id}/credibility` | ✓ repair_delta 0.433, rounds 4 |
| `/runs/{id}/claims/{cid}/history` | ✓ 4 versions weak→moderate |
| `/sources/{source_id}` (drawer) | ✓ url + raw_text + content_hash (dbpedia + notion.com/pricing) |
| `/runs/{id}/trace` | ✓ 92 events |
| `/runs/{id}/llm_calls` | ✓ 15 calls |
| `/schemas` (global) | ✓ {domains:[default,ai_agent,hr], active:default} |
| `/runs/{id}/survey-design` | 404 — this Notion run has no survey lane (expected; lane exists, just unused here) |

---

## 4. Judge dogfood — Chrome DevTools on `?run=3775d21a…`

**Global health:** console **0 errors / 0 warnings**; all XHR/fetch **200**. 6 tabs reachable.

| tab | verdict |
|-----|---------|
| 分析报告 (Report) | ✅ KPI strip (REPAIR_DELTA +43 % ↑, 真闭环确认, 准入率 80 %, QA 轮次 4, 平均溯源度 100 %), honest "为什么结论不多" withheld disclosure, 4 claims each with "View QA history →" |
| Schema 矩阵 | ✅ Notion × 5 fields, strength-colored `Moderate (5)` cells, SWOT `缺口` marker, domain switcher |
| 证据&溯源 | ✅ claim → CACHED source cards (URL + type + content_hash + 查看原文); right rail shows v1 weak → v4 moderate progression (citation→source money shot works) |
| QA 回放 | ⚠️ **React Flow canvas renders EMPTY in the viewport** — the weak→中 node graph is not visible on load; fit-view did not surface nodes. Only the "升级幅度 1→5 来源, 弱→中" badge + Rule line show. **This is the headline money-shot and is the #1 blocker.** |
| 执行轨迹 | ✅ full DAG intake→plan→collect→analyze→qa→route→(revise↺)→write→synthesis, live node states, revise loop-back edge, status legend, LangSmith link (React Flow works fine here) |
| 可观测 | ✅ agent list (analyst 15 calls), click-to-inspect, TOKEN USAGE BY AGENT bar chart |

---

## 5. Ranked frontend rebuild backlog (from the dogfood)

> Do NOT begin the full rewrite until this checkpoint is confirmed. Ranked by demo impact.

**P0 — money-shot blockers**
1. **QA Replay React Flow canvas renders empty / nodes invisible on load.** The dedicated
   reject→revise→pass graph — the single most important credibility visual — shows no nodes
   in the viewport even after fit-view. Trace DAG (same library) works, so it is a
   view-specific layout/height/auto-fit bug in QA Replay. The weak→strong story currently
   only survives via the 证据&溯源 right rail and the 升级幅度 badge. Fix layout so the
   version-node graph is visible and auto-fit on mount. (Until fixed, demo the delta from
   the Report KPI + 证据&溯源 rail, not the QA 回放 graph.)

**P1 — credibility-label clarity**
2. **`强证据率(准确率代理) 0%` sits prominently in the KPI strip** while every other number
   is strong. With 4 moderate / 0 strong claims this reads as "0 % accuracy", underselling a
   good run. Reframe (e.g. show strong+moderate, or relabel as "strong-evidence share" with a
   tooltip) so it does not look like a failure metric.
3. **情报缺口 section contradicts itself.** It reads "暂无达到可信门槛的结论；当前情报缺口"
   and "本节数据不足" even though 4 claims ARE verified directly below. Gate the empty-state
   copy on whether admitted claims exist.

**P2 — polish / demo-feel**
4. **Activity Feed is very long and duplicated across views** (every per-source
   collect-start/finish). Collapse repeated collector events or group by round so the feed
   reads as a clean narrative during the demo.
5. **Screenshot/canvas capture intermittently times out** under 2 s polling + React Flow.
   Consider pausing polling on terminal runs (status partial/done) to cut idle churn and
   make the UI feel snappier on the demo machine.

**Non-blockers (already good, keep):** Report KPI strip, honest withheld disclosure,
Evidence/溯源 drawer with CACHED provenance + hashes, Execution Trace DAG, Observability
token chart, Schema matrix.

---

## 6. Hard-constraint compliance

- ✅ no mock demo data — canonical run is a real LLM + real QA-loop run; live CN runs are real
- ✅ no fake closed loop — repair_delta 0.433 / 4 rounds / weak→moderate are real persisted history
- ✅ QA/evidence/PII/robots/credibility invariants NOT weakened — `qa/rules.py` untouched; the
  G21a fix makes the snippet gate *stricter* (no masking)
- ✅ browser verification done (Chrome DevTools, 0 console errors)
- ✅ Codex review done — final "No material findings"
- ✅ not pushed (Tier-C)
