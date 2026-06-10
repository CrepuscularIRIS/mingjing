# Agent Protocol — Typed Message Contracts

## Overview

The 4 agents communicate through typed Python dicts threaded via `RunState`.
No agent reaches into another agent's internal state. The orchestration nodes
(`intake`, `plan`, `route`, `revise`) are excluded from this contract —
they are not agents.

---

## RunState (the shared graph state)

Defined in `graph.py` as a `TypedDict`. List fields use LangGraph additive
reducers (append-only); scalar fields are last-write-wins.

```
RunState:
  run_id:          str                   # stable run identifier
  intake:          dict                  # raw request (competitors, fields, goal)
  tasks:           list[dict]            # research tasks (append-only)
  sources:         list[dict]            # collected source dicts (append-only)
  claims:          list[dict]            # claim dicts, versioned (append-only)
  qc_reports:      list[dict]            # QC result dicts (append-only)
  revision_round:  int                   # current round (0 = first pass)
  phase:           str                   # last node name (tracing)
  budget_calls:    int                   # cumulative LLM + fetch calls
  budget_max:      int                   # from MINGJING_BUDGET_CALLS (default 40)
  db:              Any                   # Database carrier (not domain state)
  verdict:         str                   # "pass" | "reject" (set by qa node)
  assignee:        str                   # "collector" | "analyst" (set by qa node)
  budget_ok:       bool                  # recomputed at route node
  cap:             int                   # from MINGJING_REVISE_CAP (default 2)
  report:          str                   # final rendered report body
```

---

## Collector output — source dicts

Produced by `agents/collector.py:collect()`. Each element in the returned list:

```
{
  "url":          str,           # the fetched URL
  "title":        str,           # from search result
  "snippet":      str,           # from search result
  "fetched":      bool,          # False = robots-disallowed or fetch failed
  "reason":       str | absent,  # "skipped_robots" | "fetch_failed" when fetched=False
  "source_id":    str,           # UUID (present when fetched=True)
  "source_mode":  "LIVE"|"CACHED",
  "text":         str,           # extracted plain text
  "content_hash": str,           # sha256[:16] of text
  "fetched_at":   float,         # Unix timestamp
}
```

### Per-run depth parameter

`collect()` accepts a `source_cap` kwarg that governs how many sources are fetched
per task per round. In the live graph this is set to `1 + revision_round`: round 0
fetches 1 source (thin), round 1 fetches up to 2 (a genuine additional fetch, not
withheld data). The depth tier (`quick` or `detailed`, set by `MINGJING_DEPTH`)
controls the breadth of the search candidate pool (sub-query count, engines,
top_k), independently of the per-round source cap.

---

## Analyst output — claim payload

Produced by `agents/analyst.py:analyze_field()`. One call per `(competitor, field)`.
The LLM returns JSON (parsed defensively by `parse_json_with_repair`; no native tool/function-calling is used — see the function-calling note in docs/judge-qa.md):

```
{
  "statement":    str,           # the human-readable claim text
  "claim_type":   "fact" | "inference",
  "value":        object,        # structured value (field-schema-specific)
  "evidence_ref": [source_id, ...]  # only ids from the supplied source set
}
```

`evidence_ref` is validated against the actual supplied source ids before
propagation; any hallucinated or empty id is dropped by `filter_evidence_refs`.

### Verbatim-evidence contract

Each cited evidence item produced by the analyst carries a **verbatim `snippet`**
— a short passage copied verbatim from the source's raw text. The QA
`HALLUCINATED_SNIPPET` rule enforces this contract: it asserts that every snippet
is a substring of its cited source's `raw_text` (after whitespace normalization).
Any snippet not found in the source text causes a `HALLUCINATED_SNIPPET` issue,
which routes the claim back to the analyst for correction. This is the primary
anti-fabrication gate for cited evidence.

---

## QA output — review result

Produced by `agents/qa.py:review()`, which wraps `qa/rules.qa_check()`:

```
{
  "verdict":        "pass" | "reject",
  "issues": [
    {
      "code":     IssueCode,     # see full list below
      "claim_id": str | None,
      "detail":   str
    }, ...
  ],
  "revision_tasks": [
    {
      "id":          str (UUID),
      "run_id":      str,
      "claim_id":    str | None,
      "assignee":    "collector" | "analyst",
      "issue_code":  str,
      "instruction": str,
      "status":      "open",
      "round":       int
    }, ...
  ]
}
```

### QA IssueCodes (complete list from `qa/rules.py` + `schemas.py`)

Six deterministic checks; each emits one code:

| Issue code | Check | Assignee |
|---|---|---|
| `SCHEMA_GAP` | A claim omits a `required` sub-field for its field schema, OR an inference `based_on` references a non-existent claim id | collector |
| `WEAK_EVIDENCE` | `scoring.strength()` scores the claim `"weak"` from its evidence metadata | collector |
| `HALLUCINATED_SNIPPET` | An evidence snippet is NOT a verbatim substring of its cited source's `raw_text` | analyst |
| `CONTRADICTION` | Two claims on the same `(competitor, field)` carry conflicting values; OR a single claim's evidence has both a `supports` and a `refutes` stance from distinct domains | collector |
| `LOW_COVERAGE` | Fraction of required fields covered is below 0.8 threshold | collector |
| `VALUE_UNSUPPORTED` | A substantial string leaf under a **required** sub-field of `claim.value` is not found in any cited source's `raw_text`; also checks numeric magnitudes under required sub-fields (exact token match) | collector |

Note: `INFERENCE_LINEAGE` is the logical name for the `based_on` integrity check,
but the code emits `SCHEMA_GAP` with `meta.reason="inference_lineage_unknown"` for
routing purposes (so the existing collector-routing applies without a new route
branch).

The verdict is computed **purely from structured metadata** — no freeform LLM
judgment. This means an injected instruction in fetched web text cannot flip the
tier or suppress a contradiction.

---

## Writer output — Report

Produced by `agents/writer.py:render_report()`. Pure and deterministic; no LLM.

```
Report:
  body:            str              # templated lines, one per surviving claim
  referenced_ids:  list[str]        # exactly the QA-passed ids that were referenced
```

**Projection invariant:** every `id` in `referenced_ids` is guaranteed to be in
the passed-claims set. Any `claim_id` not in that set is dropped. The report
cannot cite an unbacked claim. Unit-tested in `tests/test_writer_projection.py`.

**Claim lifecycle: `draft` -> `pass`.** Every claim is persisted `status="draft"`
by `claim_builder.build_claim`. The terminal write node promotes each QA-accepted
(passed) claim to `status="pass"` by appending a superseding version (append-only,
never UPDATE — see `claim_builder.supersede_target`). Flagged/rejected claims on
the partial path stay `draft`. The report API (`/runs/{id}/report`) surfaces only
`status="pass"` claims, so the promotion is what makes the Final Report non-empty.

---

## Trace event vocabulary

Events are emitted by `trace_events.py` into the `trace_events` table.
`GET /runs/{id}/trace?since=N` returns them as a paginated stream that the
frontend polls every 2 seconds.

| Event type | Emitting node | Key payload fields |
|---|---|---|
| `node_enter` | every node | `node`, `agent` (optional) |
| `discovery_started` | discover (runner pre-step, Discovery Mode) | `category`, `market_scope` |
| `competitors_discovered` | discover (runner pre-step) | `selected`, `candidates`, `queries` |
| `discovery_empty` | discover (runner pre-step) | `selected` (empty), `candidates`, `queries` |
| `collect_start` | collect | `competitor`, `field`, `round` |
| `collect_done` | collect | `competitor`, `field`, `sources_added`, `round` |
| `analyze_start` | analyze | `competitor`, `field` |
| `analyze_done` | analyze | `competitor`, `field`, `claim_id`, `evidence_strength` |
| `qa_pass` | qa | `claim_ids`, `round` |
| `qa_fail` | qa | `claim_id`, `reason`, `code`, `round` — one event per issue |
| `revise_start` | revise | `assignee`, `round`, `claim_id` |
| `revise_done` | qa (round > 0 path) | `round` |
| `run_complete` | write | `claims_total`, `strong`, `moderate`, `weak` |
| `run_partial` | write | same as `run_complete` — emitted when cap or budget hit |
| `claim_skipped` | write | `claim_id` — claim dropped (not in QA-passed set) |
| `synthesis_start` | synthesis | emitted before the LLM synthesis calls begin |
| `synthesis_done` | synthesis | emitted after the synthesis payload is persisted |

The `claim_id` in `revise_start` identifies the first open QC report's claim so
the frontend can highlight which claim triggered the self-correction.

---

## LLM observability

Every `call_llm()` invocation appends a row to `llm_calls`:

```
{
  "id":                int,
  "run_id":            str,
  "agent":             str,           # collector / analyst / qa / writer
  "model":             str,           # e.g. "MiniMax-M2.7"
  "prompt_json":       str,           # JSON-encoded messages list (API key redacted)
  "output_text":       str,
  "prompt_tokens":     int | None,
  "completion_tokens": int | None,
  "total_tokens":      int | None,
  "created_at":        str            # ISO timestamp
}
```

Any value of `MINIMAX_API_KEY` is redacted from `prompt_json` at write time.
`GET /runs/{id}/llm_calls` returns all rows for a run, enabling full prompt /
output / token inspection — the scored 25% observability requirement.
