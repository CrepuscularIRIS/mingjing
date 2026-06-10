# MingJing Kickoff Audit — 2026-06-06

Source of truth: `docs/POLISH-PLAN-2026-06-06.md` · branch `feature/mingjing-w1-core` · submit 6/10 (~4 days) · 答辩 6/12–6/19.

## Phase 0 — Compliance Gate (G1 Doubao switch)

**BLOCKED.** No Doubao / Volcengine Ark credential exists in `.env`. The only LLM key is a MiniMax `sk-cp-...` key; `config.py` resolves `base_url=https://api.minimaxi.com/v1`, `model=MiniMax-M2.7`, so the runtime currently calls **MiniMax, not the mandated Doubao-Seed-2.0-lite**. The `.env` header comment falsely claims "Doubao via Ark" — trust values, not comments.

The good news: clients are OpenAI-SDK / OpenAI-compatible, so Ark is a **config-only switch** — no change at the `OpenAI()` call sites (`llm.py:371`, `graph.py:186`). Clearing it:

1. **G17 (owner=User):** obtain a rotated Ark key + EP id (`ep-20260514111325-xjmj7`) from organizers (the shared key leaked in source).
2. Set in `/home/lingxufeng/Langgraph/mingjing/.env`: `MINGJING_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`, `MINIMAX_API_KEY=<ark key>`, `MINIMAX_MODEL=<doubao-seed EP id>`; mirror in `.env.example`.
3. **Rename for judges + fix redaction:** vars stay `minimax_*` even when pointed at Ark — rename to provider-neutral / add `DOUBAO_*` aliases, and update `trace.py:20-21` redaction so the Ark key is scrubbed under its new name (else it leaks into the observability view).
4. **Verify:** POST `/runs` completes and real Doubao tokens appear in the trace (seen in Slice 8 Observability).

Gate: a live run completes on Doubao with real tokens logged.

## Hard Blockers

| ID | Type | Blocker | Next action |
|----|------|---------|-------------|
| G1 | Compliance 🔴 | Runtime calls MiniMax, not Doubao | Config switch above; gated on G17 |
| G17 | Compliance 🔴 | Leaked shared key | User rotates with organizers |
| G2 | Demo 🔴 (User) | 6-min 录屏 not recorded | Record in Phase 4 after Slices 1–6 green |
| G3 | Demo 🔴 | Closed-loop stays dark | Seed a run with ≥1 reject→revise so `repair_delta>0` |
| — | Tech | `minimax_*` naming debt + trace redaction gap | Fold into G1 rename |
| — | Tech | `TraceEvent.created_at` / `SourceProvenance.fetched_at` typed `string`, backend is REAL | Client-only type fix in Slices 5 / 3 |
| — | Tech (one-time) | shadcn/Magic UI/React Bits not vendored; no `cn()`, no `@/` alias, no Radix/motion | Bootstrap in Slice 1 |

Baseline is green before any change: `tsc -b` exit 0, 664 backend tests collect clean.

## Scoring Axes (by weight)

1. **35% — 多Agent协作与输出可信度** → 4 specialist agents on a visible LangGraph DAG (Slice 5), the REAL reject→revise loop with measurable `repair_delta` (Slices 4 + 6, G3), Schema conformance (Slice 7), one-click 溯源 (Slice 3). **The money axis — protect the honest weak→strong loop.**
2. **25% — 技术深度与工程完整度** → full data→orchestration→storage→API→frontend pipeline live on Doubao (G1), per-agent Prompt/IO/decision/Token observability (Slice 8), hallucination/robustness (forced citation, G5 snippet QA, G20 search).
3. **20% — 业务价值与产品体验** → KPIs as "verified claims gained" + human baseline 16–40h→X min + 准确率/覆盖率/人工修正率 (Slice 6, G6/G7) + HITL correction (Slice 10).
4. **10% — 代码质量与文档** → modular code, one-commit-per-slice, README+架构图+Agent协议+部署说明 (G15/G16), TRAE traces (G19).
5. **10% — 合规、材料与答辩** → robots/ToS + PII 脱敏 + 合规声明 (G18), 录屏 (G2), organized 答辩.

## Open GAPs → Slice Mapping

**Blocking:** G1→Phase 0 · G2→Phase 4 · G3→Slices 4+6.
**High:** G4→all slices · G5→backend P1 (surfaced Slice 4) · G6→Slice 6 · G7→Slices 6+10 · G8→backend P1.
**Normal:** G9→Slice 8 · G10→Slice 5 · G11→Slice 4 · G12→Slice 3 · G13→Slice 3 · G14→Slice 9 · G15/G16→Phase 3 docs · G17→Phase 0 · G18→Phase 3 · G19→Phase 3 · G20→backend P1.

## Slice Readiness (build order)

| # | Slice | Status | Endpoint / data |
|---|-------|--------|-----------------|
| 1 | App shell / IA | READY | `/runs`, `/schemas`, `/health` (ALIGNED). NEEDS one-time vendor bootstrap (cn/alias/shadcn/motion); preserve ink/mirror/strength tokens |
| 2 | Final Report | READY | `/runs/{id}/report` (ALIGNED) |
| 3 | Evidence & 溯源 | READY | `/sources/{id}` — fix `fetched_at: number\|null`; +G12 badge +G13 count |
| 4 | QA Replay delta | READY to build / BLOCKED-FOR-DEMO-BY G3 | `/claims/{cid}/history` (ALIGNED); G11 delta client-side |
| 5 | Execution Trace DAG | READY | `/runs/{id}/trace` — fix `created_at: number`; +G10 synthesis node |
| 6 | Credibility / KPI | READY to build / BLOCKED-FOR-DEMO-BY G3 | `/credibility` + `/metrics` (ALIGNED); G6/G7 reframe |
| 7 | Schema Matrix | READY | `/schemas`, `/schemas/{domain}`, `/report` (ALIGNED) |
| 8 | Observability | READY | `/runs/{id}/llm_calls` (ALIGNED); G9 mount; verifies G1 tokens. Confirm `Observability.tsx` not legacy first |
| 9 | 问卷/访谈 card | READY | `/survey-design` (ALIGNED, {} fallback); G14 label demo-data |
| 10 | Correction HITL | READY | POST `/claims/{cid}/correct` (ALIGNED); confirm reverse-channel re-feeds a run |

All 10 are buildable now (backend endpoints align); Slices 4 and 6 only need G3's seeded run to look green **on camera**, not to build.

## First Slice

**Build Slice 1 (App shell / IA) first.** Phase-0 compliance (G1) does **not** need to precede it — the shell wires to already-aligned real endpoints and Phase 0 (backend) is a parallel track. Slice 1 owns the one-time vendor bootstrap (cn() + clsx + tailwind-merge + `@/` alias + shadcn/Radix/tailwindcss-animate + motion, `tsc -b` clean) that unblocks every later slice's Magic UI / React Bits copy. G1 must be cleared before **Phase 4 demo capture**, not before Slice 1.

## How This Run Executes

- **Model:** Opus 4.8 throughout.
- **Per-slice loop:** (1) Plan — superpowers brainstorming + writing-plans, no code first → (2) Build — Vite + shadcn/ui + Magic UI / React Bits (ts-tailwind variant), wired to the **real API client, no mock data**, TDD + Vitest → (3) Self-QA live — gstack headless: navigate, screenshot, diff, console/network, responsive + design-review → (4) Verify — run the app, `tsc -b` clean, Vitest green, backend stays green via `make test` → (5) Acceptance — Codex stop-hook review (verify, don't blind-comply; fix until it passes) → (6) Commit — one Conventional Commit per slice.
- **Definition of done:** real data wired · §3a visual bar met · gstack screenshot attached · Vitest + `make test` green · Codex acceptance passed.
- **Guardrails:** no mock data on the demo path · never drop a hero experience · `tsc -b` (not `--noEmit`) · do NOT weaken backend QA/evidence/PII/credibility invariants (relax G5 QA only if it over-rejects) · honest weak→strong (source cap = 1 + revision_round; later rounds fetch genuinely new data) · motion only on state change/arrival, never idle · stay Vite SPA + shadcn (no DeerFlow copy) · demo capture last.
- **Tracks:** Backend (Phase 0–2) and Frontend (Slices 1–10) run in parallel; **Phase 4 (G3 seed run + G2 录屏) is gated on everything.**
- **Score-floor fallback if time runs short:** G1 → G3+G2 录屏 (the 35% closed-loop proof on camera) → Slices 2+3+4 (Report + Evidence + QA Replay) → G6 KPI reframe. Everything else additive.
