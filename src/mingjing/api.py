"""Read-only FastAPI views over the SQLite source-of-truth (Task 18).

Design notes:
- All endpoints are READ-ONLY except ``POST /runs`` (which creates a run row and
  optionally kicks off the executor in a background daemon thread).
- The factory ``create_app(db=..., run_executor=...)`` allows tests to inject a
  ``tmp_path`` DB and a fake executor without network or LLM.
- The module-level ``app = create_app(wire_default_executor=True)`` is what
  ``uvicorn mingjing.api:app`` picks up; it builds a real DB lazily from
  ``Settings`` and wires the production run executor (``make_run_executor``)
  bound to that same lazy DB, so a live ``POST /runs`` actually drives the
  graph. No network I/O occurs at import time — the executor is only CALLED on
  ``POST /runs``, inside a background daemon thread.
- CORS is permissive: the Vite dev server runs on a different port.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .api_helpers import (
    _build_report_sections,
    _claim_groundedness,
    _evidence_source_ids,
    _run_with_logging,
    load_credibility_inputs,
)
from .api_models import ClaimCorrectionRequest, CreateRunRequest, SurveyImportRequest
from .claim_builder import to_json
from .db import Database
from .metrics import compute_metrics
from .schema_registry import (
    domain_source_weights,
    list_domains,
    load_domain,
    resolved_active_domain,
)
from .scope import scope_methodology_for_run
from .synthesis import build_withheld_disclosure

# Re-export the request models and pure helpers so existing import paths keep
# working (e.g. ``from mingjing.api import CreateRunRequest`` and the tests that
# reach for ``api._build_report_sections`` / ``api._claim_groundedness``). These
# now live in ``api_models`` / ``api_helpers``; the names below are the stable
# public surface of this module.
__all__ = [
    "ClaimCorrectionRequest",
    "CreateRunRequest",
    "_build_report_sections",
    "_claim_groundedness",
    "_evidence_source_ids",
    "_run_with_logging",
    "app",
    "create_app",
    "load_credibility_inputs",
]

_log = logging.getLogger(__name__)


def _source_weights_view(domain: str) -> dict[str, Any]:
    """Build the ADVISORY source-weights block for ``GET /schemas/{domain}``.

    Pure, read-only projection: the domain's own ``source_weights`` map (may be
    empty), the built-in ``fallback`` letters, and ``unknown_letter`` for types
    in neither. This is SECONDARY Admiralty reliability metadata for the legend;
    it never enters the 3-tier scorer (``scoring.strength`` is independent of
    Admiralty letters), so it cannot change any verdict/tier/admission.
    """
    from .admiralty import fallback_source_weights

    return {
        "weights": domain_source_weights(domain),
        "fallback": fallback_source_weights(),
        "unknown_letter": "F",
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    db: Database | None = None,
    run_executor: Callable[[str], None] | None = None,
    wire_default_executor: bool = False,
) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        db: A pre-opened :class:`~mingjing.db.Database` instance. When
            ``None`` (default), the real DB is opened lazily from ``Settings``
            the first time an endpoint needs it.
        run_executor: A callable ``(run_id: str) -> None`` that drives the
            graph run. When not ``None``, ``POST /runs`` launches it in a
            daemon background thread. When ``None`` (the default in tests),
            ``POST /runs`` only creates the run row — unless
            ``wire_default_executor`` builds the real one.
        wire_default_executor: When ``True`` and ``run_executor`` is ``None``,
            construct the production executor (``make_run_executor``) bound to
            this app's own lazy ``_get_db`` so a live ``POST /runs`` actually
            drives the graph. The module-level ``app`` sets this; tests leave it
            ``False`` so the executor stays ``None`` and no graph runs.

    Returns:
        A configured :class:`fastapi.FastAPI` instance.
    """
    app = FastAPI(title="MingJing Evidence API", version="0.1.0")

    # --- CORS ---------------------------------------------------------------
    # allow_origin_regex covers all localhost ports; no need for a static list.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Lazy DB resolver ---------------------------------------------------
    _db_holder: list[Database] = []  # mutable cell for closure
    _db_init_lock = threading.Lock()

    def _get_db() -> Database:
        """Return the injected DB, or lazily open the configured DB path.

        The double-checked lock on ``_db_holder`` prevents a TOCTOU race where
        two concurrent first-requests would each open a separate connection.
        """
        if db is not None:
            return db
        if not _db_holder:
            with _db_init_lock:
                if not _db_holder:
                    from .config import Settings

                    settings = Settings.load()
                    lazy_db = Database(settings.db_path)
                    lazy_db.init_schema()
                    # Server-side recovery: any run left at status='running' for
                    # more than 1h has an orphaned (dead) executor process — flip
                    # it to 'error' so the UI doesn't show a perpetual spinner.
                    # Non-destructive: only stale running runs are touched.
                    lazy_db.reap_stale_running(older_than_s=3600.0)
                    _db_holder.append(lazy_db)
        return _db_holder[0]

    # --- Default production executor ----------------------------------------
    # When asked to build the production app (and no executor was injected),
    # bind the real executor to THIS app's lazy ``_get_db`` so the executor and
    # the read endpoints share one Database/connection. Tests leave
    # ``wire_default_executor=False`` so ``run_executor`` stays ``None``.
    if run_executor is None and wire_default_executor:
        from .runner import make_run_executor

        run_executor = make_run_executor(get_db=_get_db)

    # --- Endpoints ----------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness check."""
        return {"status": "ok"}

    @app.post("/runs", status_code=201)
    def create_run(body: CreateRunRequest) -> dict[str, str]:
        """Create a new analysis run and optionally kick off the executor.

        The ``depth`` field defaults to the app's settings value
        (``MINGJING_DEPTH`` env var, default ``"quick"``) when the request
        omits it.

        Returns:
            ``{"run_id": "<hex>"}`` with HTTP 201.
        """
        active_db = _get_db()
        # Resolve depth: request value takes precedence; fall back to settings
        # (loaded lazily from MINGJING_DEPTH env var) or hardcoded "quick".
        if body.depth is not None:
            resolved_depth = body.depth
        else:
            try:
                from .config import Settings

                resolved_depth = Settings.load().depth
            except Exception:
                _log.warning(
                    "Failed to load Settings.depth; falling back to 'quick'",
                    exc_info=True,
                )
                resolved_depth = "quick"
        run_id = active_db.create_run(
            category=body.category,
            competitors=body.competitors,
            goal=body.goal,
            domain=body.domain,
            depth=resolved_depth,
            market_scope=body.market_scope,
            max_competitors=body.max_competitors,
            seed_competitors=body.seed_competitors,
        )
        if run_executor is not None:
            t = threading.Thread(
                target=_run_with_logging,
                args=(run_executor, run_id),
                daemon=True,
            )
            t.start()
        return {"run_id": run_id}

    @app.get("/runs")
    def list_runs(limit: int = 20) -> dict[str, Any]:
        """List recent runs newest-first (read-only) for the workbench picker.

        Powers the frontend "查看示例分析" one-click example and the 近期运行
        list. Each item carries a ``passed_claims`` count so the UI can surface
        a "✓ N 条已验证" badge and pick a good corpus-driven example run.

        Args:
            limit: Maximum number of runs to return (default 20, capped at 100).

        Returns:
            ``{"runs": [...]}`` — newest-first run summary dicts.
        """
        active_db = _get_db()
        capped = max(1, min(int(limit), 100))
        return {"runs": active_db.list_runs(limit=capped)}

    @app.get("/runs/{run_id}/trace")
    def get_trace(run_id: str, since: int = 0) -> dict[str, Any]:
        """Return trace events for a run, supporting incremental polling.

        Args:
            run_id: The run identifier.
            since: Return only events with ``id > since`` (default 0 = all).

        Returns:
            ``{"events": [...], "max_seq": N}`` where ``max_seq`` is the highest
            event ``id`` returned (0 when empty), for use as the next ``since``.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        events = active_db.trace_events_for_run(run_id, since=since)
        max_seq = events[-1]["id"] if events else 0
        return {"events": events, "max_seq": max_seq}

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str) -> dict[str, Any]:
        """Return QA-passed claims grouped by schema_field with a strength tally.

        Only ``status="pass"`` claims appear. Each section includes decoded
        ``value`` and ``evidence_source_ids``. The response also carries a
        deterministic ``scope_methodology`` block (range & method disclosure;
        see :func:`mingjing.scope.scope_methodology_for_run`).
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        claims = active_db.latest_claims_for_run(run_id)
        sources = {s["id"]: s for s in active_db.sources_for_run(run_id)}
        report = _build_report_sections(claims, sources)
        report["scope_methodology"] = scope_methodology_for_run(active_db, run_id)
        return report

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

    @app.get("/runs/{run_id}/synthesis")
    def get_synthesis(run_id: str) -> dict[str, Any]:
        """Return the latest projected synthesis for a run (read-only, no LLM).

        The synthesis pass runs once after the write node and persists a single
        projected payload; this endpoint serves it verbatim (already projected to
        passed claims). When the run has no synthesis row yet (synthesis is
        non-fatal and may have produced nothing), an empty object ``{}`` is
        returned so the frontend can fall back to the deterministic ledger.

        Raises:
            HTTPException(404): When the run does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        return active_db.get_synthesis(run_id) or {}

    @app.get("/runs/{run_id}/withheld")
    def get_withheld(run_id: str) -> dict[str, Any]:
        """Enumerate claims withheld from the report and WHY (advisory, no LLM).

        A claim that the last QA round flagged correctly STAYS ``draft`` (absent
        from the ``status="pass"`` report). This endpoint exposes
        ``build_withheld_disclosure`` so the frontend can render a self-explaining
        empty/partial run ("N claims withheld: VALUE_UNSUPPORTED…") instead of a
        blank panel. It never promotes claims or alters any verdict.

        Returns:
            ``{"withheld": [{"claim_id", "issue_codes": [...], "round"}, ...]}``;
            ``{"withheld": []}`` when nothing was withheld.

        Raises:
            HTTPException(404): When the run does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        return {"withheld": build_withheld_disclosure(run_id, active_db)}

    @app.get("/runs/{run_id}/claims/{claim_id}/history")
    def get_claim_history(run_id: str, claim_id: str) -> dict[str, Any]:
        """Return the full version history for a single claim, oldest first.

        This powers the QA Replay view's before/after (pass-1 weak vs pass-2
        strong) comparison. Every persisted version of the claim is returned —
        revisions supersede by version, so the list shows how a claim's
        evidence_strength and statement evolved across QA rounds.

        Raises:
            HTTPException(404): When the run does not exist, or no claim with
                ``claim_id`` exists in that run.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        rows = active_db.claim_versions(run_id, claim_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Claim not found")

        versions: list[dict[str, Any]] = []
        for claim in rows:
            try:
                value = json.loads(claim.get("value_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                value = {}
            try:
                evidence_source_ids = _evidence_source_ids(
                    json.loads(claim.get("evidence_json") or "[]")
                )
            except (json.JSONDecodeError, TypeError):
                evidence_source_ids = []
            versions.append(
                {
                    "id": claim.get("id"),
                    "competitor": claim.get("competitor"),
                    "schema_field": claim.get("schema_field"),
                    "statement": claim.get("statement", ""),
                    "evidence_strength": claim.get("evidence_strength"),
                    "status": claim.get("status"),
                    "value": value,
                    "evidence_source_ids": evidence_source_ids,
                    "version": claim.get("version"),
                    "produced_by": claim.get("produced_by"),
                    "note": claim.get("note"),
                }
            )
        return {"claim_id": claim_id, "versions": versions}

    @app.get("/runs/{run_id}/llm_calls")
    def get_llm_calls(run_id: str) -> dict[str, Any]:
        """Return all LLM call records for a run, with secrets already redacted.

        Each call record carries the messages/prompt (as a parsed list), the
        model output text, and the token usage figures. API keys are redacted at
        write time by ``trace.log_llm``; this endpoint returns exactly what is
        stored in the database — no further scrubbing is applied.

        Args:
            run_id: The run identifier.

        Returns:
            ``{"calls": [...]}`` where each item has:
            ``id``, ``agent``, ``model``, ``prompt_json``, ``output_text``,
            ``prompt_tokens``, ``completion_tokens``, ``total_tokens``,
            ``created_at``.

        Raises:
            HTTPException(404): When the run does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        rows = active_db.llm_calls_for_run(run_id)
        calls: list[dict[str, Any]] = []
        for row in rows:
            calls.append(
                {
                    "id": row.get("id"),
                    "agent": row.get("agent"),
                    "model": row.get("model"),
                    "prompt_json": row.get("prompt_json"),
                    "output_text": row.get("output_text"),
                    "prompt_tokens": row.get("prompt_tokens"),
                    "completion_tokens": row.get("completion_tokens"),
                    "total_tokens": row.get("total_tokens"),
                    "created_at": row.get("created_at"),
                }
            )
        return {"calls": calls}

    @app.get("/sources/{source_id}")
    def get_source(source_id: str) -> dict[str, Any]:
        """Return source provenance and raw content.

        Raises:
            HTTPException(404): When the source is not found.
        """
        active_db = _get_db()
        row = active_db.get_source(source_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Source not found")
        return {
            "id": row.get("id"),
            "url": row.get("url"),
            "source_mode": row.get("source_mode"),
            "source_type": row.get("source_type"),
            "fetched_at": row.get("fetched_at"),
            "raw_text": row.get("raw_text"),
            "content_hash": row.get("content_hash"),
        }

    @app.post("/runs/{run_id}/survey/import", status_code=201)
    def import_survey(run_id: str, body: SurveyImportRequest) -> dict[str, Any]:
        """Ingest REAL survey responses for a run (问卷调研 entry point).

        The door to ``ingest.ingest_survey``: responses are PII-scrubbed
        (email/phone/ID redaction + respondent_meta anonymization) and
        persisted as ``source_type="survey"`` / ``source_mode="INGESTED"``
        rows whose ``survey:<id>/r<n>`` locators collapse to ONE independent
        "survey" domain voice for the scorer. Unlike the SIMULATED fixture
        lane, INGESTED rows keep authoritative scoring weight — real research
        data earns the lift that synthetic demo data is denied. The import is
        recorded as a ``survey_ingested`` trace event (audit chain).
        """
        from .ingest import ingest_survey

        active_db = _get_db()
        if active_db.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        # Strict SurveyResponseItem validation already rejected malformed
        # payloads with 422 BEFORE this point — the ingest loop below can no
        # longer fail on shape, so no partial unaudited batch is possible.
        source_ids = ingest_survey(
            active_db,
            run_id,
            [r.model_dump(exclude_none=True) for r in body.responses],
            survey_id=body.survey_id,
        )
        active_db.insert_trace_event(
            {
                "run_id": run_id,
                "agent": "collector",
                "node": "collect",
                "event_type": "survey_ingested",
                "payload_json": json.dumps(
                    {
                        "survey_id": body.survey_id,
                        "count": len(source_ids),
                        "source_ids": source_ids,
                    },
                    ensure_ascii=False,
                ),
            }
        )
        return {"survey_id": body.survey_id, "count": len(source_ids), "source_ids": source_ids}

    @app.post("/runs/{run_id}/claims/{claim_id}/correct", status_code=201)
    def correct_claim(
        run_id: str, claim_id: str, body: ClaimCorrectionRequest
    ) -> dict[str, Any]:
        """Apply a human override to a claim (accept / reject / edit).

        The correction is appended as a new version row — the existing rows are
        never mutated so the full audit trail and the weak→strong history are
        preserved. The new row always carries ``produced_by="human:correction"``
        so a metrics endpoint can later compute the 人工修正率.

        Args:
            run_id: The run the claim belongs to.
            claim_id: The logical claim identifier (shared across versions).
            body: A :class:`ClaimCorrectionRequest` specifying the action.

        Returns:
            ``{"claim_id", "version", "status", "produced_by"}`` with HTTP 201.

        Raises:
            HTTPException(404): When the run or claim does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")

        # Build ONLY the delta — never read the latest content here. The fresh
        # latest row is read and the delta overlaid atomically inside
        # ``append_superseding_claim`` (single _WRITE_LOCK), so concurrent
        # corrections see each other's committed content (no stale-read clobber).
        updates: dict[str, Any] = {
            "produced_by": "human:correction",
            # Reviewer rationale on THIS version (advisory HITL audit trail). Not
            # carried forward: a later correction without a note leaves it NULL.
            # Never an input to scoring/QA.
            "note": body.note,
        }

        if body.action == "accept":
            updates["status"] = "pass"
        elif body.action == "reject":
            updates["status"] = "rejected"
        else:  # edit
            updates["status"] = "pass"
            if body.statement is not None:
                updates["statement"] = body.statement
            if body.value is not None:
                updates["value_json"] = to_json(body.value)

        try:
            new_version = active_db.append_superseding_claim(
                run_id, claim_id, updates
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Claim not found") from exc

        return {
            "claim_id": claim_id,
            "version": new_version,
            "status": updates["status"],
            "produced_by": "human:correction",
            "note": body.note,
        }

    @app.get("/runs/{run_id}/metrics")
    def get_metrics(run_id: str) -> dict[str, Any]:
        """Return business-loop KPI metrics for a run.

        Metrics are computed on-the-fly from persisted DB rows — no gold
        labels required. The ``accuracy_caveat`` key in the response reminds
        callers that ``strong_rate`` is a necessary-not-sufficient proxy for
        factual accuracy.

        Args:
            run_id: The run identifier.

        Returns:
            A dict with keys ``coverage``, ``citation_rate``, ``strong_rate``,
            ``human_correction_rate``, ``efficiency`` (nested dict with
            ``elapsed_s``, ``source_count``, ``llm_calls``, ``total_tokens``),
            and ``accuracy_caveat``.

        Raises:
            HTTPException(404): When the run does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")

        claims = active_db.latest_claims_for_run(run_id)
        llm_calls_rows = active_db.llm_calls_for_run(run_id)
        sources_rows = active_db.sources_for_run(run_id)
        trace_events_rows = active_db.trace_events_for_run(run_id)
        intake = active_db.get_run(run_id) or {}

        return compute_metrics(
            claims=claims,
            llm_calls=llm_calls_rows,
            sources=sources_rows,
            trace_events=trace_events_rows,
            intake=intake,
        )

    @app.get("/runs/{run_id}/credibility")
    def get_credibility(run_id: str) -> dict[str, Any]:
        """Credibility KPI panel for a run (ADVISORY — display/KPI only).

        Returns avg_groundedness, claim_admission_rate, coverage, repair_delta,
        and rounds, plus the advisory admission-waterfall counts
        (proposed_claims, admitted_claims, withheld_claims) and coverage-gap
        field names (covered_fields, uncovered_fields — names only, bounded to
        the run's required schema fields). These numbers never change any verdict
        or route decision; they surface the quantified credibility the
        deterministic loop produced.

        Raises:
            HTTPException(404): When the run does not exist.
        """
        active_db = _get_db()
        if not active_db.run_exists(run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        from .qa.credibility import credibility_panel

        panel = credibility_panel(**load_credibility_inputs(active_db, run_id))
        # Terminal-state signal for the frontend's zero-admitted honesty gate:
        # an in-flight run legitimately reports PRE-FINAL ZEROS (claims are only
        # promoted to pass at the write node), and that transient must never be
        # presented as a settled "0 条结论准入" verdict.
        run_row = active_db.get_run(run_id)
        panel["run_status"] = (run_row or {}).get("status")
        return panel

    @app.get("/schemas")
    def list_schema_domains() -> dict[str, Any]:
        """List available schema domains and the currently active one.

        Returns:
            ``{"domains": [...], "active": "<domain>"}`` where ``domains`` is
            sorted with ``"default"`` first.
        """
        return {"domains": list_domains(), "active": resolved_active_domain()}

    @app.get("/schemas/{domain}")
    def get_schema_domain(domain: str) -> dict[str, Any]:
        """Return the field-schema dict for the requested domain.

        Args:
            domain: Domain name (e.g. ``"default"``, ``"ai_agent"``, ``"hr"``).

        Returns:
            ``{"domain": name, "fields": {...}, "source_weights": {...}}`` where
            ``fields`` maps each field name to its ``required`` / ``sub_fields``
            spec, and ``source_weights`` is ADVISORY display metadata (the
            domain's source-type → Admiralty reliability-letter map + the
            built-in fallback). The source-weights block never affects scoring —
            the 3-tier scorer is independent of Admiralty letters.

        Raises:
            HTTPException(404): When the domain file doesn't exist.
        """
        try:
            fields = load_domain(domain)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "domain": domain,
            "fields": fields,
            "source_weights": _source_weights_view(domain),
        }

    return app


# ---------------------------------------------------------------------------
# Module-level app for ``uvicorn mingjing.api:app``
# ---------------------------------------------------------------------------

app = create_app(wire_default_executor=True)
