# MingJing Launch Film (明镜 · 产品宣传片)

Programmatic **product explainer / launch film** for MingJing, built with
[Remotion](https://remotion.dev) (React → MP4). It mirrors the MingJing
frontend design system (dark "ink" canvas, teal "mirror" accent, lime
money-shot, honest strong/moderate/weak evidence palette) so the film looks
like the product, not a slideshow.

> Standalone — does **not** touch the `mingjing/` app. Renders MP4 directly:
> no live API calls, no secrets, no Playwright needed (Remotion drives its own
> headless Chrome and bundles its own ffmpeg).

## Planning docs (read these first)

| Doc | What |
|-----|------|
| [`docs/SPEC.md`](docs/SPEC.md) | Authoritative spec — goal, constraints, design tokens, **canonical run `4fff4227` numbers**, scene-by-scene data |
| [`docs/PLAN.md`](docs/PLAN.md) | Phased implementation plan + crunch division of labor |
| [`docs/TODO.md`](docs/TODO.md) | Live build checklist |
| [`docs/VOICEOVER.md`](docs/VOICEOVER.md) | Chinese narration script + per-scene burned-in captions |

## Prerequisites

- Node ≥ 18 (this machine: v22) + npm — ✅ ・ `npm install` already run — ✅
- Chrome Headless Shell — auto-downloaded by Remotion on first render — ✅
- ffmpeg — **not required** (Remotion bundles its own, outputs H.264 MP4).

## Commands

```bash
npm run dev        # Remotion Studio — live preview / scrubbing
npm run still      # one frame → out/title.png (fast smoke test)
npm run render     # full film → out/mingjing-launch.mp4 (H.264)
./scripts/render.sh   # same as npm run render, with size report
./scripts/preview.sh  # same as npm run dev
```

Iterate on a specific frame/range:

```bash
npx remotion still   MingJingLaunch out/frame.png --frame=55
npx remotion render  MingJingLaunch out/mingjing-launch.mp4 --frames=0-240
```

## Structure

```
mingjing-video/
├── docs/               # SPEC / PLAN / TODO / VOICEOVER
├── scripts/            # render.sh, preview.sh
├── public/audio/       # drop voiceover.wav here (optional; render works without)
├── reference/remotion/ # shallow clone of the official Remotion monorepo (gitignored,
│                       #   ~1.1 GB) — borrow templates/transitions/cinematic patterns
├── out/                # rendered output (gitignored)
└── src/
    ├── index.ts            # registerRoot
    ├── Root.tsx            # <Composition id="MingJingLaunch"> 1920×1080 @ 30fps
    ├── MingJingLaunch.tsx  # storyboard — <Series> of scenes + SCENE_FRAMES
    ├── theme.ts            # MingJing design tokens (mirrored from tailwind.config.js) + fonts
    ├── components/
    │   └── Background.tsx   # ambient dark dot-grid + teal glow
    └── scenes/
        └── TitleScene.tsx   # Scene 1 — title / thesis (done)
```

## Structure (as delivered — ≈6:16, two cases, all 6 pages)

Authoritative source = [`src/timeline.ts`](src/timeline.ts) (20 `Series.Sequence`).
Full breakdown + acceptance mapping in [`REPORT.md`](REPORT.md).

- **00–05** 开场（真实封面）· 问题 · 产品思路 · 架构 · 输入（真实表单）· Agent DAG
- **案例一 · Notion 单一竞品** (`3775d21a`)：报告 · QA 回放（定价 **弱1→中5 · +38%**）· 执行轨迹
- **案例二 · Notion × Linear** (`4fff4227`)：报告 · 可信度（**+42%** · 漏斗 10→6 · 强1中5弱0 · 覆盖 80% · 引用 100%）· QA 钱镜头（双弧线）· 证据溯源 · Schema 矩阵 · 可观测
- **诚实性硬证据**（逐字 100% · 校准 P/R/acc=1.00 · 豆包实跑）· **业务价值**（16–40h → **23分6秒** · 约 **42–104×**）· 收尾

> All numbers trace to the live runs (`/metrics`, `/credibility`). The cover is re-rendered from
> the current `docs/presentation/cover.html` and shows **+42% (run `4fff4227`)**, consistent with
> the film body.

## Adding a scene

Create `src/scenes/XxxScene.tsx`, add a `ChapterDef` to `CHAPTERS` in `src/timeline.ts`,
and map its `id` in `MingJingLaunch.tsx`. Composition length follows the timeline
automatically. Colors/fonts from `src/theme.ts`. Real-page beats use `ShotScene`
(spotlight rects are calibrated from live DOM `getBoundingClientRect`).
