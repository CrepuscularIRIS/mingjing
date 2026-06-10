"""Writer agent — a PURE deterministic projection of QA-passed claims.

The Writer turns the set of QA-passed claim rows into a :class:`Report`. There is
NO LLM in the claim->text path: the body is assembled by string templating over
the passed rows so the projection is deterministic and unit-testable offline.

The load-bearing invariant (plan Task 14, PURE test #5): every rendered
``referenced_id`` must exist in the passed-claims set. An id that is referenced
elsewhere but is NOT among the passed claims is dropped — the report can never
cite an unbacked claim.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Report:
    """A rendered report: templated body + the claim ids it actually cites.

    ``referenced_ids`` is guaranteed to be a subset of the passed-claims ids
    (the traceability invariant).
    """

    body: str
    referenced_ids: list[str] = field(default_factory=list)


def _render_claim_line(claim: dict[str, Any]) -> str:
    """Template a single passed claim into one report line (verbatim statement)."""
    cid = claim.get("id", "")
    field_name = claim.get("schema_field", "")
    statement = claim.get("statement", "")
    return f"[{cid}] ({field_name}) {statement}"


def render_report(
    *,
    passed_claims: list[dict[str, Any]],
    all_referenced_ids: list[str],
) -> Report:
    """Project QA-passed claims into a :class:`Report`, dropping unbacked ids.

    Pure and deterministic: identical inputs always yield an identical report.

    Args:
        passed_claims: The QA-passed claim rows (each a dict with at least
            ``id``; ``statement`` and ``schema_field`` are templated in).
        all_referenced_ids: Every claim id referenced anywhere downstream. Any id
            here that is NOT a passed claim is dropped from the output.

    Returns:
        A :class:`Report` whose ``referenced_ids`` is exactly the passed ids that
        were also referenced, in passed-claim order; the ``body`` templates only
        those surviving claims.
    """
    passed_by_id = {c.get("id"): c for c in passed_claims if c.get("id")}
    referenced = set(all_referenced_ids)

    # Preserve passed-claim order; keep only ids that are both passed and referenced.
    surviving = [c for c in passed_claims if c.get("id") in referenced]
    referenced_ids = [c["id"] for c in surviving]

    lines = [_render_claim_line(passed_by_id[cid]) for cid in referenced_ids]
    body = "\n".join(lines)
    return Report(body=body, referenced_ids=referenced_ids)
