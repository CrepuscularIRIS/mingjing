"""Load a curated source corpus and build a deterministic ``collect_fn``.

The corpus JSON is competitor-scoped: ``{"competitor": str, "fields": {field: [src, ...]}}``.
Sources are ordered weak-first per field so that ``source_cap = 1 + revision_round``
yields a thin source in round 0 and adds a strong source in round 1.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..graph_nodes import build_query

logger = logging.getLogger(__name__)


def corpus_key(competitor: str, field: str) -> str:
    """Return the exact query string the plan node will emit for this pair."""
    return build_query(competitor, field)


def load_corpus(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a competitor manifest into a query-keyed corpus.

    Returns a dict mapping ``build_query(competitor, field)`` to
    ``{"competitor": str, "field": str, "sources": list[dict]}``.

    Raises:
        FileNotFoundError: when ``path`` does not exist.
        ValueError: when the manifest is missing ``competitor`` or ``fields``.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"corpus manifest {p} must be a JSON object")
    competitor = data.get("competitor")
    fields = data.get("fields")
    if not competitor or not isinstance(fields, dict):
        raise ValueError(f"corpus manifest {p} must have 'competitor' and 'fields'")
    corpus: dict[str, dict[str, Any]] = {}
    for field, sources in fields.items():
        if not isinstance(sources, list):
            raise ValueError(
                f"corpus manifest {p}: field '{field}' must map to a list of sources"
            )
        corpus[corpus_key(competitor, field)] = {
            "competitor": competitor,
            "field": field,
            "sources": list(sources),
        }
    return corpus


def make_demo_collect_fn(
    corpus: dict[str, dict[str, Any]],
) -> Callable[..., list[dict[str, Any]]]:
    """Build a deterministic ``collect_fn`` over a query-keyed ``corpus``.

    The returned callable matches the signature the collect node invokes:
    ``fn(query, *, cache, source_cap, mode)``. It returns the first ``source_cap``
    sources for the matching query (weak-first ordering), each shaped exactly as
    the collect node expects (``fetched``/``url``/``text``/``title``/``source_mode``/
    ``fetched_at``/``content_hash``). Unknown queries return ``[]`` (the run then
    skips that field — same as a live miss).
    """

    def collect(
        query: str,
        *,
        cache: Any = None,
        source_cap: int = 1,
        mode: str = "cache_first",
    ) -> list[dict[str, Any]]:
        entry = corpus.get(query)
        if entry is None:
            logger.warning("demo corpus miss for query=%r", query)
            return []
        out: list[dict[str, Any]] = []
        for src in entry["sources"][: max(source_cap, 0)]:
            text = src.get("text", "")
            out.append(
                {
                    "fetched": True,
                    "url": src.get("url", ""),
                    "title": src.get("title"),
                    "text": text,
                    "source_mode": "CACHED",
                    "fetched_at": time.time(),
                    # Match FetchResult's content_hash convention so demo source
                    # rows are consistent with live ones.
                    "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                }
            )
        return out

    return collect
