# 问卷/访谈 Evidence Lane — Design Spec

**Date:** 2026-06-02
**Status:** Draft for review (brainstorming output → writing-plans next)
**Author:** brainstorming session

## Goal

Close the one 题目-named requirement still dormant: the collector "含问卷设计 / 问卷调研 / 用户访谈." `survey.design_survey`, `survey.scrub_open_text`, `ingest.ingest_survey`, `ingest.ingest_interview`, `ingest.anonymize_respondent_meta` all exist and are tested, but **no run or API path ever reaches them.** This spec wires them into the main pipeline as a first-class **evidence lane**, plus a thin **questionnaire-design output card**, so a judge sees the collector actually design a survey AND ingest survey/interview evidence that flows through the same gate.

## Scope (decided in brainstorming)

- **Option 1 (evidence-lane wiring + visibility) + a thin slice of Option 2** (a lightweight survey-design output card). **NOT** the full Option-2 orchestration overhaul (no new graph node, no re-plan edge).
- Two artifacts with **different truth-status**, deliberately:
  - **Questionnaire (`design_survey`)** = a *plan* ("what we'd ask"). Deterministic, LLM-free. Produced for **every** run. Rendered as a card. **Not evidence.**
  - **Survey/interview *responses*** = *evidence*. Must be **real data we have** — a curated, **competitor-keyed fixture**. Ingested only on a run whose competitor matches the fixture. **Never synthesized for arbitrary competitors** (that would be fabricating evidence — the exact thing the Evidence-Admissible gate forbids).

## Non-goals (honesty boundary — state plainly in 答辩)

- **No live respondent recruitment / distribution / panel automation.** We design the questionnaire and ingest responses we already have; we do not "run a survey" against live users.
- **No synthesized responses.** A competitor with no fixture ingests **zero** survey/interview evidence (honest absence).
- **No LLM in the survey-design or ingest path** (deterministic; preserves the gate's injection-proofness).
- Multi-domain survey field-mapping is out of scope: the fixture + question→field map target the **default** domain (the demo competitor). `ai_agent`/`hr` runs get the design card but no fixture (noted, not hidden).

---

## Architecture & data flow (confirmed)

```
RUN (executor, before graph.invoke)
  ├─ design_survey(primary_competitor, goal)  → SurveyDesign artifact
  │     (8–10 questions, each tagged to a schema field; a PLAN, not evidence)
  │     persisted + emitted as a collector trace event ("survey_designed")
  └─ if a curated fixture exists for a run competitor → survey_seed(...):
        append_source ONE source per (competitor, field) it informs:
          source_type = survey | interview        (authoritative in scoring)
          raw_text    = PII-scrubbed answer / segment  ← the GROUNDABLE content
          url         = survey:SV-1/q3 | interview:IV-1/seg2   (locator/badge)
          source_mode = INGESTED
        SEED those {source_id, field, competitor} entries into the initial
        graph state:  graph.invoke({..., "sources": survey_entries})

COLLECT node (existing, per competitor×field)  — UNCHANGED
  └─ web evidence  (collect_fn → append_source) ADDS to the seeded survey
     sources (RunState.sources is an additive list)

ANALYZE → CLAIM
   state["sources"] for (competitor, field) now = web + seeded survey/interview;
   analyst reads each source's db.get_source(sid).raw_text and may cite the
   survey/interview source in evidence_ref (real analyst in the demo; a
   survey-aware fake analyze_fn in the deterministic test)
QA gate           (SAME SCHEMA_GAP / VALUE_UNSUPPORTED / snippet-substring /
                   contradiction checks; value must be grounded in the scrubbed
                   response text — survey/interview is just another source_type)
REPORT claim      → 问卷 / 访谈 provenance badge + clickable survey:SV-1/q3 locator
```

**Load-bearing property:** a survey-backed claim is admitted by the *identical* deterministic gate as a web-backed one — no special-case, no bypass. Primary research is first-class evidence, not a side panel.

---

## Components

### 1. Question → schema-field mapping (`survey.py`)
- Add a `field` key to each entry in `_QUESTION_TEMPLATE`, mapping the question to a **default-domain** schema field it informs (e.g. Q2–Q3 satisfaction → `user_sentiment`; Q6 feature-gap → `feature_tree`; Q7–Q8 switching/WTP → `pricing_model`; Q9 barriers → `user_persona`; Q4–Q5 NPS → `user_sentiment`). `design_survey` echoes `field` per question in its output (used by both the card and the collect-lane routing).
- This is the only change to `survey.py` proper; `design_survey` stays deterministic + LLM-free.

### 2. Curated fixture (`src/mingjing/fixtures/survey/` or a small module)
- A competitor-keyed fixture: `{competitor_name: {"survey": {survey_id, responses: [...]}, "interview": {interview_id, segments: [...]}}}`.
- **Each response/segment must carry, per informed field, a self-contained answer text** that can stand alone as a source `raw_text` — i.e. it must contain the concrete claim content (e.g. a pricing answer like "respondents report the Pro plan at $20/mo") so the analyst can extract a value AND QA can ground it (value ⊆ that text). Thin/structured-only answers won't ground a claim (see Component 3). Open-text carries realistic PII so `scrub_open_text` visibly does work.
- Ship one fixture for the demo competitor (the one the demo corpus already uses), with a few survey responses + one interview transcript covering 2–3 fields. Real-shaped, modest size.
- Lookup helper: `fixture_for(competitor) -> dict | None` (exact/normalized competitor-name match).

### 3. Survey evidence lane — MUST land as per-field SOURCE ROWS (`raw_text`)

> **CRITICAL mechanism note (the flaw the first draft missed).** The analyze node
> reads a field's candidate evidence as `db.get_source(sid).raw_text` (it builds
> the analyst prompt and `build_claim` `src_rows` from **source rows**), and QA's
> `_check_value_unsupported` builds its grounding haystack from the cited
> **sources' `raw_text`** too. **Neither reads the `evidence_chunks` table.**
> `ingest_survey`/`ingest_interview` store the per-question answers as
> `evidence_chunks` (`survey:SV-1/q3`) and persist only ONE source per response
> whose `raw_text` is a free-text summary. So answers-as-chunks are **invisible**
> to the analyst and to QA → claims cannot be grounded in them. **Survey/interview
> evidence MUST therefore enter as SOURCE ROWS whose `raw_text` is the groundable
> answer text**, exactly like a web source.

**Mechanism (verified feasible): executor builds survey source rows + SEEDS them into the graph's initial `sources` state.** This rides the exact path web sources use without a collect-node change (the collect node would mis-type a `survey:` url as `web`, and the `sources` table has no field/competitor column to "look up" by — both dead ends; seeding avoids both).

- **Builder `survey_seed(db, run_id, design, fixture) -> list[dict]`** (new, deterministic, LLM-free): for each fixture response/segment, for each `(competitor, field)` it informs:
  - `append_source({...})` a source row — `append_source` honors the dict's `source_type` (no inference), so:
    - `id` = a **STABLE deterministic id** (e.g. `f"survey-{survey_id}-q{n}"` / `f"interview-{interview_id}-seg{m}"`) — so tests + curated paths can reference it and re-seeding is idempotent (run-scoped, seeded once at init, never per-round, so no collision with the collect round-uuid invariant),
    - `source_type` = `"survey"` | `"interview"` (authoritative in `scoring.strength`),
    - `raw_text` = `scrub_open_text(<that field's answer/segment text>)[0]` — the **groundable** content the analyst + QA actually read,
    - `url` = `"survey:SV-1/q3"` | `"interview:IV-1/seg2"` — the locator for the provenance badge + EvidenceDrawer,
    - `source_mode` = `"INGESTED"` (a new provenance value distinct from LIVE/CACHED — **add `"INGESTED"` to the `SourceMode` literal in `schemas.py` AND `frontend/src/api/types.ts`**, since `append_source` takes a raw dict but `SourceDoc`/frontend types constrain the value).
  - returns the new_sources-shaped entries `{"source_id": id, "field": field, "competitor": competitor}` for seeding.
  (The chunk-based `ingest_survey`/`ingest_interview` are **provenance-only** and NOT on the analyze/QA path; prefer building source rows directly + reusing `scrub_open_text`.)
- **Executor (`runner.py`)**, after intake build, before `graph.invoke`:
  - `design_survey(primary_competitor, goal)` → persist + emit `survey_designed` trace event (the design card's data).
  - for each competitor with `fixture_for(competitor)`: `survey_entries += survey_seed(...)`.
  - seed them into the initial state: `graph.invoke({"run_id": ..., "db": db, "intake": intake, "sources": survey_entries})`. `RunState.sources` is an additive-reducer list, so collect's web sources ADD to the seed; `analyze`'s `state["sources"]` filter (`field == ... and competitor == ...`) then surfaces survey + web for that field identically, reading each source's `raw_text` from `db.get_source`. A survey-only field still analyzes (`src_rows` non-empty).
- **No collect-node change, no new node, no re-plan.** The lane is: a deterministic builder + a few executor lines + one extra key in the initial `graph.invoke` state.

**Citing (how a survey source becomes a claim's evidence):** the demo runs the **REAL analyst** (`analyze_fn=None`), which reads the survey source's `raw_text` in its per-field prompt and cites it in `evidence_ref` when it supports the field's value (then `build_claim` includes it; `scoring.strength` sees `source_type="survey"` → authoritative). The deterministic **integration test** injects a survey-aware fake `analyze_fn` that cites the stable survey `source_id`, so the test is deterministic even though the live demo relies on the real analyst.

### 4. Survey-design artifact: persistence + API
- Persist the design payload once per run. Options (implementer picks the lightest that fits existing patterns): (a) a `survey_designed` trace event (already exposed via the trace endpoint), or (b) a tiny `survey_designs` row + `GET /runs/{run_id}/survey-design`. **Recommendation:** dedicated endpoint `GET /runs/{run_id}/survey-design → {survey_id, competitor, goal, questions:[{id,text,field,pii_scrub}]}` for a clean card fetch; emit the trace event too (so it shows in the timeline).

### 5. Frontend
- **问卷设计 card** (new small component, e.g. `SurveyDesignCard.tsx`): collapsible card titled "问卷设计 (Collector)" listing the 8–10 questions with their field tag and a PII-scrub indicator on open-text questions. Rendered in the **Evidence&QA** view (top, collapsible) — near where survey evidence appears. Fetched from the survey-design endpoint; absent/empty → not rendered.
- **Provenance badge:** extend `SourceProvenanceTag` (currently shows `source_mode` LIVE/CACHED) to (a) render the new `source_mode="INGESTED"` value gracefully, and (b) render a `源类型` chip when `source_type` is `survey` or `interview` ("📋 问卷" / "🎤 访谈"). The evidence row + report claim show the survey/interview locator (`survey:SV-1/q3`) as the provenance (opens the EvidenceDrawer; render `survey:`/`interview:` locators as text, NOT an external href).
- Types: add `source_type` to the source/evidence frontend types where needed; add a `SurveyDesign` type.

---

## Honesty & scope discipline (carry into 答辩)
- "Survey/interview evidence is **real, ingested, PII-scrubbed, and gated like any source**; we only admit data we actually collected. Respondent recruitment is operator-supplied — we design the instrument and govern the evidence, we don't fabricate respondents."
- The design card proves the collector **designs** the instrument (not just ingests a blob).
- A competitor without a fixture shows the design card but **no survey evidence** — honest absence, demonstrating we never synthesize.

## Testing
- **Unit:** question→field mapping present for every template question; `fixture_for` returns the demo fixture / None; `survey_evidence_for_field` returns the right chunks for a field and nothing for an unmapped field.
- **Integration (the headline test, deterministic):** drive the executor for the **fixture competitor** with a **survey-aware fake `analyze_fn`** that cites the stable survey `source_id` for the survey-backed field (deterministic — no live LLM). Assert: the seeded `source_type=survey` (or `interview`) source is in the run; a claim cites it; its value is grounded in that source's `raw_text` so it **passes the same `VALUE_UNSUPPORTED`/`SCHEMA_GAP` gate** (verify by reading the persisted source row, not a chunk); the report claim carries the `survey:SV-1/q3` locator (the source `url`) and `source_type=survey`. A run for a **non-fixture** competitor seeds zero survey/interview sources (honest absence) but still emits `survey_designed`.
- **Seeding guard:** assert the seeded survey source appears in the initial `state["sources"]` for its `(competitor, field)` and that `analyze` reads it (catches a regression where the seed doesn't reach the additive `sources` reducer).
- **Mechanism guard:** assert the survey source row's `raw_text` is non-empty and equals the scrubbed answer text (catches the chunk-vs-raw_text regression — the bug this revision fixes).
- **Gate-parity:** a survey claim whose value isn't in the scrubbed response text trips `VALUE_UNSUPPORTED` exactly like a web claim (no special-casing).
- **API/UI:** `GET /runs/{id}/survey-design` returns the questions; `SurveyDesignCard` renders them; `SourceProvenanceTag` shows the 问卷/访谈 chip; no regression to existing suites.

## Out of scope / deferred
- Live distribution/recruitment; operator upload UI (`POST /runs/{id}/survey`); multi-domain (ai_agent/hr) survey fixtures + field maps; LLM-assisted question generation; survey analytics/aggregation beyond per-response evidence.

## Open questions / risks
- **RESOLVED — chunk vs source `raw_text`:** analyze + QA read `source.raw_text`, never `evidence_chunks`. Survey evidence enters as per-`(competitor, field)` **source rows** whose `raw_text` is the scrubbed answer (Component 3). Chunk/locator model = provenance-display only.
- **RESOLVED — how survey sources reach analyze (2nd Codex flag):** NOT via a collect-node lookup (the `sources` table has no field/competitor column) and NOT via collect's result stream (collect infers `source_type` from URL → a `survey:` url mistypes to `web`). Instead the executor `append_source`s the survey rows (which honors `source_type`) and **seeds** their `{source_id, field, competitor}` entries into the additive `graph.invoke({..., "sources": ...})` initial state, so analyze surfaces them with no collect change.
- **Live-run reliability:** the real analyst must actually cite the survey source for a claim to form on a live run. Bounded by giving the survey `raw_text` clear, field-relevant content; the deterministic test does not depend on the LLM. If a live demo must be guaranteed, run the fixture competitor through the curated corpus path (real analyst, deterministic web evidence) and rely on the survey `raw_text` being the strongest signal for its field.
- **Field routing granularity:** one source row per `(competitor, field)` carrying that field's answer text (chosen). If a single answer informs multiple fields, emit one source per field (duplicated raw_text is fine). If it complicates the builder, fall back to the survey's dominant field(s) and note it.
- **Source-vs-source contradiction:** a survey "refutes" stance vs a web "supports" could (correctly) trigger the existing ContradictionCard — a *bonus* demo moment; confirm it doesn't over-fire on benign differences.
- **Demo competitor identity:** the fixture key must match the competitor string the demo corpus/run uses (exact-match or normalized) — verify during implementation.
