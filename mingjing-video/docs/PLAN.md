# MingJing Launch Film — Implementation Plan

Phased build. Each phase ends green (`tsc --noEmit` clean + a still/preview render).
See `SPEC.md` for the authoritative scene + data spec, `TODO.md` for the live checklist.

## Phase 0 — Environment (DONE / this turn)

- ✅ Standalone Remotion project `mingjing-video/` (manual scaffold = "Blank" template;
  `create-video` is interactive-only). Node 22 / npm 11 / google-chrome verified.
- ✅ Deps installed; `npm run still` renders end-to-end; `tsc --noEmit` clean.
- ✅ `theme.ts` mirrors MingJing tokens; Scene 1 (Title) built & rendered.
- ⏳ Official Remotion monorepo shallow-cloned to `reference/remotion/` (templates + docs
  for borrowing transition/text/cinematic patterns — `reference/` is gitignored).
- ⏳ Planning docs: SPEC / PLAN / TODO / VOICEOVER (this turn).

## Phase 1 — Project skeleton & shared kit

- Rename composition `MingJingVideo` → **`MingJingLaunch`**, output `out/mingjing-launch.mp4`
  (align with GPT's render command + SPEC).
- `scripts/render.sh`, `scripts/preview.sh`; `public/audio/.gitkeep`, `out/.gitkeep`.
- Audio wrapper (`components/Voiceover.tsx`) — graceful no-op when the wav is missing.
- Caption system (`components/Subtitle.tsx` + `src/captions.ts`) — burned-in cue list.
- Shared primitives under `src/components/`: `KpiChip`, `AnimatedNumber` (spring count-up),
  `EvidenceTierBadge` (strong/moderate/weak), `DepthCard`, `StatusChip`, `Beam`/`DagEdge`.
- `src/data/run.ts` — the canonical `4fff4227` figures as a typed fixture (single source;
  ideally exported from the live app — see TODO data-export task).

## Phase 2 — Scenes (in money-shot-first order)

Build the emotional spine first so we can judge pacing early:

1. **Scene 6 — QA repair money-shot** (highest value; the static horizontal flow + REPAIR_DELTA
   lime card + 真闭环 seal + two arcs). Reference `a4-qareplay.jpeg`.
2. **Scene 5 — Report result** (KPI chips, funnel, tier tally). Reference `audit-02-moneyshot.png`.
3. **Scene 4 — Agent DAG** (Collector→Analyst→QA→Writer + reject back-edge).
4. **Scene 7 — Evidence drawer** (claim → URL/snippet/hash/badge/verdict).
5. **Scene 2 — Problem**, **Scene 3 — Input**, **Scene 8 — Business impact**.
6. **Scene 9 — Final** (reuse Title kit).
7. Title (Scene 1) already done — polish to match final type scale.

## Phase 3 — Assembly, timing, audio

- Wire all scenes into `<Series>` via `timeline.ts`; tune cue timing to the voiceover.
  (As delivered: ≈6:16, two cases — this PLAN's earlier 3–4 min target is historical.)
- Add transitions (`@remotion/transitions` fade/slide) between scenes — restrained.
- Drop in `voiceover.wav` if recorded; otherwise ship silent + captions.
- Subtitle cue timing pass.

## Phase 4 — Render & QA

- `npm run render` → `out/mingjing-launch.mp4`; watch for slowness (cut effects, not length).
- Visual QA against the real UI screenshots; verify every number matches `run.ts`/the live run.
- Commit: **"add Remotion launch video package"** (exclude `reference/`, `node_modules/`, `out/`).

## Parallelism (4-hour crunch division of labor)

| Track | Owner | Work |
|-------|-------|------|
| Video engineering / animation | Claude Code | Phases 1–4 |
| Voiceover | user | record `voiceover.wav` from `docs/VOICEOVER.md` |
| Main UI polish | other process | unchanged — this project never touches `mingjing/` |
| Last 60 min | all | render MP4 + check audio/captions + upload |

## Risks

- **Wrong numbers on screen** → mitigated by the single `run.ts` fixture + verify-against-live step.
- **CJK font in headless shell** → relies on system CJK; verify in the first money-shot render.
- **Render time at 1080p/30fps ~3–4 min** → keep glow/blur layers cheap; raise concurrency if needed.
- **Scope creep into a full tutorial** → SPEC caps it at thesis + money-shot; OBS covers depth.
