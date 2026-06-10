# MingJing Launch Film — TODO

Live checklist. `[x]` done · `[~]` in progress · `[ ]` not started. See SPEC.md / PLAN.md.

## Phase 0 — Environment (DONE)
- [x] Scaffold standalone Remotion project; deps installed; `npm run still` green; `tsc` clean
- [x] `theme.ts` mirrors MingJing tokens; Google-fonts weights constrained
- [x] Shallow-clone Remotion monorepo → `reference/remotion/` (gitignored, ~1.1 GB)
- [x] SPEC / PLAN / TODO / VOICEOVER docs
- [x] Pull canonical run `4fff4227` real data from live app DB → `src/data/run.ts`

## Phase 1 — Skeleton & shared kit (DONE)
- [x] Composition `MingJingLaunch` → `out/mingjing-launch.mp4`; `scripts/render.sh` + `preview.sh`
- [x] `public/audio/.gitkeep`, `out/.gitkeep`
- [x] `src/timeline.ts` — single SoT for chapter order/durations/captions (~6:16, two cases)
- [x] Burned-in captions + chapter-progress bar (`Overlays.tsx`)
- [x] `config.ts::HAS_VOICEOVER` gate — silent render if no `voiceover.wav`
- [x] Primitives: `KpiChip` / `AnimatedNumber` / `TierBadge` / `DepthCard` / `Rise` / `Eyebrow`;
      `AppFrame` (MingJing window chrome) + `Chapter` wrapper

## Phase 2 — Scenes (DONE — 12 chapters)
- [x] 00 Title · 01 Problem · 02 Approach (产品构建思路) · 03 Architecture (前端/后端/编排/数据)
- [x] 04 Input · 05 Agent DAG (reject back-edge)
- [x] 06 Report — AppFrame: BLUF + SWOT + 引用 chip  ← frontend case
- [x] 07 Credibility — AppFrame: KPI chips, 漏斗 10→6·4, 强1·中5·弱0, +42%  ← frontend case
- [x] 08 QA Replay money-shot — 弱2 → 打回 → +2源 → 复核 → 中4; +42% seal; 2nd arc 中→强  ← frontend case
- [x] 09 Evidence — AppFrame: URL/snippet/hash/LIVE·CACHED·SNIPPET/Admiralty/admitted  ← frontend case
- [x] Business impact (16–40h → 23分6秒 · 42–104×) · Final

## Phase 3 — Assembly & audio
- [x] Wire scenes via `timeline.ts`; total ≈ 6:16 (two cases); caption cues (中文) + progress bar
- [ ] Scene transitions (`@remotion/transitions`) — optional polish
- [ ] Record `voiceover.wav` (user, from VOICEOVER.md) → flip `config.ts::HAS_VOICEOVER`

## Phase 4 — Render & QA
- [~] Full render → `out/mingjing-launch.mp4` (in progress)
- [x] Visual QA vs real UI (stills): money-shot / report / credibility / evidence / dag / problem / final
- [x] CJK renders in headless shell
- [ ] Commit "add Remotion launch video package" (exclude reference/, node_modules/, out/)

## Open / needs user
- [ ] Record voiceover (optional — film renders silent with burned-in captions)
- [ ] Optional: add cross-scene transitions; tune any per-scene timing after first full review
