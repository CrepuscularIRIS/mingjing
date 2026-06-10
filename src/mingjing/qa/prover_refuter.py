"""Anti-symmetric Prover/Refuter adjudication (deterministic aggregation).

STATUS — STAGED, NOT YET WIRED INTO THE GRAPH. This pure aggregation function is
implemented and tested, but the upstream LLM Prover/Refuter *roles* that would feed
it (and the QCReport confidence field it would adjust) are not yet built. Nothing
in graph.py / agents/qa.py calls ``adjudicate`` today. Do NOT pitch Prover/Refuter
as a live capability until it is wired — the running system's contradiction signal
is currently the deterministic source-vs-source ``stance`` logic in ``qa/rules.py``,
a different mechanism. (Keeping this honest is itself the evidence-discipline thesis.)

Two same-family LLM roles judge an un-attributed claim: a Prover argues it holds,
a Refuter hunts a refutation. There is no 'author' to prefer, so same weights are
fine. This module deterministically AGGREGATES their boolean verdicts into a
confidence tier + a contradiction flag — the verdict is code, the LLM only votes.
The result is ADVISORY (adjusts display confidence + feeds ContradictionCard); it
never enters route() or any gate boolean.
"""
from typing import get_args

from ..schemas import EvidenceStrength

# Ordering (low→high) is this module's concern; the schema Literal is unordered.
# MEMBERSHIP, however, comes from schemas.EvidenceStrength — the single source of
# truth. The assert turns a future vocab drift (a renamed/added tier) into a loud
# import-time failure instead of a silent downgrade through the `else "moderate"`.
_ORDER: tuple[str, ...] = ("weak", "moderate", "strong")
assert set(_ORDER) == set(get_args(EvidenceStrength)), "tier vocab drift vs schemas.EvidenceStrength"


def _down(tier: str, steps: int = 1) -> str:
    i = max(0, _ORDER.index(tier) - steps)
    return _ORDER[i]


def adjudicate(*, prover_supports: bool, refuter_refutes: bool, base_tier: str) -> dict:
    """Return {'confidence': tier, 'contradiction': bool}.

    - agree (prover supports, refuter finds nothing) → keep base tier.
    - refuter dissents while prover supports → genuine contradiction: downgrade 1
      step and flag (feeds ContradictionCard).
    - prover cannot support → collapse to weak.
    """
    base = base_tier if base_tier in _ORDER else "moderate"
    if not prover_supports:
        return {"confidence": "weak", "contradiction": refuter_refutes}
    if refuter_refutes:
        return {"confidence": _down(base, 1), "contradiction": True}
    return {"confidence": base, "contradiction": False}
