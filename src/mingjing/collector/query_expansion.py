"""LLM-driven query expansion for deep-collect.

Expands a single base search query into *n* targeted sub-queries by asking an
injected LLM callable.  All failures are non-fatal: any exception from the LLM
falls back to ``[base_query]``.  An optional in-memory cache avoids redundant
LLM calls within the same run.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Matches leading list markers such as "1.", "-", "*", "1)", etc.
_LIST_MARKER_RE = re.compile(r"^\s*(?:\d+[.)]\s*|[-*]\s*)")


def _build_prompt(competitor: str, field: str, base_query: str, n: int) -> str:
    """Return the prompt sent to the LLM.

    ``base_query`` is the actual research topic and is ALWAYS included — it is the
    only reliable signal in the production path, where ``collect_fn`` carries no
    competitor/field and the closure passes them empty. ``competitor``/``field``
    are added as optional context only when present.
    """
    context = ""
    if competitor or field:
        context = f" (company: '{competitor}', dimension: '{field}')"
    return (
        f"You are a competitive-intelligence research assistant.\n"
        f"Generate {n} distinct, specific web-search queries that expand and refine "
        f"this research query: '{base_query}'{context}.\n"
        f"Maximize source coverage by spreading the queries across different angles:\n"
        f"- the company's OWN site (official pricing / docs / product pages)\n"
        f"- independent third-party reviews (e.g. G2, Capterra, Reddit, 知乎, 少数派)\n"
        f"- news, comparisons, and 'X vs competitor' articles\n"
        f"Write some queries in English and some in Chinese (简体中文) so both "
        f"international and Chinese-language sources are reached.\n"
        f"Output exactly one query per line with no numbering, bullets, or extra prose."
    )


def _parse_lines(raw: str, n: int, base_query: str) -> list[str]:
    """Parse raw LLM output into a deduplicated, capped list of query strings.

    Returns ``[base_query]`` if parsing yields nothing.
    """
    seen: set[str] = set()
    result: list[str] = []

    for line in raw.splitlines():
        # Strip leading list markers then whitespace
        cleaned = _LIST_MARKER_RE.sub("", line).strip()
        if not cleaned:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
        if len(result) >= n:
            break

    return result if result else [base_query]


def expand_queries(
    competitor: str,
    field: str,
    base_query: str,
    n: int,
    *,
    llm: Callable[[str], str],
    cache: dict | None = None,
    run_id: str = "",
) -> list[str]:
    """Expand *base_query* into up to *n* targeted sub-queries via *llm*.

    Parameters
    ----------
    competitor:
        Name of the company being researched.
    field:
        Research dimension (e.g. "pricing", "market share").
    base_query:
        Fallback query; always guaranteed to appear in an empty result.
    n:
        Maximum number of queries to return (≥ 1).
    llm:
        Injected callable ``(prompt: str) -> str``.  Must be safe to call
        synchronously.  Any exception is caught and triggers fallback.
    cache:
        Optional ``dict`` for in-memory memoisation keyed by
        ``(run_id, competitor, field, base_query)``.  ``base_query`` MUST be part
        of the key: the production closure passes a constant empty
        competitor/field for every task, so without ``base_query`` every field's
        expansion would collide and later tasks would reuse the first task's
        sub-queries.  Pass ``None`` to disable caching.
    run_id:
        Opaque identifier for the current pipeline run; used as part of the
        cache key so different runs start fresh.

    Returns
    -------
    list[str]
        Non-empty list of search query strings (length ≤ *n*).
    """
    cache_key = (run_id, competitor, field, base_query)

    if cache is not None and cache_key in cache:
        return cache[cache_key]

    prompt = _build_prompt(competitor, field, base_query, n)

    try:
        raw = llm(prompt)
    except Exception:  # noqa: BLE001
        logger.warning(
            "expand_queries: LLM call failed for competitor=%r field=%r; "
            "falling back to base_query",
            competitor,
            field,
            exc_info=True,
        )
        return [base_query]

    queries = _parse_lines(raw, n, base_query)

    if cache is not None:
        cache[cache_key] = queries

    return queries
