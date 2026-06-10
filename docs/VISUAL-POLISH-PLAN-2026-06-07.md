# MingJing Frontend Award-Polish Plan — 2026-06-07 (Goal mode)

Raise the frontend from submission-ready workbench → award-level **premium Chinese
enterprise intelligence / BI workbench** (Linear / Vercel / Bloomberg register), WITHOUT
breaking the locked demo path. No new framework; keep Vite + shadcn/ui.

## Baseline (Slice 0 — recorded, all green)
- HEAD `5710611`; tracked tree clean. `tsc -b` ✓, lint ✓, build ✓ (pre-existing large-chunk warn only).
- **206 frontend tests pass.** API+WEB up; canonical `3775d21a` real (repair_delta 0.433).
- Rollback point: `git reset --hard 5710611` (or revert per-slice commits).

## Assets available (no new deps)
- `motion` (framer-motion) + `cn` already present → vendor magicui MIT primitives as-is.
- magicui registry: `UI/magicui/apps/www/registry/magicui/{border-beam,shine-border,number-ticker,dot-pattern,magic-card,animated-list,aurora-text,flickering-grid}.tsx`
- react-bits ts-tailwind: `SpotlightCard`, `GlassSurface`, `Counter`, `AnimatedList`, `StarBorder`, `FadeContent`.
- Existing keyframes: `upgrade`, `loopSeal` (tailwind.config.js); reduced-motion reset in index.css.

## Vendoring policy
Copy small components into `src/components/ui/` (vendored, reviewed), rewrite imports to `../../lib/utils`.
Prefer dependency-light/CSS where trivial. Each vendored file gets a header noting source + adaptation.

## Slices (each: SDD review fan-out → implement → browser-verify → Codex → 1 commit)
1. **Visual system** — vendor `NumberTicker`, `BorderBeam`, `ShineBorder`, `DotPattern`, `MagicCard/Spotlight`;
   add depth/elevation + glass utilities + motion primitives to index.css/tailwind; reduced-motion safe.
   *No data contracts touched.*
2. **App shell** — premium sidebar + top status bar + ambient dot-grid bg at low opacity; canonical run identity.
3. **Credibility hero** — `repair_delta +43%` as protagonist: NumberTicker + BorderBeam/ShineBorder ONLY on the
   repair_delta tile + 真闭环确认 seal. Keep honest KPI copy (已验证结论/覆盖率/引用率/证据强度构成). No 强证据率 0%.
4. **Report + citations** — depth/typography rhythm; elegant clickable citation chips; drawer path obvious.
5. **Evidence/provenance** — Spotlight/MagicCard depth on source cards; LIVE/CACHED/SNIPPET/hash readable.
6. **QA Replay** — preserve working static flow; cinematic-but-credible (PASS1 弱(1) → +4 来源 → PASS2 中(5)).
7. **Trace + Observability** — DAG depth + node badges; revise loop-back obvious; redacted logs.
8. **Schema + HITL** — premium comparison grid; honest correction controls.
9. **Final rehearsal** — Playwright/Chrome DevTools all 6 tabs; 0 console errors; all 200; screenshots; self-score.

## Risks & guards
- Tests assert classNames/testids → preserve all testids; add wrappers, don't rename existing hooks.
- Money-shot (QA Replay) is locked → visual-only, keep `qa-moneyshot`/`pass1-badge`/`pass2-badge`/`qa-delta`/`strength-rule`.
- Bundle size (already warns) → prefer CSS/SVG primitives; lazy-load only if needed.
- Motion behind dense text forbidden → ambient bg only in low-opacity gutters/headers, never under report prose.
- 60fps + prefers-reduced-motion honored (existing reset covers animation/transition).

## Completion record (Slices 1–9 shipped)

| Slice | Commit | What |
|------|--------|------|
| 1 Visual system | `61fb031` | depth/glass utilities, `shine` keyframe, vendored NumberTicker/ShineBorder/DotPattern/SpotlightCard (reduced-motion-safe) |
| 2 App shell | `8573460` | glass top bar + faint static ambient dot-grid behind opaque panels |
| 3 Credibility hero | `494ce45` | +43% enlarged + ShineBorder (loop-confirmed only) + NumberTicker across KPI strip |
| 4 Report/citations | `bae1756` | elegant on-brand mirror citation chips, short ref + tooltip, click→drawer |
| 5 Evidence depth | `e959b03` | source cards wrapped in SpotlightCard (depth + hover spotlight) |
| 6 QA Replay | `253d651` | depth-card on Pass cards (locked money-shot preserved) |
| 7 Trace/Observability | `c9c0aa8` | depth-card on per-call inspection cards |
| 8 Schema/HITL | `a58c0a4` | depth-card on the comparison grid; HITL left honest/unchanged |

### Slice 9 — final judge rehearsal (Chrome DevTools, run `3775d21a`, 2026-06-07)
- 6/6 tabs render; **0 console errors** (1 pre-existing benign React Flow `nodeTypes` warn in 执行轨迹 only).
- All polled endpoints **200** (metrics/report/credibility/synthesis/withheld/trace/llm_calls/schemas); **no mock data**.
- Money-shot intact: Pass1 弱(1) → +4 来源 → Pass2 中(5), 升级幅度 1→5 来源 弱→中.
- Credibility hero: +43% ↑ + 真闭环确认 + ShineBorder; KPI strip animates to 4 条/80%/100%/0%/277s/强0·中4·弱0.
- Report citation chip → evidence drawer works; evidence cards have depth/spotlight.
- Full suite: **206 tests pass**, tsc -b + lint + build clean; tracked tree clean.

### Self-score vs rubric (frontend lens)
| Axis | Score | Note |
|------|-------|------|
| Trustworthy multi-agent (35%) | 9/10 | visible reject→revise→pass, +43% hero, citations→drawer, evidence depth, honest copy |
| Engineering completeness (25%) | 8.5/10 | 206 tests, 0 console errors, all 200, reduced-motion + 60fps |
| Business/product value (20%) | 8.5/10 | premium BI workbench: glass shell, depth cards, number tickers, restrained motion |
| Docs/code quality (10%) | 8.5/10 | plan + runbook + per-slice commits |
| Compliance/materials (10%) | 7/10 | Doubao/Ark pending (Tier-C credential escalation — NOT frontend) |

No frontend-related axis ≤8. The only sub-8 axis (compliance) is the external Doubao/Ark
credential dependency, which is an escalation item, not a reversible frontend gap.

## Dark-intelligence rebuild + materials (RB1–RB5) — shipped

| Slice | Commit | What |
|------|--------|------|
| RB0 | `36cecde` | `DESIGN.md` dark system spec |
| RB1 | `d9b3910` (+`6b8a49e`,`99f55f3`) | dark token foundation (inverted ink/mirror, lime, mono) + shell + contrast fixes |
| RB2 | `38e49ea` | credibility hero band — giant lime +43% + glow + coverage donut |
| RB3/RB4 | `97cea5a` | dark report/evidence/QA (via foundation) + dark DAG nodes + obs/schema |
| AA | `f3abf5a` | muted-text contrast lifted to AA (Codex review) |
| RB5 | (this) | 答辩 deck + cover poster (docs/presentation/) |

### RB5 — 答辩 materials
- `docs/presentation/deck.html` — 11-slide single-file dark 答辩 deck (keyboard ←/→, F fullscreen,
  progress bar, offline). Maps to all 5 scoring axes: 问题 → 4-agent DAG → 真闭环 +43% money-shot →
  可信度(verbatim-or-reject/溯源) → Schema → 可观测 → 产品/HITL → KPI → 合规/技术栈 → 收尾.
- `docs/presentation/cover.html` — dark hero cover/poster (logo, 可信闭环 headline, giant lime +43%,
  tech pills). For submission cover / video opening.
- Both verified rendering via file:// (title, money-shot slide, cover screenshotted).

### Final rehearsal (dark app, run 3775d21a)
6/6 tabs coherent dark; 0 console errors; canonical data intact (+43%/80%/277s); money-shot + all
testids preserved; **206 tests + tsc -b + lint + build green**; AA contrast confirmed (ink-400 ~5.4:1).

### Refreshed self-score (post dark rebuild + materials)
| Axis | Before → After | Note |
|------|----------------|------|
| 可信度 (35%) | 9 → 9 | unchanged substance; premium UI strengthens perception |
| 工程完整度 (25%) | 8.5 → 8.5 | dark data-viz polish; tests green |
| 产品体验 (20%) | 8.5 → **9.3** | premium dark BI workbench, giant +43% hero, donut, lit DAG |
| 文档/代码 (10%) | 8.5 → 8.5 | DESIGN.md + deck + cover added |
| 合规/材料/答辩 (10%) | 7 → **8** | 答辩 deck + cover shipped (video still a human record step; Doubao still pending key) |

Net: the frontend is no longer "太朴素" — it reads as a premium dark intelligence workbench, and the
答辩 materials directly lift the 20% + 10% axes. Remaining external blocker unchanged: Doubao/Ark key.

## Hard constraints (carried)
No mock data; no fake loop; no weakening QA/evidence/PII/robots/credibility; no backend changes unless necessary;
no flashy-over-trust; no push; tracked tree clean at end except documented artifacts.
