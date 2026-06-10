# MingJing — Evidence-Grounded Competitive-Analysis Multi-Agent Runtime

A live, self-correcting research system built on LangGraph. It searches the web,
has an independent QA agent reject weakly-supported claims, re-collects real
evidence, and upgrades the claim from **weak → strong** — every conclusion
clickable to its original source.

---

## Live demo & video

- **Live case-study workbench** (no install — runs in your browser):
  **https://crepusculariris.github.io/mingjing** — two real completed analyses
  (Notion × Linear, and a Notion run verified on Doubao-Seed-2.0-lite) replayed as
  read-only static snapshots: final report, evidence drawer, weak→strong QA replay,
  and the credibility panel.
- **Demo video** (~5m38s, 1080p): attached to the
  [v0.1.0 release](https://github.com/CrepuscularIRIS/mingjing/releases/tag/v0.1.0).
- **Run it yourself**: `docker compose up --build` (see below).

---

## What the 6-minute demo shows

**Minute 1 — judge picks competitors.** The frontend presents a supported set of
SaaS products. Pre-warm has already fired at demo start, so the first run begins
immediately without a network-cold hang.

**Minutes 2-3 — collection + DAG motion.** The activity feed scrolls in real
time: "Collector fetching g2.com…", "Analyst extracted pricing claim",
"QA reviewing claims." The LangGraph loop is visibly alive on a 2-second poll;
no dead air.

**Minutes 3-4 — the weak → strong loop (the core moment).** Round 1 produces a
`user_sentiment` claim backed by a single source. QA runs its deterministic
check families (7 → 6 IssueCodes): the snippet-match gate and the source-count gate both flag it. QA emits a
`WEAK_EVIDENCE` issue and a concrete RevisionTask. The route function sends the
task back to the Collector. Round 2 performs a **real additional fetch** — not
data that was withheld — from a second independent domain. QA re-runs. Two
distinct supporting sources from an authoritative type: the transparent rule
fires, the tier upgrades to **strong**. The badge animates weak → strong on
screen. The rule is printed next to the badge in plain English.

**Minute 5 — business insight.** The Final Report leads with an LLM-synthesised
BLUF brief (竞争态势/机会/风险) over the deterministic claim ledger, with a KPI
bar showing measured machine time against an industry human-baseline estimate.
Every claim in the report is clickable to an EvidenceDrawer that scrolls to and
highlights the exact cited sentence.

**Minute 6 — close.** Fallback: if all live calls fail, `MINGJING_MODE=cache_first`
auto-downgrades and the demo completes on the pre-recorded cache.

---

## Run with Docker (one command)

The full stack — backend (FastAPI) + frontend (nginx) + SearXNG — boots with **no
API key** in deterministic `cache_first` mode:

```bash
docker compose up --build
# then open http://localhost:5173   (API on http://localhost:8000)
```

For live web + LLM analysis, copy `.env.example` → `.env`, set `MINIMAX_API_KEY`
(and a search key, or use the bundled SearXNG), then run with
`MINGJING_MODE=live_first docker compose up --build`. Native (non-Docker) setup is
in the **Quickstart** section below.

---

## Current status

| Layer | Status |
|---|---|
| Backend (config, DB, graph, 4 agents, QA, scoring, API) | Complete; 883 unit tests passing offline |
| Frontend (Final Report, QA Replay, Activity Feed, Observability) | Complete; 314 tests (31 files) green; wired to backend |
| Live run (stress-test model) | Requires `MINIMAX_API_KEY` in `.env`; D0 spike confirmed the key works |
| Live demo rehearsal / wall-clock confirmation | Pending human |
| Fallback video | Pending recording |
| Doubao/Ark | **Full run verified 2026-06-10** (run `33835db0`: 18 llm_calls all on the contest EP; 1 admitted at strong, 4 withheld with codes). No key committed (full git object-store scan, 0 hits); historical shared credentials deactivated (401). Demo default remains the MiniMax stress test. |

---

## Quickstart

```bash
# 1. Install Python deps
uv sync

# 2. Copy and fill in the environment file
cp .env.example .env          # then add MINIMAX_API_KEY

# 3. Run offline tests (no key required)
make test

# 4. Start the backend API (port 8000)
make api

# 5. Start the frontend dev server (port 5173)
cd frontend && npm install    # first time only
make web                      # or: cd frontend && npm run dev
```

### Starting an analysis run

With both servers running, open `http://localhost:5173`. Either **(Directed Mode)**
select competitors and click **Analyze**, or **(Discovery Mode)** leave the
competitor field empty and provide just a *category* (+ market scope) to let the
system discover the products to analyze. The frontend polls
`GET /runs/{id}/trace?since=N` every 2 seconds and updates the activity feed in
real time.

Alternatively, start a run via the API directly:

```bash
# Directed Mode — you name the competitors:
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"category":"crm","competitors":["CompetitorA","CompetitorB"],"goal":"pricing and sentiment"}'
# returns {"run_id": "<hex>"}

# Discovery Mode — empty competitors + a category; a bounded pre-step discovers
# them (only selects WHICH competitors enter the loop — never feeds previews into
# evidence). Optional: market_scope, max_competitors, seed_competitors.
curl -X POST http://localhost:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"category":"团队协作 / 项目管理工具","goal":"pricing and sentiment","market_scope":"global","max_competitors":4}'
```

### Running the demo timing harness

```bash
make demo          # runs scripts/demo_timing.py (offline by default)
MINGJING_TIMING_LIVE=1 make demo-timing   # live path (requires key)
```

---

## Project layout

```
mingjing/
  pyproject.toml          # uv project, Python 3.12
  Makefile                # make test / api / web / demo
  src/mingjing/           # backend Python package
    config.py             # env-driven settings
    db/                   # SQLite WAL, append-only helpers (mixin package)
    schemas.py            # Pydantic v2 models + 5 field schemas
    graph.py              # LangGraph StateGraph wiring
    graph_nodes.py        # live node factories (close over GraphDeps)
    scoring.py            # transparent 3-tier scorer (PURE)
    qa/rules.py           # 7 deterministic QA check families → 6 IssueCodes (PURE)
    qa/route.py           # route() pure function (PURE)
    agents/               # 4 agents: collector, analyst, qa, writer
    collector/            # fetch/robots/search/independence/cache
    llm.py                # MiniMax client + JSON parse/repair
    trace.py              # log_event / log_llm
    trace_events.py       # typed trace-event emit helpers
    api.py                # FastAPI read-only views
    prewarm.py            # demo-start pre-warm
    ingest.py             # PII-anonymizing survey/interview ingest
    vendor/ldr/
      ATTRIBUTION.md      # D0 spike decision record (LDR not vendored)
  tests/                  # 883 unit tests
  frontend/               # React + Vite + TS + Tailwind
    src/views/            # FinalReport, QAReplay, Observability
    src/components/       # Badge, ClaimRow, EvidenceDrawer, …
  data/cache/             # read-only demo cache store
  scripts/demo_timing.py  # wall-clock timing harness
  docs/                   # this file + architecture, agent-protocol, deployment, roadmap
```

---

## How it was built / AI-assisted development

MingJing was built with AI-assisted tooling throughout. For a factual account of
the development method, AI collaboration evidence, and what is independently
verifiable from this repo (git history, Superpowers plan docs, QA gate
screenshots, Codex review-gate config), see
[docs/AI-ASSISTED-DEV.md](docs/AI-ASSISTED-DEV.md).

---

## Tech stack

- **Backend:** Python 3.12, uv, FastAPI, LangGraph, Pydantic v2, stdlib `sqlite3` (WAL)
- **LLM:** MiniMax-M2.7 via OpenAI SDK at `https://api.minimaxi.com/v1` — deliberately
  run as a *high-hallucination stress test* for the deterministic QA gate. The gate is
  provider-agnostic and **verified on Doubao-Seed-2.0-lite** (full run `33835db0`,
  2026-06-10 — same strict gate behavior under the official contest model).
- **Frontend:** React + Vite + TypeScript + Tailwind + reactflow + recharts (zero-CDN)
- **Search:** duckduckgo-search (keyless)
- **DB:** single-file SQLite (WAL + busy_timeout), append-only by `run_id/round/claim_id`

---

## See also

- `docs/architecture.md` — loop diagram, agent responsibilities, trust mechanics
- `docs/agent-protocol.md` — typed message contracts, RunState, trace vocabulary
- `docs/deployment.md` — env vars, live vs cache mode, SSRF/robots posture
- `docs/ROADMAP.md` — deferred items and honest pending-human tasks
- `docs/judge-qa.md` — prepared answers to judge questions

---

## License

Released under the [MIT License](LICENSE) © 2026 CrepuscularIRIS (MingJing).
