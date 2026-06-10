"""Append-only observability log.

``log_event`` writes a ``trace_events`` row (the activity feed / DAG trace);
``log_llm`` writes an ``llm_calls`` row (prompt / output / tokens for the
observability view). Both redact the live ``MINIMAX_API_KEY`` value from any
stored payload before insert, so a secret accidentally threaded into a prompt or
header never lands in the database.
"""

import json
import os
from typing import Any

from .db import Database

_REDACTED = "[REDACTED_API_KEY]"


def _redact(text: str) -> str:
    """Replace the live MiniMax API key value (if set and non-empty) with a marker."""
    key = os.environ.get("MINIMAX_API_KEY", "")
    if key:
        text = text.replace(key, _REDACTED)
    return text


def _redact_json(value: Any) -> str:
    """Serialize ``value`` to JSON with the API key value scrubbed."""
    return _redact(json.dumps(value, default=str, ensure_ascii=False))


def node_trace(state: Any, node: str, agent: str | None = None) -> None:
    """Emit a ``node_enter`` trace event for ``node`` from a graph node.

    Lives here (not in ``graph.py``) so both ``graph.py`` and ``graph_nodes.py``
    import it from ``trace`` — breaking the module-load cycle between them. A
    no-op when no :class:`Database` carrier or ``run_id`` is threaded through the
    state (the compile-only build/test path).
    """
    db = state.get("db")
    run_id = state.get("run_id")
    if db is not None and run_id:
        log_event(
            db,
            run_id,
            agent=agent,
            node=node,
            event_type="node_enter",
            payload={"phase": state.get("phase")},
        )


def log_event(
    db: Database,
    run_id: str,
    *,
    agent: str | None = None,
    node: str | None = None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one trace event. Payload is JSON-serialized with key redaction."""
    db.insert_trace_event(
        {
            "run_id": run_id,
            "agent": agent,
            "node": node,
            "event_type": event_type,
            "payload_json": _redact_json(payload or {}),
        }
    )


def log_llm(
    db: Database,
    run_id: str,
    *,
    agent: str | None = None,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    output_text: str | None = None,
    usage: dict[str, Any] | None = None,
) -> None:
    """Append one LLM call record (prompt, output, token usage) with redaction."""
    usage = usage or {}
    db.insert_llm_call(
        {
            "run_id": run_id,
            "agent": agent,
            "model": model,
            "prompt_json": _redact_json(messages or []),
            "output_text": None if output_text is None else _redact(output_text),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    )
