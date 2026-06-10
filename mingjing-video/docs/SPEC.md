# MingJing Launch Film — SPEC

> ⚠️ **SUPERSEDED for structure — see [`../REPORT.md`](../REPORT.md) for the as-delivered film.**
> The original single-case 9-scene storyboard below is historical. The shipped film is a
> **two-case, 20-chapter, ≈6:16** cut (案例一 Notion `3775d21a` + 案例二 Notion×Linear
> `4fff4227`, all 6 pages). The **design tokens (§3) and the canonical numbers (§4) below are
> still authoritative** and have been corrected to the live `/metrics` values (23分6秒 / 42–104×).

**Status:** v2 · 2026-06-10 (numbers reconciled to live `/metrics`)
**Deliverable:** `out/mingjing-launch.mp4` — a ≈6:16 premium product launch film for the
MingJing (明镜) CIS competition, rendered with Remotion (React → MP4). Serves as the
演示视频 deliverable.

---

## 1. Goal & non-goals

**Goal.** A cinematic explainer that sells MingJing's *thesis*, not its feature list:
not "it generates a competitive-analysis report" but "it generates an **auditable**
competitive-intelligence *process*" — claim-level provenance, a deterministic QA gate,
a real repair loop, admitted/withheld claims, source-grounded evidence. Emotional peak =
the QA repair money-shot (weak evidence → QA rejects → re-collect → tier upgrade).

**Non-goals.**
- Not a feature tutorial / not a 6-min full walkthrough (that's the OBS recording).
- Not a screen recording — it's motion design that *recreates* the UI in Remotion.
- No live API calls, no keys, no paid services, no TTS dependency.

## 2. Hard constraints

- Everything under `mingjing-video/`. **Do not modify** `mingjing/` app behavior — read-only
  access to its design tokens / screenshots / exported run JSON only.
- 1920×1080, 30fps (as delivered ≈6:16, two cases; original target was 3–4 min).
- Renders locally to MP4 via `npx remotion render` (Remotion bundles its own Chrome + ffmpeg).
- **Burned-in subtitles/captions** on every scene (so it reads even muted).
- Optional local voiceover at `public/audio/voiceover.wav` via `<Audio src={staticFile(...)} />`;
  **render must not fail if the file is absent** (guard with a fallback).
- **Every on-screen number must trace to a real run export** (see §4). No invented figures.

## 3. Design system — USE MINGJING TOKENS (override GPT's generic palette)

> GPT's brief suggested "deep navy / cyan / violet". **Ignore that.** The user's instruction
> is to base the film on the *actual MingJing frontend*, and an honesty-themed product must
> look like itself. Tokens are mirrored verbatim in `src/theme.ts` from
> `mingjing/frontend/tailwind.config.js` + `index.css`.

| Role | Token | Hex |
|------|-------|-----|
| Canvas (page) | ink-50 | `#0a0e10` |
| Raised panel | ink-100 / depth-card | `#11171a` |
| Border / hairline | ink-200 | `#1b2329` |
| Muted text | ink-600 | `#a7b4ba` |
| Primary text | ink-900 | `#f1f5f6` |
| Brand accent "mirror" (primary action) | mirror-400 | `#449a96` |
| Brand bright (text/icon on dark) | mirror-300 | `#71bbb6` |
| **Money-shot lime** (repair_delta / 真闭环 / gains ONLY) | lime-500 | `#84cc16` |
| Strong evidence | strong | bg `#11271b` / text `#5fd08a` / border `#2e9e5a` |
| Moderate evidence | moderate | bg `#16182e` / text `#9aa0ee` / border `#6060b8` |
| Weak evidence (never red) | weak | bg `#241f10` / text `#d9c06a` / border `#b89830` |

Type: **Inter** (UI/body), **Source Serif 4** (report + brand wordmark / BLUF big type),
**JetBrains Mono** (metric numerals). CJK falls back to system serif/sans in the headless shell.
Surfaces: `depth-card` (raised slate + hairline + inner top highlight), `glass-surface`
(translucent dark chrome), ambient dot-grid + soft teal radial glow. Motion is *arrival-only*
(spring in, settle) — never idle loops; mirrors the product's `prefers-reduced-motion` ethos.

## 4. Single source of truth for numbers — canonical run `4fff4227`

The film is driven by ONE real run. **These are the corrected figures** (GPT's brief had
wrong numbers — listed for contrast so we never regress to them).

### Default landing run — `4fff4227cdce4661a654603566a0385e`
Notion vs Linear · multi-competitor **matrix** · **Chinese** output · generated under the
simulated-survey exclusion (tiers from real sources only).

| Metric | **Real value (USE THIS)** | GPT brief said (WRONG) |
|--------|---------------------------|------------------------|
| Claims proposed → admitted → withheld | **10 → 6 → 4** (4 withheld w/ issue codes) | 10 → 7 → 3 |
| Tier mix | **强 1 · 中 5 · 弱 0** | strong 4 / moderate 3 |
| repair_delta | **≈ 0.423 (+42%)**, `is_tier_upgrade=true`, 真闭环确认 seal lit | +38% |
| Repair arcs (TWO) | **用户口碑 弱(2源)→中(4源)** AND **Linear 定价 中(2源)→强(4源)** | single weak→moderate |
| Coverage | **80%** (swot honestly uncovered, self-disclosed in 情报缺口) | 100% |
| Citation rate | **100%** | — |
| Elapsed / speedup | **23分6秒（live /metrics elapsed 1385.8s）· 约 42–104×**（基线 16–40h 估算） | ~17min · 57–142×（WRONG run） |
| QA rounds | 3 `qa_pass` affirmative-verdict trace events | — |

Deep link: `http://localhost:5173/?run=4fff4227cdce4661a654603566a0385e`
Verify: `GET /runs/4fff4227…/credibility` → `repair_delta 0.423, is_tier_upgrade true`.

### Repair-depth archive (alt, EN) — `3775d21a9b634b5a86854c613c3187c8`
Notion single · **depth** · EN. weak→moderate, repair_delta ≈ **0.376 (+38%)**, sources
**1 → 5**, 4 admitted (强0·中4). Predates Chinese output + the simulated-survey split. Kept as
history; **don't lead with it** (single-competitor, no strong tier).

> **Honesty chain (答辩 point):** the video does not hardcode these by hand. We export the run's
> real `/credibility` + `/metrics` + report JSON into `src/data/run-4fff4227.json` and drive the
> compositions from that fixture. On-screen numbers therefore trace to the same run a judge can
> open in the live app. This mirrors the product's own "升级幅度…（真实数据，不写死）" rule.

## 5. Composition & storyboard

Composition id **`MingJingLaunch`**, `out/mingjing-launch.mp4`. Scenes are a `<Series>`;
`SCENE_FRAMES` drives total duration. Visual reference = the real UI screenshots in the repo
root (`a4-report.jpeg`, `a4-qareplay.jpeg`, `a4-evidence.jpeg`, `audit-02-moneyshot.png`) and
the components named below — recreate their *layout*, don't screenshot them.

| # | Scene | ~dur | Content (real data) | UI reference |
|---|-------|------|---------------------|--------------|
| 1 | **Title** | 8s | 明镜 MingJing · "Traceable Competitive Intelligence Agent" · thesis "It knows when it should not be confident." | wordmark |
| 2 | **Problem** | 15s | "Deep Research gives a report you can only **trust**." → "MingJing gives a report you can **audit**." (weak-yellow vs strong-green) | — |
| 3 | **Input** | 18s | Polished run form: Category=通用 AI Agent · Market=中国 · Competitors=**自动发现** · Goal (task exec / workflow / RAG / enterprise / pricing / auditability) | run form (left rail) |
| 4 | **Agent team / DAG** | 22s | Animated DAG **Collector → Analyst → QA → Writer** with the reject back-edge `qa → collect`; "structured messages, not free-form chat" | `ExecutionTrace.tsx` 9-node DAG |
| 5 | **Report result** | 25s | Header KPI chips: 已验证 **6** · 覆盖率 **80%** · 引用率 **100%** · 准入漏斗 **10 提议 → 6 准入 · 4 暂存** · 强1·中5·弱0 | `KpiBar.tsx`, `CredibilityPanel.tsx`, `StrengthTally.tsx` |
| 6 | **QA repair / MONEY-SHOT** | 35s | Static horizontal flow: **PASS 1 · 初判 弱(2源)** "用户口碑证据偏弱" → `QA 打回 · 证据偏弱` → `重新取证 +2 来源` → `QA 复核通过 · 已升级` → **PASS 2 · 复核 中(4源)**. 升级幅度 tile `2→4 来源 · 弱→中`. Then the second arc Linear 定价 `中→强`. **REPAIR_DELTA +42%** lime card + 真闭环确认 seal. Rule chip "中 = 2+ 相互独立来源印证". | `QAReplay.tsx`, `QAReplayFlow.tsx` |
| 7 | **Evidence drawer** | 22s | Claim card → cited source: **URL · 原文 snippet (highlighted cited chunk) · content_hash · LIVE/CACHED/SNIPPET badge · QA verdict · admitted/withheld** | `EvidenceDrawer.tsx`, `EvidenceAndQA.tsx`, `CitedSentence.tsx` |
| 8 | **Business impact** | 18s | Analyst baseline **16–40h（行业估算）** → MingJing **23分6秒 (replay-measured)** · 约 **42–104× 提速** · claim-level provenance · deterministic QA gate · replayable trace | `KpiBar` baseline tile |
| 9 | **Final** | 15s | "Not just a report." → "An auditable intelligence workflow." → 明镜 MingJing · "It knows when it should not be confident." | wordmark |

*(Historical single-case plan ≈ 178s. As delivered the film is two-case, ≈6:16 —
see `../REPORT.md` and `src/timeline.ts` for the actual chapter list & durations.)*

## 6. Audio & subtitles

- `<Audio src={staticFile("audio/voiceover.wav")} />` wrapped so a missing file → silent render
  (probe via a build-time flag or `try/catch` import; never throw in the composition).
- Captions: one `<Subtitle>` component, burned in bottom-center, per-scene cue list in
  `src/captions.ts` (Chinese primary; the VOICEOVER.md script is the source text).
- Recommended audio path: user records `voiceover.wav` by reading `docs/VOICEOVER.md` (no TTS).

## 7. Render pipeline

```bash
npm run dev      # Remotion Studio — live preview / scrub
npm run still    # one frame → out/title.png (smoke test)
npm run render   # full film → out/mingjing-launch.mp4 (H.264)
# explicit: npx remotion render MingJingLaunch out/mingjing-launch.mp4
```

If render is slow: reduce heavy effects (blur/glow layers, particle beams), **not** duration.

## 8. Open decisions (tracked in TODO)

- [ ] Export real run JSON from the live app vs. transcribe the verified figures into a fixture.
- [ ] Lead money-shot = the two-arc `4fff4227` (recommended) vs. the simpler `3775d21a` 1→5.
- [ ] Voiceover language: Chinese (matches default run + judges) — recommended; EN optional v2.
