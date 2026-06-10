"""Blind groundedness score — an ADVISORY credibility signal, never a veto.

This complements (does NOT replace) the deterministic VALUE_UNSUPPORTED gate. The
deterministic gate keeps the only veto power; this score is surfaced as a 0..1
credibility number per claim. It is "blind": it receives ONLY the asserted value
leaves and the cited source text — never the analyst's reasoning, the report
context, or the claim's identity — so it cannot be talked into agreeing.

CONSISTENCY WITH THE DETERMINISTIC GATE
---------------------------------------
The hard gate ``_check_value_unsupported`` in ``rules.py`` decides "supported"
using three notions: which leaves are *checkable* (``_is_checkable_leaf``), how
text is *normalized* (``_normalize_ws`` → collapse-whitespace + ``.lower()``), and
the *substring* containment test. The advisory score below MUST agree with the
gate on what counts as supported, otherwise the credibility number and the veto
would tell two different stories.

We deliberately keep LOCAL copies of the checkable-leaf and whitespace-normalize
logic rather than ``from .rules import _normalize_ws`` because ``rules.py`` pulls
in ``scoring``, ``collector.independence`` and ``schemas`` at import time; this
blind scorer is a self-contained, dependency-free pure function and importing
rules would chain in that whole subtree for two tiny helpers. There is no
circular-import barrier (rules → groundedness has no edge), so this is a
leanness/coupling choice, not a necessity. The local copies are byte-for-byte
behaviour-identical to the gate: checkable ⇔ ≥4 chars (raw-stripped) AND ≥1
alpha; normalize ⇔ collapse whitespace runs to single spaces, strip, lowercase;
support ⇔ normalized leaf is a substring of normalized source text.
"""

import re
from typing import Any

# Matches rules.py ``_WS_RUN`` exactly (collapse-whitespace notion shared with the gate).
_WS = re.compile(r"\s+")


def _leaves(node: Any) -> list[str]:
    """Collect string leaves from a dict/list/str tree.

    Mirrors rules.py ``_collect_string_leaves``: dict KEYS are ignored, only
    VALUES and list items are examined; non-string scalars are skipped.
    """
    out: list[str] = []
    if isinstance(node, dict):
        for v in node.values():
            out.extend(_leaves(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_leaves(v))
    elif isinstance(node, str):
        out.append(node)
    return out


def _checkable(leaf: str) -> bool:
    """Mirrors rules.py ``_is_checkable_leaf``: ≥4 raw-stripped chars and ≥1 alpha."""
    s = leaf.strip()
    return len(s) >= 4 and any(c.isalpha() for c in s)


def score_groundedness(*, value: dict, cited_source_text: str) -> float:
    """Fraction of checkable value leaves found verbatim in the cited source text.

    Returns 1.0 when there are no checkable leaves (nothing to disprove).
    """
    hay = _WS.sub(" ", (cited_source_text or "")).strip().lower()
    leaves = [leaf for leaf in _leaves(value or {}) if _checkable(leaf)]
    if not leaves:
        return 1.0
    if not hay:
        return 0.0
    supported = sum(1 for leaf in leaves if _WS.sub(" ", leaf).strip().lower() in hay)
    return round(supported / len(leaves), 3)
