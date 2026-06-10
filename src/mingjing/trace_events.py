"""Emit-helper wrappers for the rich trace-event vocabulary.

These thin functions wrap :func:`mingjing.trace.log_event` with the exact
``event_type`` tokens the frontend understands (see ``frontend/src/lib/trace.ts``).
All helpers are no-ops when ``db`` or ``run_id`` are absent so the compile/test
path without a real DB remains clean.

Vocabulary emitted here:
  collect_start, collect_done
  analyze_start, analyze_done
  qa_pass, qa_fail
  revise_start, revise_done
  run_partial, run_complete
  synthesis_done, synthesis_empty
  run_error
"""

from typing import Any

from .trace import log_event


def emit_collect_start(
    db: Any,
    run_id: str | None,
    *,
    competitor: str,
    field: str,
    round_idx: int,
) -> None:
    """Emit ``collect_start`` before fetching for a (competitor, field) task."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="collector",
        node="collect",
        event_type="collect_start",
        payload={"competitor": competitor, "field": field, "round": round_idx},
    )


def emit_collect_done(
    db: Any,
    run_id: str | None,
    *,
    competitor: str,
    field: str,
    sources_added: int,
    round_idx: int,
) -> None:
    """Emit ``collect_done`` after fetching for a (competitor, field) task."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="collector",
        node="collect",
        event_type="collect_done",
        payload={
            "competitor": competitor,
            "field": field,
            "sources_added": sources_added,
            "round": round_idx,
        },
    )


def emit_analyze_start(
    db: Any,
    run_id: str | None,
    *,
    competitor: str,
    field: str,
) -> None:
    """Emit ``analyze_start`` before the analyst processes a task."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="analyst",
        node="analyze",
        event_type="analyze_start",
        payload={"competitor": competitor, "field": field},
    )


def emit_analyze_done(
    db: Any,
    run_id: str | None,
    *,
    competitor: str,
    field: str,
    claim_id: str,
    evidence_strength: str,
) -> None:
    """Emit ``analyze_done`` after the analyst produces a claim."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="analyst",
        node="analyze",
        event_type="analyze_done",
        payload={
            "competitor": competitor,
            "field": field,
            "claim_id": claim_id,
            "evidence_strength": evidence_strength,
        },
    )


def emit_qa_verdict(
    db: Any,
    run_id: str | None,
    *,
    verdict: str,
    latest_claims: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    round_idx: int,
) -> None:
    """Emit per-round QA verdict events: ``qa_pass`` and/or ``qa_fail``.

    ``qa_pass`` carries the ids of claims with NO per-claim issue THIS round —
    emitted even when the run-level verdict is ``reject`` (mixed outcome: some
    claims pass while others are sent back; run-level issues like LOW_COVERAGE
    have no claim_id and do not flag individual claims — matching the write
    node's promotion semantics). Previously qa_pass only fired on an all-clean
    round, which never happens in a run with withheld claims, so the audit
    trail recorded only rejections and a judge asking "show me one claim's
    affirmative verdict" had nothing to point at. Pure observability: routing
    and adjudication read ``verdict``/``issues``, never these events.
    """
    if db is None or not run_id:
        return
    flagged_ids = {i.get("claim_id") for i in issues if i.get("claim_id")}
    passed_ids = [c["id"] for c in latest_claims if c.get("id") and c["id"] not in flagged_ids]
    if passed_ids:
        log_event(
            db,
            run_id,
            agent="qa",
            node="qa",
            event_type="qa_pass",
            payload={"claim_ids": passed_ids, "round": round_idx},
        )
    if verdict != "pass":
        for issue in issues:
            reason = issue.get("detail") or issue.get("code") or "qa_issue"
            log_event(
                db,
                run_id,
                agent="qa",
                node="qa",
                event_type="qa_fail",
                payload={
                    "claim_id": issue.get("claim_id"),
                    "reason": reason,
                    "code": issue.get("code"),
                    "round": round_idx,
                    # Carry Issue.meta (e.g. contradiction supports/refutes
                    # domains) so the frontend ContradictionCard can render it.
                    "meta": issue.get("meta") or {},
                },
            )


def emit_revise_start(
    db: Any,
    run_id: str | None,
    *,
    assignee: str | None,
    round_idx: int,
    claim_id: str | None,
) -> None:
    """Emit ``revise_start`` when entering the revise node."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent=assignee or "collector",
        node="revise",
        event_type="revise_start",
        payload={"assignee": assignee, "round": round_idx, "claim_id": claim_id},
    )


def emit_revise_done(
    db: Any,
    run_id: str | None,
    *,
    round_idx: int,
) -> None:
    """Emit ``revise_done`` at the start of the subsequent QA node."""
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="qa",
        node="qa",
        event_type="revise_done",
        payload={"round": round_idx},
    )


def emit_run_terminal(
    db: Any,
    run_id: str | None,
    *,
    is_partial: bool,
    latest_claims: list[dict[str, Any]],
) -> None:
    """Emit ``run_complete`` or ``run_partial`` at the start of the write node."""
    if db is None or not run_id:
        return
    strength_counts: dict[str, int] = {"strong": 0, "moderate": 0, "weak": 0}
    for c in latest_claims:
        s = c.get("evidence_strength", "weak")
        strength_counts[s] = strength_counts.get(s, 0) + 1
    log_event(
        db,
        run_id,
        agent="writer",
        node="write",
        event_type="run_partial" if is_partial else "run_complete",
        payload={
            "claims_total": len(latest_claims),
            "strong": strength_counts.get("strong", 0),
            "moderate": strength_counts.get("moderate", 0),
            "weak": strength_counts.get("weak", 0),
        },
    )


def emit_synthesis_done(
    db: Any,
    run_id: str | None,
    *,
    sentences: int,
) -> None:
    """Emit ``synthesis_done`` ONLY when a real (non-empty) brief was produced.

    Carries ``{"sentences": N}`` (N > 0 by contract) so a consumer can see how
    much synthesis was actually written. Callers MUST route the empty case to
    :func:`emit_synthesis_empty` instead — firing ``synthesis_done`` on an empty
    synthesis is a false positive (reads as "a brief was produced" when none was).
    """
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="synthesis",
        node="synthesis",
        event_type="synthesis_done",
        payload={"sentences": sentences},
    )


def emit_synthesis_empty(
    db: Any,
    run_id: str | None,
) -> None:
    """Emit ``synthesis_empty`` when synthesis ran but produced no brief.

    Empty is a legitimate honest outcome (too few claims passed, or the LLM
    failed / returned unparseable JSON and ``run_synthesis`` fell back to the
    deterministic ledger). This distinct event lets the trace label that state
    honestly instead of misrepresenting it as a completed ``synthesis_done``.
    """
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="synthesis",
        node="synthesis",
        event_type="synthesis_empty",
        payload={"sentences": 0},
    )


def emit_run_error(
    db: Any,
    run_id: str | None,
    *,
    message: str,
) -> None:
    """Emit ``run_error`` as the terminal event when a run fails hard.

    Without this terminal event the frontend report keeps polling/spinning
    forever, since no ``run_complete`` / ``run_partial`` is ever written on a
    hard failure. The ``message`` is a concise, human-readable summary only —
    callers MUST NOT pass raw stack traces or anything carrying secrets.
    """
    if db is None or not run_id:
        return
    log_event(
        db,
        run_id,
        agent="writer",
        node="write",
        event_type="run_error",
        payload={"message": message},
    )
