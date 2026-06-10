# MingJing DESIGN.md — Dark Intelligence System (rebuild 2026-06-07)

Single source of truth for the award-level frontend rebuild. Direction chosen with the
user: **Bloomberg / Palantir dark-intelligence workbench** — a serious, trustworthy
competitive-intelligence terminal, NOT a flashy toy. Premium = restraint + craft +
data-viz quality + one confident accent, not effects.

References: Bloomberg Terminal, Palantir Foundry/Gotham, Linear (dark), Vercel dashboards.

## 0. Why (maps to the official 评分 rubric)
- **20% 业务价值与产品体验** ← the primary target: report/溯源/HITL/回放 must feel premium.
- **35% 可信度** ← a confident dark intelligence UI *reads* as more trustworthy; DAG/溯源/QA-replay visuals are graded.
- **10% 材料/答辩** ← the demo video will be a recording of this UI (pending recording); deck + cover ship here.
Visual work does NOT fix the Doubao/Ark model-compliance gap (separate, needs the key).

## 1. Color system (dark)

### Canvas / neutrals — INVERT the existing `ink` scale in place
The app already uses `ink-50`=lightest-surface … `ink-900`=text **consistently**. Inverting
the scale's hex values flips the whole app to dark coherently with near-zero component
edits. New cool-slate `ink` scale (tailwind.config.js):
```
ink-50:  #0a0e10   /* app canvas (near-black slate) — was lightest */
ink-100: #11171a   /* raised surface */
ink-200: #1b2329   /* card border / hairline */
ink-300: #2a343b   /* stronger divider */
ink-400: #6f7e85   /* muted text (mid) */
ink-500: #8b9aa1   /* secondary-muted */
ink-600: #a7b4ba   /* secondary text */
ink-700: #c5cfd4   /* body text */
ink-800: #dfe6e9   /* strong text */
ink-900: #f1f5f6   /* primary text / headlines (near-white) — was darkest */
```

### Semantic shadcn vars (index.css `:root`) → dark
```
--background: 10 14 16      /* ink-50 canvas */
--foreground: 241 245 246   /* ink-900 */
--card: 17 23 26            /* raised slate (ink-100-ish) */
--card-foreground: 241 245 246
--popover: 17 23 26
--border: 27 35 41          /* ink-200 */
--input: 27 35 41
--muted: 27 35 41
--muted-foreground: 139 154 161  /* ink-500 */
--primary: 68 154 150       /* mirror-400 teal — brighter on dark */
--primary-foreground: 6 12 12
--accent: 20 40 40          /* deep teal tint */
--accent-foreground: 113 187 182
--ring: 68 154 150
--radius: 0.625rem
```

### Accents
- **Primary = mirror teal** (brand). On dark use mirror-400 `#449a96` / mirror-300 `#71bbb6` for text/links so it pops.
- **Data accent = LIME** (new) — reserved for the credibility hero (+38% repair_delta, 真闭环) and "improvement/gain" data. Add a `lime` token:
  ```
  lime: { 400:'#a3e635', 500:'#84cc16', 600:'#65a30d', glow:'rgb(132 204 22 / 0.45)' }
  ```
- **Strength palette retuned for dark** (higher luminance text, deep-tint bg, visible border):
  ```
  strong:   bg #11271b  text #5fd08a  border #2e9e5a
  moderate: bg #16182e  text #9aa0ee  border #6060b8
  weak:     bg #241f10  text #d9c06a  border #b89830
  ```
- LIVE = teal/lime dot; CACHED = slate; keep semantic, never red-for-weak.

## 2. Typography
- **UI/body:** Inter Variable (installed).
- **Editorial headlines / BLUF:** Source Serif 4 Variable (installed) — large display sizes for the report story.
- **Display numbers (NEW):** a monospace for KPI/metric numerals — add `@fontsource-variable/jetbrains-mono` (or IBM Plex Mono). `font-mono` → big tabular metric numbers (Bloomberg feel).
- **Scale (add display sizes):** metric-hero `text-5xl/6xl font-mono font-bold tabular-nums`; section head serif `text-2xl/3xl`; body `text-sm/base`; label `text-[11px] uppercase tracking-wide text-ink-500`.
- Rhythm: generous section spacing; cap report line-length (`max-w-prose`).

## 3. Depth / elevation (dark)
- Layering by **raised slate surface + hairline border + soft outer shadow + subtle inner top-highlight**, not white shadows.
- `depth-card` (index.css) → `background: #11171a; border:1px solid rgb(27 35 41); box-shadow: 0 1px 0 rgb(255 255 255/0.03) inset, 0 8px 30px -12px rgb(0 0 0/0.6)`.
- `glass-surface` (chrome) → `background: rgb(12 16 18 / 0.66); backdrop-blur(12px); border:1px solid rgb(27 35 41/0.7)`.
- Ambient: keep a faint dot-grid but in `text-ink-300` at low opacity over the near-black canvas (now actually visible).
- **Glow** reserved for the hero only: lime/teal box-shadow on the +38% / 真闭环 tile.

## 4. Motion (restrained, trustworthy)
- Motion ONLY on state-change / arrival / hover. No idle loops except the single hero shimmer (reduced-motion-disabled).
- NumberTicker count-up on KPIs (already test-safe). Tab arrival blur-fade. Hover: subtle lift + spotlight on data cards.
- Honor `prefers-reduced-motion` (existing global reset) + 60fps. Optional GSAP for the cinematic money-shot only.

## 5. Migration strategy (keeps app coherent + demo path green)
1. **Foundation slice:** invert `ink` scale + flip semantic vars + retune `depth-card`/`glass-surface` + add `lime` + mono font (tailwind.config.js + index.css only). ~90% of the app flips to dark automatically.
2. **Targeted fixes:** literal `bg-white`/`text-white` (6), hardcoded strength/amber hexes, any chart colors → dark tokens.
3. **Per-view drama:** add the premium layer on the now-dark base — giant mono hero number + lime glow, coverage donut, token/latency timeline, schema heatmap, dramatic DAG loop-back, BLUF display scale.
4. Every slice: keep all `data-testid`s + the locked money-shot; `tsc -b` + lint + 206 tests green; browser-verify on `3775d21a`; commit; Codex review.

## 6. Per-view intent
- **Hero band:** one dark band, GIANT mono `+38%` with lime glow + 真闭环确认, coverage donut, 已验证 N, 证据强度构成 强/中/弱 chips. The 10-second story.
- **Report:** BLUF in large serif on dark; editorial rhythm; mirror citation chips → evidence drawer.
- **Evidence:** dark source cards, teal spotlight, bright provenance badges + hash.
- **QA Replay:** dark cinematic Pass1 弱 → +N → Pass2 中/强; keep all testids.
- **Trace:** dark DAG, dramatic revise loop-back edge, per-node token/latency badges.
- **Observability:** token + latency timeline charts; redacted prompt/output panels.
- **Schema:** competitor × field **confidence heatmap** grid.

## 7. Guardrails (inviolable)
- Trust > flash: stays a serious intelligence workbench; no carnival/cursor-follower/particles.
- Never break the locked demo path or any `data-testid`; money-shot semantics unchanged.
- No mock data; honest copy (证据强度构成, no misleading 强证据率 0%).
- reduced-motion honored; 60fps on the demo machine; AA contrast on dark.
