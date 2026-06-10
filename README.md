# MingJing 明镜 — an evidence-*admissible* competitive-analysis runtime

> **The LLM proposes, deterministic code adjudicates, evidence decides.**
> A self-correcting multi-agent system (built on LangGraph) that searches the web, lets an
> independent QA agent **reject** weakly-supported claims, **re-collects real evidence**, and
> upgrades a conclusion from **weak → strong** — and every conclusion in the report is
> clickable, in 30 seconds, to its original source span and the reason QA admitted it.

Its soul sentence: **"它知道自己什么时候不该自信"** — *it knows when it should not be confident.*

---

## Why it's different

A Deep-Research agent hands you a report you can only **choose to believe**. MingJing hands you
a **process you can audit**: every claim is graded, weak ones are bounced and re-collected, and
you can click to verify the verbatim citation. The well-known failure mode of research agents —
citation *links* are ~94% valid but citation *facts* are only 39–77% accurate — is closed here
by a hard rule: **a cited snippet must be a verbatim substring of its source, or the claim is
rejected and re-collected.** Nothing reaches the report on the model's say-so.

The full design philosophy and the theory behind it (verification-for-governance, Verifier's
Law, the Admiralty/Toulmin lineage, the honest fact/inference ceiling) is in **[AGENTS.md](AGENTS.md)**.

---

## Live demo & video

- **Live case-study workbench** (no install — runs in your browser, no login, no backend):
  **https://crepusculariris.github.io/mingjing** — two real completed analyses
  (Notion × Linear, and a Notion run verified on Doubao-Seed-2.0-lite) replayed as read-only
  static snapshots: final report, evidence drawer, weak→strong QA replay, credibility panel.
- **Demo video** (~5m38s, 1080p): attached to the
  [v0.1.0 release](https://github.com/CrepuscularIRIS/mingjing/releases/tag/v0.1.0).
- **Run it yourself**: `docker compose up --build` (below).

---

## The money-shot: a real weak→strong loop

On the flagship run `4fff4227` (Notion × Linear, Chinese), watch a claim repair itself **on
screen** — twice, in one run:

1. **Round 1** produces a `user_sentiment` claim backed by a single weak source. The QA agent —
   which sees *only the evidence text, never the analyst's reasoning* — scores it **weak** and
   emits a `WEAK_EVIDENCE` issue + a concrete `RevisionTask`.
2. The router sends the task **back to the Collector**, which performs a **real additional
   fetch** (source cap = `1 + revision_round`, so this is genuinely new data, not data held
   back for show). Sources animate **2 → 4**.
3. QA re-runs. With two more independent sources, the transparent tier rule fires: the tier
   upgrades **weak → moderate**. In the *same* run, Linear pricing goes further: **moderate →
   strong** (2 → 4 sources).
4. The credibility panel shows **`repair_delta +42%`** and lights the *real-closed-loop /
   tier-upgrade* seal — a deterministic QA/scoring output, **not** model self-grading. The
   admission funnel reads **10 proposed → 6 admitted · 4 withheld** (the 4 withheld are kept
   with their issue codes, never deleted).

Reverse-honesty invariant: if **0** claims are admitted, the seal and the speedup UI
**extinguish**. The system refuses to look good when it isn't.

---

## Run with Docker (one command)

The full stack — backend (FastAPI) + frontend (nginx) + SearXNG — boots with **no API key** in
deterministic `cache_first` mode:

```bash
docker compose up --build
# then open http://localhost:5173   (API on http://localhost:8000)
```

For live web + LLM analysis, copy `.env.example` → `.env`, set `MINIMAX_API_KEY` (and a search
key, or use the bundled SearXNG), then run with
`MINGJING_MODE=live_first docker compose up --build`.

### Native (no Docker)

```bash
uv sync              # Python 3.12 deps
make test            # 883 backend tests — NO API key required (DI fakes)
make api             # FastAPI on :8000
make web             # Vite frontend on :5173
```

Offline tests need **no** API key. Full setup, Directed vs Discovery Mode, and the demo timing
harness: [docs/deployment.md](docs/deployment.md).

---

## How it works (60-second tour)

```
(discover) → intake → plan → collect → analyze → qa → route ─┬→ write → synthesis → END
                        ↑                                     │
                        └──────── revise (collect | analyze) ─┘
```

Four **scored** agents do the work; orchestration nodes are kept separate:

| Agent | Role |
|-------|------|
| **Collector** | web search → robots check → SSRF-guarded fetch → evidence chunks |
| **Analyst** | one LLM call per field; untrusted web text quarantined in an `<UNTRUSTED>` envelope |
| **QA** | 7 deterministic checks → 6 IssueCodes, **no LLM** (so prompt-injection can't flip a verdict) |
| **Writer** | pure projection — templates *only* QA-passed claims; an unbacked claim can never reach the report |

Evidence strength is a transparent **3-tier** rating (strong / moderate / weak) with **no
confidence decimals** — distinct registrable domains + authoritative source types + a
contradiction flag. Simulated survey data is badged and **excluded from all credibility math**.
Claims are **append-only** (versioned, never updated), so the full history — including human
corrections — is preserved and auditable. Deep dive: **[AGENTS.md](AGENTS.md)**.

---

## Verified status (reproducible locally)

| Gate | Result | Command |
|---|---|---|
| Backend tests | **883 passed**, exit 0 | `make test` |
| Frontend tests | **314 passed** across 31 files, 0 `act()` warnings | `cd frontend && npx vitest run` |
| Frontend typecheck | `npx tsc -b` exit 0 (use `-b`, not `--noEmit`) | `cd frontend && npx tsc -b` |
| Production build | exit 0 | `make web-build` |
| File-size rule | no source file > 800 lines | — |

Canonical runs: **`4fff4227`** (Notion × Linear, +42% repair, 强1·中5, coverage 80%) ·
**`33835db0`** (Notion on Doubao-Seed-2.0-lite, 18 `llm_calls` all on the official endpoint) ·
**`3775d21a`** (single-competitor depth, +38%).

---

## Tech stack

- **Backend:** Python 3.12, uv, FastAPI, LangGraph (StateGraph), Pydantic v2, stdlib `sqlite3`
  (WAL + single-writer lock), OpenAI-compatible LLM client.
- **LLM:** MiniMax-M2.7 — run deliberately as a *high-hallucination stress test* for the
  provider-agnostic gate; the gate is **verified on Doubao-Seed-2.0-lite** (full run
  `33835db0`). Config-level switch; no RAG / vector DB by design.
- **Frontend:** React 19 + Vite + TypeScript + Tailwind + shadcn/ui + reactflow + recharts
  (zero CDN).
- **Search:** keyless/trusted providers + self-hosted SearXNG (`deploy/searxng/`).
- **Video:** standalone Remotion project in [`mingjing-video/`](mingjing-video/) (renders the
  v0.1.0 demo video).

---

## Honest boundaries

We say these plainly, because honesty *is* the product:

- Metrics (`repair_delta` / `strong_rate` / `coverage`) are **evidence-strength proxies, not
  factual accuracy** — "traceable & verifiable," never "true about the world."
- The online demo is a **read-only** static replay; new analyses / human corrections need the
  local `docker compose up`.
- Run-level concurrency scheduler, dynamic schema evolution, voting/self-eval, and a real
  LangSmith deep-link are **deferred — not claimed as built** ([docs/ROADMAP.md](docs/ROADMAP.md)).

---

## Repo layout

```
src/mingjing/         # backend: graph, agents, qa, scoring, api, collector, domains
frontend/             # React 19 + Vite workbench
mingjing-video/       # standalone Remotion demo-video project
docs/                 # architecture, agent-protocol, deployment, compliance, defense, runbook
deploy/searxng/       # self-hosted keyless search (docker compose)
AGENTS.md             # ← the full design & theory reference
```

## See also

- **[AGENTS.md](AGENTS.md)** — full design & theory (the *why*)
- [docs/architecture.md](docs/architecture.md) — loop diagram, agents, trust mechanics
- [docs/agent-protocol.md](docs/agent-protocol.md) — typed contracts, RunState, trace vocabulary
- [docs/COMPLIANCE.md](docs/COMPLIANCE.md) — robots / SSRF / PII posture, honest gaps
- [docs/DEFENSE-NARRATIVE.md](docs/DEFENSE-NARRATIVE.md) — the defense main line
- [docs/SELF-AUDIT.md](docs/SELF-AUDIT.md) — gap-by-gap self-score

---

## License

Released under the [MIT License](LICENSE) © 2026 CrepuscularIRIS (MingJing).
