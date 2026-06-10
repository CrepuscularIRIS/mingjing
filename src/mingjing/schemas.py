"""Typed artifacts for the MingJing runtime (Pydantic v2).

Contains the in-flight domain models, the 5 frozen field schemas, and the QA
issue-code enum. The load-bearing invariant: a ``fact`` claim must carry at least
one evidence chunk (a fact without evidence is a hallucination, not a claim).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from .schema_registry import load_domain, resolve_active_schema

# SNIPPET: search-result snippet fallback (collector); SIMULATED: fixture-seeded
# demo survey/interview rows — display+grounding only, never feed credibility.
SourceMode = Literal["LIVE", "CACHED", "INGESTED", "SNIPPET", "SIMULATED"]
ClaimType = Literal["fact", "inference"]
EvidenceStrength = Literal["strong", "moderate", "weak"]
Verdict = Literal["pass", "reject"]


class IssueCode(str, Enum):
    """QA issue codes emitted by the verifier rules."""

    SCHEMA_GAP = "SCHEMA_GAP"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    CONTRADICTION = "CONTRADICTION"
    HALLUCINATED_SNIPPET = "HALLUCINATED_SNIPPET"
    LOW_COVERAGE = "LOW_COVERAGE"
    VALUE_UNSUPPORTED = "VALUE_UNSUPPORTED"


class ResearchTask(BaseModel):
    """A single competitive-analysis run request."""

    id: str
    category: str
    competitors: list[str]
    goal: str
    fields: list[str] = []


class SourceDoc(BaseModel):
    """A fetched/ingested source with provenance."""

    id: str
    run_id: str
    url: str | None = None
    title: str | None = None
    source_type: str = "web"  # web | official | review | forum | survey | interview
    source_mode: SourceMode | None = None
    fetched_at: float | None = None
    content_hash: str | None = None
    raw_text: str | None = None
    respondent_meta: dict[str, Any] = {}


class EvidenceChunk(BaseModel):
    """A precise, locator-addressed span of a source supporting a claim."""

    id: str
    run_id: str
    source_id: str | None = None
    locator: str | None = None  # e.g. "url#p:3" or "survey:SV-1/q3"
    text: str
    content_hash: str | None = None


class Claim(BaseModel):
    """A typed claim. A fact claim must have at least one evidence chunk."""

    id: str
    run_id: str
    competitor: str | None = None
    schema_field: str
    claim_type: ClaimType
    statement: str
    value: dict[str, Any] = {}
    evidence: list[EvidenceChunk] = []
    based_on: list[str] = []  # claim ids this inference depends on
    evidence_strength: EvidenceStrength
    status: str = "draft"  # draft | passed | rejected | superseded | partial
    version: int = 1
    produced_by: str | None = None

    @model_validator(mode="after")
    def _fact_requires_evidence(self) -> "Claim":
        if self.claim_type == "fact" and not self.evidence:
            raise ValueError("a fact claim must have at least one evidence chunk")
        return self


class SWOTBlock(BaseModel):
    """Structured SWOT for one competitor."""

    competitor: str
    strengths: list[str] = []
    weaknesses: list[str] = []
    opportunities: list[str] = []
    threats: list[str] = []


class QCReport(BaseModel):
    """QA verdict for a claim with its emitted issues."""

    id: str
    run_id: str
    claim_id: str | None = None
    round: int = 0
    verdict: Verdict
    issues: list[IssueCode] = []


class RevisionTask(BaseModel):
    """A concrete, assignee-routed redo instruction (never freeform prose)."""

    id: str
    run_id: str
    claim_id: str | None = None
    assignee: str  # collector | analyst
    issue_code: IssueCode | None = None
    instruction: str = ""
    status: str = "open"  # open | done
    round: int = 0


class ReportSection(BaseModel):
    """A projected report section; only references QA-passed claim ids."""

    schema_field: str
    title: str
    body: str = ""
    referenced_ids: list[str] = []


# Active domain field schemas — resolved at import time from the
# MINGJING_SCHEMA_DOMAIN env-var (default: the 5 frozen fields below).
# Switching domains requires ZERO code edits; see schema_registry.py.
# Default domain = pricing_model / user_sentiment / feature_tree /
#                  user_persona / swot  (byte-identical to the original literal).
FIELD_SCHEMAS: dict[str, dict[str, Any]] = resolve_active_schema()


# Per-run active schema. Default (None) → the env-resolved FIELD_SCHEMAS. A run
# executor sets this for its own thread/context so a run can analyze a different
# domain without disturbing the global default (concurrent-safe via ContextVar).
_active_schema: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "active_field_schemas", default=None
)


def active_field_schemas() -> dict[str, dict[str, Any]]:
    """The field schema for the current context (per-run override, else env default).

    Uses ``is None`` (not truthiness) so a legitimately EMPTY active domain is
    honored rather than silently falling back to the default — only the unset
    sentinel restores the default.
    """
    active = _active_schema.get()
    return FIELD_SCHEMAS if active is None else active


def set_active_domain(name: str | None) -> None:
    """Set the active schema for THIS context to ``name``'s domain (None → default).

    Raises:
        ValueError: When ``name`` is not a known domain (from ``load_domain``).
    """
    _active_schema.set(load_domain(name) if name else None)


@contextmanager
def use_domain(name: str):
    """Use ``name``'s domain schema within the block, then RESTORE the previous
    context value (nestable). ``load_domain(name)`` raises ``ValueError`` for an
    unknown domain before the block runs."""
    token = _active_schema.set(load_domain(name))
    try:
        yield
    finally:
        _active_schema.reset(token)
