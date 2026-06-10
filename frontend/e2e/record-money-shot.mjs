/**
 * record-money-shot.mjs — auto-record the 6-minute MingJing money-shot demo.
 *
 * Drives the running workbench through the canonical credibility beat-sheet
 * (DEFENSE-NARRATIVE.md §4) and saves BOTH a video (.webm) and per-beat PNG
 * key-frames, so the 答辩 录屏 is reproducible and never depends on a hand-run.
 *
 * Beats (all by stable data-testid, no brittle selectors):
 *   0  home / run picker
 *   1  查看示例分析 → report: evidence-legend + 看闭环 banner + +43% hero
 *   2  看闭环 → QA Replay money-shot (PASS1 弱 → +N 来源 → PASS2 中, level-up tick)
 *   3  linger on the money-shot frame (弱→中 · 1→5 · +43%)
 *   4  back to report → credibility (repair_delta + 真闭环确认)
 *
 * Prereq (one-time): the app must be running (make api + make web), then
 *   cd mingjing/frontend
 *   npm i -D playwright            # or: use a global playwright install
 *   npx playwright install chromium
 *   node e2e/record-money-shot.mjs            # MJ_BASE overrides the URL
 *
 * Output: e2e/recordings/  (money-shot.webm + beat-*.png)
 */
import { chromium } from 'playwright';
import { mkdirSync, renameSync } from 'node:fs';
import { join } from 'node:path';

const BASE = process.env.MJ_BASE || 'http://localhost:5173';
const OUT = 'e2e/recordings';
const VIEWPORT = { width: 1440, height: 900 };

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: VIEWPORT,
  recordVideo: { dir: OUT, size: VIEWPORT },
  // deterministic, judge-readable motion: real animations, no reduced-motion.
});
const page = await context.newPage();
const video = page.video(); // capture the handle now; resolve its path after close

const beat = async (n, label) => {
  await page.screenshot({ path: join(OUT, `beat-${n}-${label}.png`) });
  console.log(`beat ${n}: ${label}`);
};
const settle = (ms) => page.waitForTimeout(ms);

// 0 — home / run picker
await page.goto(BASE, { waitUntil: 'networkidle' });
await settle(1200);
await beat(0, 'home');

// 1 — one-click example → report (legend + 看闭环 banner + +43% hero settle)
await page.getByTestId('view-example-btn').click();
await page.getByTestId('see-closed-loop-btn').waitFor({ timeout: 15_000 });
await settle(2500); // let the NumberTickers settle to +43% / 80% / 4 条
await beat(1, 'report');

// 2 — jump straight to the money-shot
await page.getByTestId('see-closed-loop-btn').click();
await page.getByTestId('qa-moneyshot').waitFor({ timeout: 15_000 });
await settle(2500); // level-up tick: 1 → 5 来源, 弱 → 中
await beat(2, 'qa-replay');

// 3 — linger on the single most screenshot-worthy frame
await settle(1800);
await beat(3, 'money-shot');

// 4 — back to report → credibility hero (repair_delta + 真闭环确认)
await page.getByTestId('nav-report').click();
await settle(2200);
await beat(4, 'credibility');

await context.close(); // finalizes the video file
await browser.close();

// Give THIS run's recorded video a stable name (resolve the exact path from the
// page's own video handle — never glob the dir, which could grab a stale .webm).
if (video) {
  const vp = await video.path();
  renameSync(vp, join(OUT, 'money-shot.webm'));
  console.log('video → e2e/recordings/money-shot.webm');
}
console.log('done — key-frames + video in e2e/recordings/');
