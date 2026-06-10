# e2e — money-shot demo recorder

`record-money-shot.mjs` auto-records the 6-minute MingJing credibility money-shot
(the canonical 答辩 beat-sheet in `mingjing/docs/DEFENSE-NARRATIVE.md §4`) as a
video **and** per-beat PNG key-frames — so the 录屏 is reproducible and never
depends on a flawless hand-run.

## Run

```bash
# 1. the app must be up (same DB the demo run lives in)
make api          # :8000
make web          # :5173

# 2. one-time: get a Playwright + chromium for the recorder
cd mingjing/frontend
npm i -D playwright
npx playwright install chromium

# 3. record (MJ_BASE overrides the URL if needed)
node e2e/record-money-shot.mjs
```

Output lands in `e2e/recordings/` (git-ignored):
- `money-shot.webm` — the screen recording
- `beat-0-home.png … beat-4-credibility.png` — key-frames for slides/cover

## Beats (driven by stable `data-testid`)

| # | testid | what's on screen |
|---|--------|------------------|
| 0 | `view-example-btn` | run picker |
| 1 | `see-closed-loop-btn` appears | report: 证据图例 + 看闭环 banner + **+43%** hero |
| 2 | `qa-moneyshot` | QA Replay: PASS1 **弱(1)** → +4 来源 → PASS2 **中(5)**, level-up tick |
| 3 | — (linger) | the screenshot frame: **弱→中 · 1→5 · +43%** |
| 4 | `nav-report` | credibility hero: repair_delta + **真闭环确认** |

The recorder uses real (non-reduced) motion so the NumberTicker level-up and the
seal animation are captured. It selects only by `data-testid`, so it is robust to
copy/layout changes. The default example run (`pickExample` → most passed claims)
is the canonical Notion weak→中 money-shot. The Linear strong-tier run is the
`强` backup — **generate it on demand** with
`MINGJING_MODE=cache_first uv run python scripts/run_demo.py Linear` (needs the
LLM key), then load it from 近期运行 or by `?run=<id>`.
