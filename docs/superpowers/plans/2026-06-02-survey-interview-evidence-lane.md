# 问卷/访谈 Evidence Lane — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the dormant survey/interview modules into the main run so a survey/interview-backed claim is admitted by the **same deterministic QA gate** as a web claim, plus a thin "问卷设计" output card — closing the one 题目-named requirement (collector 含问卷设计/调研/访谈).

**Architecture:** Survey/interview evidence enters as **source rows** whose `raw_text` is the (PII-scrubbed) answer text, **seeded by the executor into the graph's initial additive `sources` state** (analyze/QA read `db.get_source(sid).raw_text`, never `evidence_chunks`; the collect node would mis-type a `survey:` url — so seeding, not collect-side, is correct). No new graph node, no re-plan. The questionnaire (`design_survey`) is a deterministic *plan* emitted every run; survey/interview *responses* are a curated competitor-keyed fixture (never synthesized).

**Tech Stack:** Python 3.12 · pytest · React/Vite/TS · vitest. Existing: `survey.design_survey`/`scrub_open_text`, `db.append_source`/`insert_trace_event`, `schemas.SourceMode`, `runner.make_run_executor`, `graph_nodes.make_analyze_node`, `qa/rules.qa_check`.

Spec: `docs/superpowers/specs/2026-06-02-survey-interview-evidence-lane-design.md`. Deep audit endorsement + acceptance criteria: `Race/ClaudeCode-DeepAudit.md` §6.

---

## File Structure

- `src/mingjing/survey.py` (modify) — add a `field` tag to each `_QUESTION_TEMPLATE` entry; `design_survey` echoes it.
- `src/mingjing/survey_fixture.py` (create) — the curated competitor-keyed fixture (`DEMO_FIXTURE`) + `fixture_for(competitor)`.
- `src/mingjing/survey_seed.py` (create) — `survey_seed(db, run_id, competitor, fixture) -> list[dict]`: append survey/interview SOURCE ROWS, return the `{source_id, field, competitor}` seed entries.
- `src/mingjing/schemas.py` (modify) — add `"INGESTED"` to the `SourceMode` literal.
- `src/mingjing/runner.py` (modify) — in the executor: `design_survey` → persist trace event; `survey_seed` per fixture competitor; seed entries into `graph.invoke({..., "sources": ...})`.
- `src/mingjing/api.py` (modify) — `GET /runs/{run_id}/survey-design`.
- `frontend/src/api/types.ts` (modify) — `SourceMode` += `'INGESTED'`; add `source_type?` to source types; add `SurveyDesign` types.
- `frontend/src/api/client.ts` (modify) — `getSurveyDesign(runId)`.
- `frontend/src/components/SourceProvenanceTag.tsx` (modify) — accept `sourceType`, render 📋问卷/🎤访谈 chip + handle `INGESTED`.
- `frontend/src/components/SurveyDesignCard.tsx` (create) — the questionnaire-design card.
- `frontend/src/views/EvidenceAndQA.tsx` (modify) — fetch + render `SurveyDesignCard`.
- Tests: `tests/test_survey_field_map.py`, `tests/test_survey_fixture.py`, `tests/test_survey_seed.py`, `tests/test_survey_lane_integration.py`, extend `tests/test_api.py`; `frontend/src/components/SurveyDesignCard.test.tsx`, extend `SourceProvenanceTag` / `EvidenceAndQA` tests.

---

## Task 1: Question → schema-field mapping

**Files:**
- Modify: `src/mingjing/survey.py` (`_QUESTION_TEMPLATE` entries; `design_survey` output)
- Test: `tests/test_survey_field_map.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Every survey question (except the qualification gate) maps to a real
default-domain schema field, and design_survey echoes the field."""
from mingjing.schema_registry import load_domain
from mingjing.survey import design_survey


def test_every_question_has_a_valid_field():
    default_fields = set(load_domain("default"))
    design = design_survey("Notion", "compare note apps")
    for q in design["questions"]:
        assert "field" in q, f"{q['id']} missing field"
        if q["field"] is not None:  # q1 qualification gate has no field
            assert q["field"] in default_fields, f"{q['id']} -> {q['field']!r} not a default field"


def test_qualification_question_has_no_field():
    design = design_survey("Notion", "g")
    q1 = next(q for q in design["questions"] if q["id"] == "q1")
    assert q1["field"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_survey_field_map.py -v`
Expected: FAIL with `KeyError: 'field'` / `assert 'field' in q`.

- [ ] **Step 3: Add a `field` to each `_QUESTION_TEMPLATE` entry**

In `src/mingjing/survey.py`, add a `"field": <value>` key to each of the 10 dicts in `_QUESTION_TEMPLATE`, using this mapping (by question id):

```
q1  qualification        -> None
q2  overall_satisfaction -> "user_sentiment"
q3  feature_satisfaction -> "feature_tree"
q4  nps                  -> "user_sentiment"
q5  nps_rationale (open) -> "user_sentiment"
q6  feature_gap          -> "feature_tree"
q7  switching_intent     -> "pricing_model"
q8  wtp                  -> "pricing_model"
q9  barriers             -> "user_persona"
q10 open_feedback (open) -> "user_sentiment"
```

`field` is a non-`str` value, so the existing `design_survey` loop (`q[k] = v.format(...) if isinstance(v, str) else v`) passes it through unchanged — no other `survey.py` change needed. (If the template entries use different ids than q1–q10, map by `dimension` instead and keep the same field targets.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_survey_field_map.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/mingjing/survey.py tests/test_survey_field_map.py
git commit -m "feat(survey): tag each questionnaire question with its schema field"
```

---

## Task 2: Curated competitor-keyed fixture

**Files:**
- Create: `src/mingjing/survey_fixture.py`
- Test: `tests/test_survey_fixture.py` (create)

- [ ] **Step 1: Write the failing test**

```python
from mingjing.survey_fixture import fixture_for


def test_fixture_for_demo_competitor_returns_per_field_text():
    fx = fixture_for("Notion")
    assert fx is not None
    # survey has per-field self-contained answer text for grounding
    assert "user_sentiment" in fx["survey"]["fields"]
    assert isinstance(fx["survey"]["fields"]["user_sentiment"], str)
    assert fx["survey"]["survey_id"] == "SV-1"
    # interview present with a field
    assert fx["interview"]["interview_id"] == "IV-1"
    assert fx["interview"]["fields"]


def test_fixture_for_match_is_case_insensitive():
    assert fixture_for("notion") is not None
    assert fixture_for("NOTION") is not None


def test_fixture_for_unknown_competitor_is_none():
    assert fixture_for("Acme Unknown Co") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_survey_fixture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mingjing.survey_fixture'`.

- [ ] **Step 3: Create `src/mingjing/survey_fixture.py`**

```python
"""Curated, competitor-keyed survey/interview fixture.

Per-field answer text is REAL-shaped demo data (we never synthesize responses for
arbitrary competitors). Each field's value is a self-contained string usable as a
source ``raw_text`` so a claim's value can be grounded in it (value ⊆ text). Keyed
to the demo competitor the corpus already uses (Notion). PII is embedded in
open-text so ``scrub_open_text`` visibly does work.
"""

from typing import Any

# field -> self-contained answer text (the groundable content for that field).
DEMO_FIXTURE: dict[str, dict[str, Any]] = {
    "notion": {
        "survey": {
            "survey_id": "SV-1",
            "fields": {
                "user_sentiment": (
                    "Across 30 surveyed Notion users overall satisfaction is high; "
                    "respondents praise flexibility but several call the mobile app slow."
                ),
                "feature_tree": (
                    "Respondents rate databases and templates as Notion's strongest "
                    "features; AI writing assist is the most-requested gap."
                ),
                "pricing_model": (
                    "Most respondents report the Pro plan at $10/mo and consider it fair value."
                ),
            },
        },
        "interview": {
            "interview_id": "IV-1",
            "fields": {
                "user_persona": (
                    "Interviewee, an operations manager, describes the core Notion "
                    "persona as a cross-functional team lead consolidating docs and tasks."
                ),
            },
        },
    },
}


def fixture_for(competitor: str | None) -> dict[str, Any] | None:
    """Return the curated fixture for ``competitor`` (case-insensitive), or None."""
    if not competitor:
        return None
    return DEMO_FIXTURE.get(competitor.strip().lower())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_survey_fixture.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/mingjing/survey_fixture.py tests/test_survey_fixture.py
git commit -m "feat(survey): curated Notion survey/interview fixture (per-field groundable text)"
```

---

## Task 3: `survey_seed` builder + `INGESTED` source mode

**Files:**
- Modify: `src/mingjing/schemas.py:17` (`SourceMode` literal)
- Create: `src/mingjing/survey_seed.py`
- Test: `tests/test_survey_seed.py` (create)

- [ ] **Step 1: Write the failing test**

```python
from mingjing.db import Database
from mingjing.survey_fixture import fixture_for
from mingjing.survey_seed import survey_seed


def _db(tmp_path) -> Database:
    d = Database(str(tmp_path / "s.db"))
    d.init_schema()
    return d


def test_survey_seed_appends_source_rows_and_returns_entries(tmp_path):
    db = _db(tmp_path)
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    entries = survey_seed(db, run_id, "Notion", fixture_for("Notion"))

    # returns new_sources-shaped entries for graph seeding
    assert entries, "expected seed entries"
    for e in entries:
        assert set(e) == {"source_id", "field", "competitor"}
        assert e["competitor"] == "Notion"

    # each entry has a persisted source row with groundable raw_text + survey type
    pricing = next(e for e in entries if e["field"] == "pricing_model")
    row = db.get_source(pricing["source_id"])
    assert row is not None
    assert row["source_type"] == "survey"
    assert row["source_mode"] == "INGESTED"
    assert "Pro plan at $10/mo" in row["raw_text"]      # groundable content (raw_text, not a chunk)
    assert row["url"] == "survey:SV-1/pricing_model"     # locator

    # interview field present as source_type=interview
    persona = next(e for e in entries if e["field"] == "user_persona")
    assert db.get_source(persona["source_id"])["source_type"] == "interview"


def test_survey_seed_is_deterministic_and_idempotent_ids(tmp_path):
    db = _db(tmp_path)
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    ids1 = {e["source_id"] for e in survey_seed(db, run_id, "Notion", fixture_for("Notion"))}
    assert "survey-SV-1-pricing_model" in ids1  # stable id (citable by tests/curated paths)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_survey_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mingjing.survey_seed'`.

- [ ] **Step 3a: Add `INGESTED` to the `SourceMode` literal**

In `src/mingjing/schemas.py` line 17:

```python
SourceMode = Literal["LIVE", "CACHED", "INGESTED"]
```

- [ ] **Step 3b: Create `src/mingjing/survey_seed.py`**

```python
"""Build survey/interview SOURCE ROWS from a fixture and return graph-seed entries.

Survey/interview evidence MUST enter the pipeline as source rows whose ``raw_text``
holds the (PII-scrubbed) answer text — analyze + QA read ``db.get_source(sid).raw_text``,
never ``evidence_chunks``. The executor seeds the returned entries into the graph's
initial additive ``sources`` state so analyze surfaces them per (competitor, field)
exactly like a web source. Deterministic, LLM-free; ids are stable (run-scoped, once).
"""

import time
from typing import Any

from .survey import scrub_open_text


def _append_field_sources(
    db: Any, run_id: str, competitor: str, *,
    kind: str, ident: str, fields: dict[str, str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for field, text in fields.items():
        scrubbed = scrub_open_text(text)[0]
        source_id = f"{kind}-{ident}-{field}"          # stable, citable id
        locator = f"{kind}:{ident}/{field}"            # survey:SV-1/pricing_model
        db.append_source(
            {
                "id": source_id,
                "run_id": run_id,
                "url": locator,
                "title": f"{kind} {ident} ({field})",
                "source_type": kind,                    # "survey" | "interview" (authoritative)
                "source_mode": "INGESTED",
                "fetched_at": time.time(),
                "content_hash": None,
                "raw_text": scrubbed,                   # the GROUNDABLE content
                "meta_json": "{}",
            }
        )
        entries.append({"source_id": source_id, "field": field, "competitor": competitor})
    return entries


def survey_seed(
    db: Any, run_id: str, competitor: str, fixture: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Append per-(competitor, field) survey/interview source rows; return seed entries.

    Returns ``[]`` when ``fixture`` is None (honest absence — no synthesized evidence).
    """
    if not fixture:
        return []
    entries: list[dict[str, Any]] = []
    survey = fixture.get("survey")
    if survey:
        entries += _append_field_sources(
            db, run_id, competitor,
            kind="survey", ident=survey["survey_id"], fields=survey.get("fields", {}),
        )
    interview = fixture.get("interview")
    if interview:
        entries += _append_field_sources(
            db, run_id, competitor,
            kind="interview", ident=interview["interview_id"], fields=interview.get("fields", {}),
        )
    return entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_survey_seed.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full backend suite (no regression from the SourceMode literal change)**

Run: `uv run pytest -q`
Expected: all pass (baseline 529).

- [ ] **Step 6: Commit**

```bash
git add src/mingjing/schemas.py src/mingjing/survey_seed.py tests/test_survey_seed.py
git commit -m "feat(survey): survey_seed builds per-field survey/interview source rows (raw_text) + INGESTED mode"
```

---

## Task 4: Executor wiring + headline integration test

**Files:**
- Modify: `src/mingjing/runner.py` (the `run(run_id)` body: design trace + seed + invoke)
- Test: `tests/test_survey_lane_integration.py` (create)

- [ ] **Step 1: Write the failing integration test (the acceptance criterion)**

```python
"""A run for the fixture competitor produces a survey-backed claim that passes
the SAME QA gate (value grounded in the survey source row's raw_text), and the
report claim carries source_type=survey + the survey: locator. A non-fixture
competitor seeds zero survey sources but still emits survey_designed.

Deterministic: a survey-aware fake analyze_fn cites the stable survey source id.
"""
import pytest

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.runner import make_run_executor


@pytest.fixture()
def settings(tmp_path) -> Settings:
    # Mirror tests/test_runner.py: an offline Settings with temp paths.
    # REUSE the existing test_runner.py settings fixture/helper rather than
    # reconstructing it; copy its construction here verbatim.
    ...  # <- replace with test_runner.py's settings construction (see that file)


def _fake_survey_analyst(*args, **kwargs):
    """Cite the seeded survey source for pricing_model; value ⊆ its raw_text."""
    field = kwargs.get("field")
    if field == "pricing_model":
        return {
            "claim_type": "fact",
            "statement": "Surveyed users report Pro at $10/mo.",
            "value": {"tiers": ["Pro plan at $10/mo"]},   # substring of the fixture text
            "evidence_ref": ["survey-SV-1-pricing_model"],  # stable seeded id
        }
    return {}  # other fields: skip (no evidence)


def _no_web(query, *, cache, source_cap, mode="live_first"):
    return []


def test_fixture_run_yields_survey_backed_passing_claim(tmp_path, settings):
    db = Database(str(tmp_path / "run.db")); db.init_schema()
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="compare note apps")
    execu = make_run_executor(
        lambda: db, settings=settings,
        collect_fn=_no_web, analyze_fn=_fake_survey_analyst, prewarm=False,
    )
    execu(run_id)

    # the seeded survey source exists and is typed survey
    src = db.get_source("survey-SV-1-pricing_model")
    assert src is not None and src["source_type"] == "survey"

    # a pricing_model claim passed QA, citing the survey source (value ⊆ raw_text)
    passed = [c for c in db.latest_claims_for_run(run_id)
              if c["schema_field"] == "pricing_model" and c["status"] == "pass"]
    assert passed, "expected a passing survey-backed pricing_model claim"

    # survey_designed trace event emitted (the design card's data)
    designed = [e for e in db.trace_events_for_run(run_id)
                if e["event_type"] == "survey_designed"]
    assert designed


def test_non_fixture_competitor_seeds_no_survey_but_emits_design(tmp_path, settings):
    db = Database(str(tmp_path / "run2.db")); db.init_schema()
    run_id = db.create_run(category="x", competitors=["Acme Unknown Co"], goal="g")
    execu = make_run_executor(
        lambda: db, settings=settings,
        collect_fn=_no_web, analyze_fn=lambda *a, **k: {}, prewarm=False,
    )
    execu(run_id)
    survey_sources = [s for s in db.sources_for_run(run_id) if s["source_type"] in ("survey", "interview")]
    assert survey_sources == []           # honest absence — no synthesized evidence
    assert [e for e in db.trace_events_for_run(run_id) if e["event_type"] == "survey_designed"]
```

(For `settings`: open `tests/test_runner.py`, copy its `settings` fixture construction verbatim into Step 1 — it builds an offline `Settings` with `tmp_path` cache/db; do not invent one.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_survey_lane_integration.py -v`
Expected: FAIL — `db.get_source("survey-SV-1-pricing_model")` is None and no `survey_designed` event (executor not wired yet).

- [ ] **Step 3: Wire the executor**

In `src/mingjing/runner.py`: add imports and, inside `run(run_id)` after `run_row` is read and `intake` is built, BEFORE `graph.invoke`, design + seed; then pass `sources` into the invoke.

Add to imports (top of file):
```python
import json

from .survey import design_survey
from .survey_fixture import fixture_for
from .survey_seed import survey_seed
```

After `intake = {...}` (and the `fields` snapshot), add:
```python
        # 问卷设计 (collector PLAN, deterministic) — emitted every run for the card.
        primary = competitors[0] if competitors else ""
        design = design_survey(primary, run_row.get("goal") or "")
        db.insert_trace_event(
            {
                "run_id": run_id,
                "agent": "collector",
                "node": "collect",
                "event_type": "survey_designed",
                "payload_json": json.dumps(design, ensure_ascii=False),
            }
        )

        # Survey/interview EVIDENCE — only for competitors we actually have data for.
        survey_entries: list[dict[str, Any]] = []
        for comp in competitors:
            survey_entries += survey_seed(db, run_id, comp, fixture_for(comp))
```

Then change the `graph.invoke(...)` call (inside the existing `with domain_ctx:` body) from:
```python
                    final = graph.invoke(
                        {"run_id": run_id, "db": db, "intake": intake}
                    )
```
to:
```python
                    final = graph.invoke(
                        {
                            "run_id": run_id,
                            "db": db,
                            "intake": intake,
                            "sources": survey_entries,  # seed: additive RunState.sources
                        }
                    )
```

(Place the design+seed block before the `with domain_ctx:`/cache block so `survey_entries` is in scope at `graph.invoke`. `RunState.sources` is an additive-reducer list, so collect's web sources add to the seed; `analyze`'s `state["sources"]` filter surfaces survey sources per (competitor, field).)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_survey_lane_integration.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full backend suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mingjing/runner.py tests/test_survey_lane_integration.py
git commit -m "feat(survey): executor designs survey + seeds survey/interview source rows into the run"
```

---

## Task 5: `GET /runs/{run_id}/survey-design` endpoint

**Files:**
- Modify: `src/mingjing/api.py` (new route, near `get_report`)
- Test: `tests/test_api.py` (extend)

- [ ] **Step 1: Write the failing test (add to tests/test_api.py)**

```python
def test_survey_design_endpoint_returns_questions(client, db):
    import json
    run_id = db.create_run(category="notes", competitors=["Notion"], goal="g")
    db.insert_trace_event({
        "run_id": run_id, "agent": "collector", "node": "collect",
        "event_type": "survey_designed",
        "payload_json": json.dumps({"survey_id": "SV-1", "competitor": "Notion",
                                    "goal": "g", "questions": [{"id": "q1", "field": None}]}),
    })
    resp = client.get(f"/runs/{run_id}/survey-design")
    assert resp.status_code == 200
    body = resp.json()
    assert body["survey_id"] == "SV-1"
    assert body["questions"][0]["id"] == "q1"


def test_survey_design_endpoint_empty_when_none(client, db):
    run_id = db.create_run(category="x", competitors=["Acme"], goal="g")
    resp = client.get(f"/runs/{run_id}/survey-design")
    assert resp.status_code == 200
    assert resp.json() == {}   # no design emitted yet → empty (frontend hides the card)
```

(Use the existing `client`/`db` fixtures in `tests/test_api.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_api.py -k survey_design -v`
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Add the route in `api.py`** (mirror the `get_report` run-scoped style: `_get_db()` → `run_exists` 404 → read)

```python
    @app.get("/runs/{run_id}/survey-design")
    def get_survey_design(run_id: str) -> dict[str, Any]:
        """The questionnaire the collector designed for this run (the 问卷设计 card).

        Reads the latest ``survey_designed`` trace event payload; ``{}`` when none.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        for ev in reversed(active_db.trace_events_for_run(run_id)):
            if ev.get("event_type") == "survey_designed":
                try:
                    return json.loads(ev.get("payload_json") or "{}")
                except (json.JSONDecodeError, TypeError):
                    return {}
        return {}
```

(`json` is already imported in `api.py`.)

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `uv run pytest tests/test_api.py -k survey_design -v && uv run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/mingjing/api.py tests/test_api.py
git commit -m "feat(api): GET /runs/{id}/survey-design (questionnaire-design card data)"
```

---

## Task 6: Frontend — provenance chip, design card, types, client

**Files:**
- Modify: `frontend/src/api/types.ts` (`SourceMode`, source_type, `SurveyDesign`)
- Modify: `frontend/src/api/client.ts` (`getSurveyDesign`)
- Modify: `frontend/src/components/SourceProvenanceTag.tsx`
- Create: `frontend/src/components/SurveyDesignCard.tsx`
- Modify: `frontend/src/views/EvidenceAndQA.tsx`
- Test: `frontend/src/components/SurveyDesignCard.test.tsx` (create); extend `SourceProvenanceTag.test.tsx`

- [ ] **Step 1: Types + client (no test needed for pure types; client mirrors `getReport`)**

In `frontend/src/api/types.ts`:
```typescript
export type SourceMode = 'LIVE' | 'CACHED' | 'INGESTED';
```
Add (near the report types):
```typescript
export interface SurveyDesignQuestion {
  id: string;
  text: string;
  field: string | null;
  pii_scrub?: boolean;
}
export interface SurveyDesign {
  survey_id: string;
  competitor: string;
  goal: string;
  questions: SurveyDesignQuestion[];
}
```
In `frontend/src/api/client.ts` (mirror `getReport`):
```typescript
/** GET /runs/{id}/survey-design → SurveyDesign | {} (empty when none). */
export async function getSurveyDesign(runId: string): Promise<Partial<SurveyDesign>> {
  return request<Partial<SurveyDesign>>(`/runs/${runId}/survey-design`);
}
```

- [ ] **Step 2: Provenance chip — write failing test** (extend `frontend/src/components/SourceProvenanceTag.test.tsx`)

```typescript
it('renders a 问卷 chip for source_type=survey', () => {
  render(<SourceProvenanceTag mode="INGESTED" sourceType="survey" />);
  expect(screen.getByText(/问卷/)).toBeInTheDocument();
});
it('renders a 访谈 chip for source_type=interview', () => {
  render(<SourceProvenanceTag mode="INGESTED" sourceType="interview" />);
  expect(screen.getByText(/访谈/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/SourceProvenanceTag.test.tsx`
Expected: FAIL (no `sourceType` prop / no chip).

- [ ] **Step 4: Implement the chip** — in `SourceProvenanceTag.tsx`, add an optional `sourceType?: string` prop; when it's `'survey'`/`'interview'`, render a chip (📋 问卷 / 🎤 访谈) alongside the existing mode text; ensure `mode === 'INGESTED'` renders gracefully (treat as not-LIVE; label e.g. "已接入"). Keep existing LIVE/CACHED behavior unchanged.

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/SourceProvenanceTag.test.tsx`
Expected: PASS.

- [ ] **Step 6: SurveyDesignCard — write failing test** (`frontend/src/components/SurveyDesignCard.test.tsx`)

```typescript
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SurveyDesignCard } from './SurveyDesignCard';

const DESIGN = {
  survey_id: 'SV-1', competitor: 'Notion', goal: 'g',
  questions: [
    { id: 'q1', text: '您是否使用 Notion？', field: null },
    { id: 'q2', text: '满意度？', field: 'user_sentiment' },
  ],
};

describe('SurveyDesignCard', () => {
  it('renders the designed questions with field tags', () => {
    render(<SurveyDesignCard design={DESIGN} />);
    expect(screen.getByText(/问卷设计/)).toBeInTheDocument();
    expect(screen.getByText('满意度？')).toBeInTheDocument();
    expect(screen.getByText('user_sentiment')).toBeInTheDocument();
  });
  it('renders nothing when design is empty', () => {
    const { container } = render(<SurveyDesignCard design={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/SurveyDesignCard.test.tsx`
Expected: FAIL (component missing).

- [ ] **Step 8: Implement `SurveyDesignCard.tsx`**

```typescript
import type { SurveyDesign } from '../api/types';

/** 问卷设计 (Collector) — the deterministic questionnaire the collector designed.
 *  Renders nothing when no design (e.g. fetch returned {}). */
export function SurveyDesignCard({ design }: { design: Partial<SurveyDesign> }): React.ReactElement | null {
  const questions = design.questions ?? [];
  if (questions.length === 0) return null;
  return (
    <details className="rounded-lg border border-gray-200 bg-white p-3" data-testid="survey-design-card" open>
      <summary className="text-sm font-semibold text-gray-700 cursor-pointer">
        📋 问卷设计 (Collector) · {design.survey_id} · {questions.length} 题
      </summary>
      <ul className="mt-2 space-y-1">
        {questions.map((q) => (
          <li key={q.id} className="text-xs text-gray-600 flex items-start gap-2">
            <span className="flex-1">{q.text}</span>
            {q.field && (
              <span className="text-[10px] font-medium text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">
                {q.field}
              </span>
            )}
            {q.pii_scrub && (
              <span className="text-[10px] text-amber-700">脱敏</span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default SurveyDesignCard;
```

- [ ] **Step 9: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/SurveyDesignCard.test.tsx`
Expected: PASS.

- [ ] **Step 10: Wire the card into `EvidenceAndQA.tsx`** — import `getSurveyDesign` + `SurveyDesignCard`; add `const [design, setDesign] = useState<Partial<SurveyDesign>>({})`; a `useEffect` on `runId` that `getSurveyDesign(runId).then(setDesign).catch(() => {})`; render `<SurveyDesignCard design={design} />` at the top of the middle (证据&溯源) column (above the source list). Pass `sourceType={src.source_type}` to existing `SourceProvenanceTag` usages (add `source_type` to the source row type the view consumes).

- [ ] **Step 11: Run frontend suite + typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: all pass (baseline 155 + new); tsc clean.

- [ ] **Step 12: Commit**

```bash
cd /home/lingxufeng/Langgraph/mingjing
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/components/SourceProvenanceTag.tsx frontend/src/components/SourceProvenanceTag.test.tsx frontend/src/components/SurveyDesignCard.tsx frontend/src/components/SurveyDesignCard.test.tsx frontend/src/views/EvidenceAndQA.tsx
git commit -m "feat(survey): frontend 问卷设计 card + survey/interview provenance chip"
```

---

## Task 7: Gate-parity + mechanism guards (lock the invariants)

**Files:**
- Test: `tests/test_survey_lane_integration.py` (extend)

- [ ] **Step 1: Add the guard tests**

```python
def test_survey_value_not_in_text_trips_value_unsupported(tmp_path):
    """Gate-parity: a survey claim whose value isn't in the survey raw_text is
    rejected by VALUE_UNSUPPORTED exactly like a web claim (no special-casing)."""
    from mingjing.qa.rules import qa_check
    from mingjing.schemas import IssueCode
    claimset = {
        "claims": [{
            "id": "S1", "schema_field": "pricing_model", "claim_type": "fact",
            "competitor": "Notion", "value": {"tiers": ["Fabricated Enterprise Tier"]},
            "evidence": [{"source_id": "survey-SV-1-pricing_model", "snippet": "x", "relevance": "supports"}],
        }],
        "sources": {"survey-SV-1-pricing_model": {
            "raw_text": "Most respondents report the Pro plan at $10/mo.",
            "source_type": "survey", "url": "survey:SV-1/pricing_model"}},
        "coverage": {"required_fields": [], "covered_fields": []},
    }
    assert IssueCode.VALUE_UNSUPPORTED in {i.code for i in qa_check(claimset)}


def test_survey_source_raw_text_is_groundable_not_chunk(tmp_path):
    """Mechanism guard: the seeded survey source row's raw_text is the scrubbed
    answer (catches a chunk-vs-raw_text regression)."""
    from mingjing.db import Database
    from mingjing.survey_fixture import fixture_for
    from mingjing.survey_seed import survey_seed
    db = Database(str(tmp_path / "g.db")); db.init_schema()
    run_id = db.create_run(category="n", competitors=["Notion"], goal="g")
    survey_seed(db, run_id, "Notion", fixture_for("Notion"))
    row = db.get_source("survey-SV-1-pricing_model")
    assert row["raw_text"] and "Pro plan at $10/mo" in row["raw_text"]
```

- [ ] **Step 2: Run to verify they pass** (these lock existing behavior from Tasks 3–4)

Run: `uv run pytest tests/test_survey_lane_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Run full backend + frontend suites**

Run: `uv run pytest -q && cd frontend && npx vitest run`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_survey_lane_integration.py
git commit -m "test(survey): gate-parity + chunk-vs-raw_text mechanism guards"
```

---

## Self-Review

**Spec coverage:**
- Component 1 (question→field) → Task 1 ✓
- Component 2 (fixture) → Task 2 ✓
- Component 3 (survey_seed source rows + INGESTED + executor seed into initial `sources`) → Tasks 3, 4 ✓
- Component 4 (survey-design persistence + API) → Task 4 (trace event) + Task 5 (endpoint) ✓
- Component 5 (frontend card + provenance chip + types) → Task 6 ✓
- Testing (integration headline, seeding/mechanism/gate-parity guards, non-fixture absence, API/UI) → Tasks 4, 5, 6, 7 ✓
- Honesty boundary (no synthesis; non-fixture seeds zero) → asserted in Task 4 `test_non_fixture_competitor_...` ✓

**Placeholder scan:** one intentional reference — the `settings` fixture in Task 4 says "copy `tests/test_runner.py`'s settings construction verbatim." That's reuse of an existing fixture (not invented logic); the implementer reads test_runner.py first. All other steps carry complete code.

**Type/name consistency:** stable ids `survey-SV-1-<field>` / `interview-IV-1-<field>` and locators `survey:SV-1/<field>` are used identically in `survey_seed.py`, the integration test, the guard tests, and the frontend locator display. `SourceMode` gains `INGESTED` in both `schemas.py` and `types.ts`. `survey_seed(db, run_id, competitor, fixture)` signature matches all call sites. Question `field` values are all default-domain schema keys (`user_sentiment`/`feature_tree`/`pricing_model`/`user_persona`), matching `load_domain("default")`.

**Out-of-scope honored:** no recruitment/upload UI, no multi-domain fixture, no LLM in survey path, chunk model untouched (provenance-only). Docs sync (audit P0#3) and frontend visibility P0 (ledger/contradiction) are **separate** efforts, not in this plan.
