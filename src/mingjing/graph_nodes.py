"""Live graph node builders (Task 15b).

These factory functions return the node callables wired into the live graph by
:func:`mingjing.graph.build_graph`. Each node CLOSES OVER an injected
:class:`~mingjing.graph.GraphDeps` (agents, cache, settings) so the graph state
stays field-keyed/serializable while the agents remain dependency-injected for
offline testing.

The honest weak->strong self-correction lives in the collect node: the per-field
source cap is ``1 + revision_round`` so a later round performs a *real additional
fetch* rather than withholding data. A claim the analyst cannot corroborate with
a cited source scores weak/moderate via the transparent :func:`scoring.strength`,
QA flags it, and the next round fetches more — until enough independent,
authoritative evidence makes the claim strong.

Claim-assembly / persistence helpers (build_claim, infer_source_type, ...) live
in :mod:`mingjing.claim_builder`; the trace helper lives in :mod:`mingjing.trace`
(``node_trace``). Rich lifecycle emit-helpers live in :mod:`mingjing.trace_events`.
Both are imported at module top — there is NO import cycle with ``graph.py``
(this module imports neither it nor anything that imports it).
"""

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from . import claim_builder
from .agents import qa as qa_agent
from .agents import writer as writer_agent
from .text_safety import sanitize_entity_name
from .trace import log_event, node_trace
from .trace_events import (
    emit_analyze_done,
    emit_analyze_start,
    emit_collect_done,
    emit_collect_start,
    emit_qa_verdict,
    emit_revise_done,
    emit_run_terminal,
    emit_synthesis_done,
    emit_synthesis_empty,
)

if TYPE_CHECKING:
    from .graph import GraphDeps, RunState

logger = logging.getLogger(__name__)

# Per-field search-query templates: the raw schema field name (e.g.
# "user_sentiment") is a poor search term that matches a vendor's own template
# pages; these natural-language templates steer discovery toward authoritative
# third-party sources (reviews, pricing pages, feature lists).
FIELD_QUERY_TEMPLATES: dict[str, str] = {
    "pricing_model": "{competitor} pricing plans cost per month",
    "user_sentiment": "{competitor} reviews pros and cons",
    "feature_tree": "{competitor} features list overview",
    "user_persona": "{competitor} who is it for target users",
    "swot": "{competitor} strengths and weaknesses review",
}


def build_query(competitor: str, field: str) -> str:
    """Build the discovery query for a (competitor, field).

    Uses a field-specific natural-language template when available so search
    engines surface authoritative third-party pages rather than the vendor's
    own template/landing pages; falls back to ``"{competitor} {field}"``.
    """
    # Sanitize at the trust boundary — a Discovery-Mode competitor name can come
    # from an attacker-influenceable search result (see text_safety).
    competitor = sanitize_entity_name(competitor)
    template = FIELD_QUERY_TEMPLATES.get(field)
    if template:
        return template.format(competitor=competitor).strip()
    return f"{competitor} {field}".strip()


def live_plan_node(state: "RunState") -> dict[str, Any]:
    """Expand the intake into one research task per (competitor x field).

    Kept as a plain node (not a ``make_*_node`` factory) because planning closes
    over no ``deps`` — it reads only the field-keyed state. The ``live_`` prefix
    distinguishes it from the compile-only ``graph.plan_node`` skeleton.
    """
    node_trace(state, "plan")
    intake = state.get("intake", {}) or {}
    competitors = intake.get("competitors", []) or []
    fields = intake.get("fields", []) or []
    tasks = [
        {"field": fld, "competitor": comp, "query": build_query(comp, fld)}
        for comp in competitors
        for fld in fields
    ]
    return {"tasks": tasks, "phase": "plan"}


def make_collect_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the live collect node closing over ``deps``."""

    def collect(state: "RunState") -> dict[str, Any]:
        """Fetch evidence per task with a round-aware cap that grows each round.

        ``source_cap = 1 + revision_round`` — round 0 fetches a single source
        (thin), round 1 fetches two (a real additional fetch). Each fetched
        source is persisted (``append_source``) with an inferred ``source_type``
        and an evidence chunk (``append_evidence_chunk``).
        """
        node_trace(state, "collect", agent="collector")
        db = state["db"]
        run_id = state["run_id"]
        round_idx = state.get("revision_round", 0)
        source_cap = 1 + round_idx
        mode = getattr(deps.settings, "mode", "live_first") if deps.settings else "live_first"
        # JS-rendered SPA pages (feishu.cn, larksuite.com) fetch HTTP 200 but
        # extract to a ~8-char loading shell. Such shells are not groundable, so
        # the QA gate rejects every claim that cites them. Drop them here (with a
        # source_skipped trace) so the analyst grounds against the content-rich
        # third-party sources collected alongside them.
        #
        # The floor is policy carried on Settings (production = 100 chars). The
        # offline smoke gate injects settings=None (or a fake lacking the field)
        # and is intentionally NOT gated — its deterministic fixtures use short
        # text by design; a missing/None setting therefore means "no gate" (0).
        min_chars = getattr(deps.settings, "min_source_chars", 0) if deps.settings is not None else 0

        new_sources: list[dict[str, Any]] = []
        for task in state.get("tasks", []):
            competitor = task.get("competitor", "")
            field = task.get("field", "")
            emit_collect_start(db, run_id, competitor=competitor, field=field, round_idx=round_idx)
            results = deps.collect_fn(
                task.get("query", ""),
                cache=deps.cache,
                source_cap=source_cap,
                mode=mode,
            )
            task_sources = 0
            for res in results:
                if not res.get("fetched"):
                    continue
                text = res.get("text", "")
                # Gate near-empty FETCHES (SPA shells) before they become citable.
                # Snippet-as-evidence rows (from_snippet) are legitimately short —
                # the search summary IS the evidence — so they bypass the floor.
                if not res.get("from_snippet") and len((text or "").strip()) < min_chars:
                    log_event(
                        db,
                        run_id,
                        agent="collector",
                        node="collect",
                        event_type="source_skipped",
                        payload={
                            "reason": "content_too_thin",
                            "url": res.get("url", ""),
                            "chars": len((text or "").strip()),
                            "min_chars": min_chars,
                            "competitor": competitor,
                            "field": field,
                        },
                    )
                    continue
                # Invariant: every persisted fetch is a NEW evidence acquisition,
                # so it gets a FRESH uuid4 source id regardless of any id the
                # collector echoes back. A re-collected task in round 2 therefore
                # can never collide with a round-1 row on the sources.id PRIMARY
                # KEY (the DB bypasses Pydantic, so a dup id would raise
                # IntegrityError mid-run).
                source_id = str(uuid.uuid4())
                url = res.get("url", "")
                db.append_source(
                    {
                        "id": source_id,
                        "run_id": run_id,
                        "url": url,
                        "title": res.get("title"),
                        "source_type": claim_builder.infer_source_type(url, competitor),
                        "source_mode": res.get("source_mode"),
                        "fetched_at": res.get("fetched_at"),
                        "content_hash": res.get("content_hash"),
                        "raw_text": text,
                    }
                )
                db.append_evidence_chunk(
                    {
                        "id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "source_id": source_id,
                        "locator": url,
                        "text": text,
                        "content_hash": res.get("content_hash"),
                    }
                )
                new_sources.append(
                    {
                        "source_id": source_id,
                        "field": field,
                        "competitor": competitor,
                    }
                )
                task_sources += 1
            emit_collect_done(
                db, run_id,
                competitor=competitor, field=field,
                sources_added=task_sources, round_idx=round_idx,
            )
        return {
            "sources": new_sources,
            "phase": "collect",
            "budget_calls": state.get("budget_calls", 0) + 1,
        }

    return collect


def make_analyze_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the live analyze node closing over ``deps``."""

    def analyze(state: "RunState") -> dict[str, Any]:
        """Turn collected sources into one claim per task via ``analyze_fn``.

        Guards a defective analyst payload: the live LLM path can yield ``None``
        or a non-dict / empty dict. Such a payload is logged, a trace event
        records the skipped field, and the task is skipped WITHOUT persisting a
        zero-evidence claim — the DB bypasses Pydantic, so a bad row would
        otherwise reach QA. The run still advances to ``write``.
        """
        node_trace(state, "analyze", agent="analyst")
        db = state["db"]
        run_id = state["run_id"]

        new_claims: list[dict[str, Any]] = []
        calls_made = 0
        for task in state.get("tasks", []):
            field_name = task.get("field", "")
            competitor = task.get("competitor", "")
            emit_analyze_start(db, run_id, competitor=competitor, field=field_name)
            src_ids = [
                s["source_id"]
                for s in state.get("sources", [])
                if s.get("field") == field_name and s.get("competitor") == competitor
            ]
            src_rows = [db.get_source(sid) for sid in src_ids]
            src_rows = [r for r in src_rows if r is not None]
            if not src_rows:
                continue
            # Label each block with its source id so the model can cite it in
            # ``evidence_ref``; otherwise filter_evidence_refs drops every ref
            # (the ids never appear in the text the model saw) and all evidence
            # collapses to weak. The labeled text stays untrusted_content so the
            # prompt-injection envelope still applies.
            evidence_text = "\n\n".join(
                f"[source_id: {r['id']}]\n{r.get('raw_text') or ''}" for r in src_rows
            )
            calls_made += 1
            try:
                payload = deps.analyze_fn(
                    db,
                    run_id,
                    field=field_name,
                    competitor=competitor,
                    evidence_text=evidence_text,
                    source_ids={r["id"] for r in src_rows},
                    settings=deps.settings,
                )
            except Exception as exc:  # noqa: BLE001
                _log_skipped_field_exc(db, run_id, field_name, competitor, exc)
                continue
            if not isinstance(payload, dict) or not payload:
                _log_skipped_field(db, run_id, field_name, competitor, payload)
                continue
            claim = claim_builder.build_claim(db, run_id, task, src_rows, payload)
            db.append_claim(claim)
            new_claims.append(claim)
            emit_analyze_done(
                db, run_id,
                competitor=competitor, field=field_name,
                claim_id=claim["id"], evidence_strength=claim["evidence_strength"],
            )

        return {
            "claims": new_claims,
            "phase": "analyze",
            "budget_calls": state.get("budget_calls", 0) + calls_made,
        }

    return analyze


def _log_skipped_field(
    db: Any, run_id: str, field_name: str, competitor: str, payload: Any
) -> None:
    """Warn + trace a skipped field when the analyst returned a bad payload."""
    logger.warning(
        "analyst returned non-dict/empty payload for (%s, %s); skipping claim (type=%s)",
        competitor,
        field_name,
        type(payload).__name__,
    )
    if db is not None and run_id:
        log_event(
            db,
            run_id,
            agent="analyst",
            node="analyze",
            event_type="claim_skipped",
            payload={
                "field": field_name,
                "competitor": competitor,
                "reason": "analyst_payload_not_a_dict_or_empty",
            },
        )


def _log_skipped_field_exc(
    db: Any, run_id: str, field_name: str, competitor: str, exc: BaseException
) -> None:
    """Warn + trace a skipped field when ``analyze_fn`` raised an exception.

    Records a ``claim_skipped`` trace event with a reason string of the form
    ``analyst_call_raised:<ExceptionType>`` so the exception type is observable
    without letting the exception propagate and crash the run.
    """
    exc_type = type(exc).__name__
    logger.warning(
        "analyze_fn raised %s for (%s, %s); skipping field: %s",
        exc_type,
        competitor,
        field_name,
        exc,
    )
    if db is not None and run_id:
        log_event(
            db,
            run_id,
            agent="analyst",
            node="analyze",
            event_type="claim_skipped",
            payload={
                "field": field_name,
                "competitor": competitor,
                "reason": f"analyst_call_raised:{exc_type}",
            },
        )


def make_qa_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the live qa node closing over ``deps``."""

    def qa(state: "RunState") -> dict[str, Any]:
        """Build the claimset from the latest claims, run QA, persist reports.

        Recomputes ``budget_ok`` (mirroring ``route_node``) and sets ``verdict``
        plus an ``assignee`` (from the first revision task) so the router can
        dispatch the redo.

        When entering a subsequent QA round (revision_round > 0) this node also
        emits ``revise_done`` so the frontend's revising-set clears before the
        new verdict lands.
        """
        node_trace(state, "qa", agent="qa")
        db = state["db"]
        run_id = state["run_id"]
        round_idx = state.get("revision_round", 0)

        # If we're re-entering QA after a revision, mark the revision as done.
        if round_idx > 0:
            emit_revise_done(db, run_id, round_idx=round_idx)

        latest = db.latest_claims_for_run(run_id)
        claims, sources = claim_builder.claimset_parts(db, latest)
        intake = state.get("intake", {}) or {}
        required = intake.get("fields", []) or []
        covered = sorted({c["schema_field"] for c in claims})
        claimset = {
            "claims": claims,
            "sources": sources,
            "coverage": {"required_fields": required, "covered_fields": covered},
        }

        result = qa_agent.review(claimset, run_id=run_id, round=round_idx)

        for claim in latest:
            db.append_qc_report(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "claim_id": claim["id"],
                    "round": round_idx,
                    "verdict": result["verdict"],
                    "issues_json": claim_builder.to_json(
                        [i["code"] for i in result["issues"] if i.get("claim_id") == claim["id"]]
                    ),
                }
            )
        for task in result["revision_tasks"]:
            db.append_revision_task(task)

        assignee = result["revision_tasks"][0]["assignee"] if result["revision_tasks"] else None
        budget_calls = state.get("budget_calls", 0)
        budget_max = state.get("budget_max", 40)

        # Emit per-verdict trace events so the frontend self-correction cues light up.
        emit_qa_verdict(
            db, run_id,
            verdict=result["verdict"], latest_claims=latest,
            issues=result["issues"], round_idx=round_idx,
        )

        return {
            "verdict": result["verdict"],
            "assignee": assignee,
            "qc_reports": result["issues"],
            "budget_ok": budget_calls < budget_max,
            "phase": "qa",
        }

    return qa


def make_write_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the live write node closing over ``deps``."""

    def write(state: "RunState") -> dict[str, Any]:
        """Project QA-passed claims into the report via the pure writer.

        On a ``pass`` verdict all latest claims passed; on the partial path
        (reject at cap/budget) only claims NOT flagged by the last QA round are
        passed. The writer drops any referenced id not in the passed set.

        A claim's lifecycle is ``draft`` -> ``pass``: every claim is persisted
        ``draft`` by :func:`claim_builder.build_claim`, and the terminal write
        node promotes each QA-accepted (passed) claim to ``status="pass"`` by
        appending a superseding version (the DB is append-only — see
        :func:`claim_builder.supersede_target`). Flagged/rejected claims on the
        partial path stay ``draft`` (the honest behavior), so the report API's
        ``status == "pass"`` filter surfaces exactly the accepted claims.

        Emits ``run_complete`` on the honest-pass path or ``run_partial`` when
        the loop terminated due to the round cap or budget exhaustion (last
        verdict was ``reject``).
        """
        node_trace(state, "write", agent="writer")
        db = state["db"]
        run_id = state["run_id"]
        latest = db.latest_claims_for_run(run_id)
        is_partial = state.get("verdict", "pass") != "pass"

        if not is_partial:
            passed = latest
        else:
            # Flagged = claims rejected by the LAST QA round (read from the DB,
            # not the additive ``qc_reports`` state field, which accumulates
            # issues across rounds and would wrongly exclude a claim that was
            # flagged early but recovered to strong by the final round).
            flagged = db.flagged_claim_ids_last_round(run_id)
            passed = [c for c in latest if c["id"] not in flagged]

        # Promote each passed claim to status="pass" by appending a superseding
        # version (append-only: never UPDATE). Done BEFORE emit so the terminal
        # tally reflects the final state. Flagged claims remain draft.
        _promote_passed_claims(db, passed)

        report = writer_agent.render_report(
            passed_claims=passed,
            all_referenced_ids=[c["id"] for c in passed],
        )
        emit_run_terminal(
            db, run_id, is_partial=is_partial, latest_claims=db.latest_claims_for_run(run_id)
        )
        return {"report": report.body, "phase": "write"}

    return write


def make_synthesis_node(deps: "GraphDeps") -> Callable[["RunState"], dict[str, Any]]:
    """Build the live synthesis node closing over ``deps``.

    Runs AFTER the write node (write -> synthesis -> END). Emits
    ``synthesis_start`` (always — it genuinely started) around the NON-FATAL
    :func:`mingjing.synthesis.run_synthesis` driver (which itself swallows any
    LLM/projection error and falls back to the deterministic ledger). The
    terminal event is then chosen HONESTLY by reading back the persisted
    synthesis: ``synthesis_done {sentences:N}`` ONLY when a real (non-empty)
    brief was produced, otherwise ``synthesis_empty``. This avoids the false
    positive of a ``synthesis_done`` firing when ``run_synthesis`` produced
    nothing (too few claims passed / LLM failed). This node never breaks the
    run's terminal path.
    """

    def synthesis(state: "RunState") -> dict[str, Any]:
        from .synthesis import brief_sentence_count, run_synthesis

        node_trace(state, "synthesis", agent="synthesis")
        db = state["db"]
        run_id = state["run_id"]
        log_event(db, run_id, agent="synthesis", node="synthesis", event_type="synthesis_start")
        run_synthesis(db, run_id, deps.settings)
        # Read back what was actually persisted and label the terminal event
        # honestly: a non-empty brief -> synthesis_done; nothing -> synthesis_empty.
        sentences = brief_sentence_count(db.get_synthesis(run_id))
        if sentences > 0:
            emit_synthesis_done(db, run_id, sentences=sentences)
        else:
            emit_synthesis_empty(db, run_id)
        return {"phase": "synthesis"}

    return synthesis


_CLAIM_ROW_KEYS = (
    "id",
    "run_id",
    "competitor",
    "schema_field",
    "claim_type",
    "statement",
    "value_json",
    "evidence_json",
    "based_on_json",
    "evidence_strength",
    "status",
    "version",
    "produced_by",
    "created_at",
)


def _promote_passed_claims(db: Any, passed: list[dict[str, Any]]) -> None:
    """Append a ``status="pass"`` superseding version of each passed claim.

    The DB is append-only (claims are never UPDATEd; a higher ``version`` under
    the same ``id`` supersedes — see :func:`claim_builder.supersede_target`).
    Each row dict from :meth:`Database.latest_claims_for_run` already carries the
    exact columns :meth:`Database.append_claim` reads, so we copy those keys
    (ignoring ``rowid_pk``), override ``status`` to ``"pass"`` and bump
    ``version`` by one. ``append_claim`` takes the single-writer ``_WRITE_LOCK``.

    A passed claim already at ``status="pass"`` is idempotently re-promoted to a
    higher version of the same strength, preserving the weak->strong history.
    """
    for claim in passed:
        promoted = {key: claim.get(key) for key in _CLAIM_ROW_KEYS}
        promoted["status"] = "pass"
        promoted["version"] = int(claim.get("version", 1)) + 1
        db.append_claim(promoted)
