# Roadmap and Known Deferred Items

This file tracks what is honestly not yet done. Items are grouped by who
needs to act.

---

## Task 0: Committed Doubao key — repo-side DONE, account-side EXTERNAL

The key `ark-REDACTED...` from the ByteDance contest shared account was committed
in `【CIS】AI 全栈项目挑战赛开题材料.md` (line 49), present in git history at the
blob reachable from commits `2c5fa63` and `9c5e3d9`.

### Repo-side cleanup — ✅ DONE (2026-05-30)

Completed locally; secret-scrubbed history pushed to the GitHub remote (origin — https://github.com/20bytes/mingjing-evidence-runtime.git); old key prefixes purged from the working tree.
1. Created an immutable, restorable backup of all pre-scrub refs:
   `~/mingjing-pre-secret-scrub-31523f1.bundle` (`git bundle verify` → complete history).
2. Added `.env.example` placeholders (`mingjing/.env.example`); all secrets read from env.
3. Added `.gitignore` patterns so the contest source doc and any populated `.env`
   can never be committed (`【CIS】*.md`, `*开题材料*.md`, `.env.*` with `!.env.example`).
4. Redacted the live key in the untracked working-copy doc → placeholder.
5. Scrubbed the doc (and thus the key) from **all** history:
   `git filter-repo --invert-paths --path '【CIS】AI 全栈项目挑战赛开题材料.md' --force`.
6. Verified purge (all returned clean):
   - `git grep -I -l "<full key>" $(git rev-list --all)` → no matches.
   - `git log --all -S 'ark-REDACTED' --oneline` → empty.
   - `git log --all -- '<doc>'` → empty (doc gone from history).
   - Raw blob scan over `git cat-file --batch-all-objects` → no match.

If the original key text is ever needed, restore from the bundle:
`git clone ~/mingjing-pre-secret-scrub-31523f1.bundle <dir>`.

### Account-side rotation — 🔴 #1 HUMAN ACTION, DO NOW (only real fix; repo work is just damage control)

Purging git history and `.gitignore`-ing the doc are **damage control, not the fix**.
The single real remediation is rotating the credential with the organizers. This is
the highest-priority human action on the project and must not keep sitting here.

**Exact steps (owner: the team, via the contest 群 / organizers):**
1. Message the organizers (飞书 群) requesting rotation/revocation of the shared
   Doubao/Ark key for this 课题's shared account.
2. Confirm in writing the old key is invalidated.
3. When the new key is issued, put it ONLY in a gitignored `.env` (never a doc).

Notes:
- The contest material `Competition.md` (this repo root) ALSO contains a live
  shared key (a *different* one from the originally-scrubbed key). It is now
  gitignored (`Competition.md` / `*Competition*.md` in `.gitignore`, commit
  `ed6225c`) and was verified absent from pushed history — but it is a real live
  credential and the same rotation request covers it.
- The MiniMax→Doubao switch is config-driven (env only, no code change) and was
  **verified 2026-06-10**: full run `33835db0` on the contest EP with a
  fresh private-channel key (in-process env only, never on disk). The demo
  default remains MiniMax as the deliberate high-hallucination stress test;
  the old leaked credentials are deactivated (401, COMPLIANCE §七).

---

## ✅ Shipped (previously deferred, now done)

- **Deep-collect pipeline + depth tiers**: `quick` / `detailed` tiers; LLM query
  expansion; parallel Tavily / Brave / DuckDuckGo / SearXNG search; quality-biased
  dedupe (authority + independence + anti-spam); two-phase fetch with Firecrawl
  JS-render fallback; thin-source gate (< 100 chars dropped).
- **Verbatim-evidence analyst prompt + `HALLUCINATED_SNIPPET` grounding check**:
  analyst emits verbatim snippets; QA gates every snippet against source `raw_text`.
- **`VALUE_UNSUPPORTED` QA rule**: value-level anti-fabrication for required
  sub-fields (string and numeric leaf grounding against cited source text).
- **Inference lineage integrity (`SCHEMA_GAP` with `inference_lineage_unknown`
  meta)**: `based_on` ids validated against the live claimset.
- **LLM client finite timeout** (`llm_timeout_s`, default 90 s): no infinite
  hangs on stuck provider; raises `APITimeoutError` instead.
- **SQLite `_WRITE_LOCK` read serialization**: all reads and writes on the shared
  connection go through `threading.Lock`; WAL + `busy_timeout=5000` covers the
  FastAPI polling path.
- **Synthesis DAG node** (`write → synthesis → END`): post-write LLM brief;
  emits `synthesis_start`/`synthesis_done`; NON-FATAL fallback to deterministic
  ledger; persists to `syntheses` table.
- **Withheld/empty-state disclosure**: on a fully-rejected partial run, synthesis
  persists a `{"withheld": [...]}` payload enumerating draft claims + their
  final-round issue codes.
- **QA-Replay stability fixes**: `run-scope seeded source ids` — per-run stable
  ids prevent `PRIMARY KEY` collisions on re-collect; `scrub_open_text` trigger
  docstring + one-source-per-claim domain invariant documented.
- **Survey evidence lane** wired: survey/interview answers enter as `source_type=survey`
  rows grounded by the same QA gate (feature/mingjing-w1-core, pending merge review).

---

## Pending human action (non-blocking for offline testing)

### Live demo rehearsal and wall-clock confirmation

The offline test suite (~648 backend + ~198 frontend tests) confirms correctness. The 6-minute wall-clock
with live MiniMax calls, the rate limiter active, and the pre-warm storm has
**not yet been measured on the actual demo machine**. Required before submission:

- Run `make demo-timing` with `MINGJING_TIMING_LIVE=1` and `MINIMAX_API_KEY` set.
- Confirm end-to-end wall-clock ≤ 6 minutes.
- If over budget, reduce `MINGJING_SOURCE_CAP` or widen the cache and re-measure.
- Test the all-live-fails path: `MINGJING_MODE=cache_first` — confirm the demo
  completes cleanly.
- External display legibility check at 1920×1080: body ≥ 18px, claims ≥ 24px.

### Fallback demo video

A pre-recorded fallback video must exist before the final demo rehearsal.
**Not yet recorded.** Steps:
1. Do one clean offline run (cache_first, no key needed).
2. Record the full 6-minute demo narrative against the cached data.
3. Keep the video accessible on the demo machine before the live event.

### Real survey / interview data (currently synthetic only)

The `ingest.py` module supports real survey/interview sources (`source_type=survey
| interview`). The plan called for N≈30 real survey responses and 2 interviews
collected in parallel from D0. **Not yet collected.** Demoted to "if-collected":
the demo vertical slice does not gate on this. Survey-as-Source adds
authoritative evidence weight (`source_type=survey` counts as authoritative in
`scoring.py`) but the demo is complete without it.

---

## Technical debt / known limitations

### SQLite global lock = serialized, not truly concurrent

`_WRITE_LOCK` in `db.py` is a single `threading.Lock` over the shared connection.
All reads and writes are serialized through it. Per-thread independent connections
(which would allow true concurrent reads under WAL) are deferred. This is
sufficient for the single-process demo, but not a concurrent multi-user setup.

### Deep-collect live-verification pending

The deep-collect pipeline (query expansion, multi-engine search, Firecrawl
fallback, dedupe scoring) is wired and unit-tested offline, but end-to-end
live verification against the actual MiniMax + Tavily + Firecrawl services on
the demo machine has not yet been run. Required before demo day.

### Value sub-fields: optional leaves only soft-pruned (not hard-gated)

`VALUE_UNSUPPORTED` hard-gates **required** sub-fields. Optional sub-field leaves
(e.g. `negatives`, `pain_points`) are soft-pruned by `prune_unsupported_optional_leaves`
(ungrounded leaves are dropped from the output, not rejected). A claim with
fabricated optional content is not rejected; it just has those leaves removed.
Post-demo hardening could extend the hard gate to high-confidence optional fields.

### DNS-rebinding TOCTOU in SSRF guard

The `is_safe_url` guard resolves the hostname at check time; `requests` resolves
it again at connect time. A fast DNS-rebinding attack could route the second
resolution to a private IP, bypassing the guard. Accepted for the demo because
fetch targets come from an allowlisted competitor/search set. IP-pinning (resolve
once, pass the IP to `requests`) is the fix for arbitrary-URL deployments.

### PII anonymization: free-text name tokens

`anonymize_respondent_meta` drops identity-named keys and redacts email/phone
patterns, but free-text name tokens inside answer content (e.g.
`{"feedback": "Jane Doe says..."}`) are not removed. NER-based name removal
would be required for complete anonymization of free-text fields.

### `node_enter` trace event

`node_trace()` emits a `node_enter` event at every node. The event vocabulary in
`trace_events.py` lists the richer lifecycle events (`collect_start/done`,
`analyze_start/done`, etc.), which are emitted from `graph_nodes.py`. The generic
`node_enter` is emitted for all nodes as a baseline, including orchestration
nodes.

---

## Scale and productionisation (out of scope for contest)

- Multi-user / auth
- SSE (currently 2s polling)
- Broad crawler resilience (JavaScript-rendered pages, CAPTCHAs)
- SqliteSaver LangGraph checkpoint ritual
- Distributed / multi-process runner
- CI/CD pipeline

> Note (feature/mingjing-w1-core): the frontend is no longer stubs. All 10 hero views
> shipped as a 6-tab ink/mirror BI workbench — 分析报告 / Schema 矩阵 / 证据&溯源 /
> QA 回放 / 执行轨迹 / 可观测 — on shadcn/ui primitives (recharts token chart, Bocha
> CN search engine, synthesis node). Shipped GAPs: G5, G6, G7, G9, G10, G11, G12, G13,
> G14, G20, and Phase 0 Doubao/Ark switch (G1/G17 — verified run `33835db0`, 2026-06-10). Pending: the
> 6-min demo recording. See docs/COMPLIANCE.md + docs/AI-ASSISTED-DEV.md.

---

## Evolution path — DELIBERATELY NOT BUILT for this contest (verbal in 答辩 only)

Decided 2026-05-31 (see memory `mingjing-scope-discipline`). These are real, good ideas
that the organizer transcript and the scoring table together rule OUT for this competition.
The right move is to *speak* them as an evolution path in 答辩 (前瞻性 scores nearly the same
spoken as built, at far less risk), and build them in the post-competition AgentSwarm project.

- **Runtime-dynamic DAG topology** — NOT built, any degree. The scoring table wants "动态
  Schema" (delivered via the config-driven schema registry), NOT a dynamic DAG. A graph that
  changes shape at runtime would break much of the 314-test suite, confuse judges (hurting the
  "DAG 可视化可追溯" sub-point), and has zero scoring slot. Verbal evolution-path only.
- **True concurrency / worker pool / dynamic scheduling** — NOT built. Organizer: "并发非强制,
  nice to have". Real场景 is single analysis on one rate-limited shared account → concurrency
  hits throttle, adds race/partial-failure risk, gives no 6-min-demo visual gain. Pure threat
  to the 25% stability axis. IF a concurrency bullet is wanted, the contest scope ceiling is a
  *lightweight demo* (2 parallel runs = 2 LangGraph instances + 2 frontend panels), and only
  AFTER every acceptance-gate item is green — never worker pools / dynamic scheduling.
- **LLM-adaptive runtime field proposal** — NOT built. Dynamic schema is config-driven
  registration only (swap a domain YAML). An agent proposing new schema fields at runtime is
  unpredictable and untestable for a live demo.
