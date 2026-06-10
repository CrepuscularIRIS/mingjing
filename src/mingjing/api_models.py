"""Pydantic request models for the MingJing API (extracted from ``api.py``).

These are the request bodies for the two mutating endpoints (``POST /runs`` and
``POST /runs/{run_id}/claims/{claim_id}/correct``). They live in their own module
so ``api.py`` stays focused on the app factory and endpoint wiring; ``api.py``
re-exports both names so existing imports (``from mingjing.api import
CreateRunRequest``) keep working unchanged.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .schema_registry import list_domains

_VALID_DEPTHS = {"quick", "detailed"}

# Input bounds for free-text / list fields. These feed prompts, search queries
# and the runs row, so we cap them to keep a single request from carrying an
# unbounded payload (DoS / prompt-stuffing defense). Generous enough that no
# legitimate competitive-analysis request is rejected.
_MAX_TEXT_LEN = 512  # category / goal
_MAX_NAME_LEN = 128  # one competitor / seed name
_MAX_LIST_LEN = 12  # competitors / seed_competitors list length


class CreateRunRequest(BaseModel):
    """Request body for ``POST /runs``.

    Two entry shapes, distinguished by ``competitors``:

    * **Directed Mode** — ``competitors`` provided: the run analyzes exactly those
      products (unchanged historical behavior).
    * **Discovery Mode** — ``competitors`` empty + ``category`` set: the runner
      runs a bounded discovery pre-step to find competitors before analysis.
      ``market_scope`` / ``seed_competitors`` / ``max_competitors`` tune it.
    """

    category: str = Field(max_length=_MAX_TEXT_LEN)
    competitors: list[str] = Field(default=[], max_length=_MAX_LIST_LEN)
    goal: str = Field(max_length=_MAX_TEXT_LEN)
    domain: str | None = None
    depth: str | None = None
    market_scope: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    max_competitors: int = 4
    seed_competitors: list[str] = Field(default=[], max_length=_MAX_LIST_LEN)

    @model_validator(mode="after")
    def require_competitors_or_category(self) -> CreateRunRequest:
        """Require explicit competitors OR a category for discovery.

        Directed Mode needs at least one competitor; Discovery Mode needs a
        non-empty category to search from. A request with neither is rejected.
        """
        if not self.competitors and not (self.category or "").strip():
            raise ValueError(
                "provide competitors (Directed Mode) or a category (Discovery Mode)"
            )
        return self

    @field_validator("competitors", "seed_competitors")
    @classmethod
    def names_within_length(cls, v: list[str]) -> list[str]:
        """Reject any single competitor/seed name longer than the per-name cap.

        ``Field(max_length=...)`` on the list bounds its LENGTH, not the length
        of each element; this caps each name so a request cannot smuggle an
        unbounded string inside a short list.
        """
        for name in v:
            if len(name) > _MAX_NAME_LEN:
                raise ValueError(f"name too long (max {_MAX_NAME_LEN} chars): {name[:32]!r}…")
        return v

    @field_validator("max_competitors")
    @classmethod
    def max_competitors_in_range(cls, v: int) -> int:
        """Clamp the discovery cap to a sane bound (1..6)."""
        return max(1, min(int(v), 6))

    @field_validator("domain")
    @classmethod
    def domain_is_known(cls, v: str | None) -> str | None:
        """Allow an unset domain, but reject any value outside the registry."""
        known = list_domains()
        if v is not None and v not in known:
            raise ValueError(f"unknown domain: {v!r}; valid domains: {', '.join(known)}")
        return v

    @field_validator("depth")
    @classmethod
    def depth_is_valid(cls, v: str | None) -> str | None:
        """Allow None (will be resolved to settings default), but reject unknown values."""
        if v is not None and v not in _VALID_DEPTHS:
            raise ValueError(
                f"invalid depth: {v!r}; valid values: {', '.join(sorted(_VALID_DEPTHS))}"
            )
        return v


class ClaimCorrectionRequest(BaseModel):
    """Request body for ``POST /runs/{run_id}/claims/{claim_id}/correct``."""

    action: Literal["accept", "reject", "edit"]
    statement: str | None = None
    value: dict | None = None
    note: str | None = None


# Bounds for one survey response: every answer becomes a persisted evidence
# chunk and feeds grounding haystacks, so entry counts and each leaf length
# are capped (DoS / prompt-stuffing defense, same posture as CreateRunRequest).
# Module-level constants — NOT class attributes: pydantic v2 wraps underscore
# class attrs in ModelPrivateAttr, which breaks comparisons inside validators
# (TypeError → 500 instead of a clean 422).
_MAX_ANSWERS = 20
_MAX_ANSWER_LEN = 4_000
_MAX_META_KEYS = 20
_MAX_META_STR_LEN = 500
_MAX_KEY_LEN = 100


class SurveyResponseItem(BaseModel):
    """One survey response — strictly typed AND bounded so malformed or
    unbounded nested payloads are rejected with 422 BEFORE any persistence.

    ``ingest_survey`` persists row-by-row inside a batch loop; an exception on
    response N would leave responses 1..N-1 in the DB with NO audit event
    (partial unaudited data — Codex stop-review). With every leaf forced to a
    bounded scalar string here, the ingest loop cannot fail on payload shape,
    so the validate-then-persist boundary is airtight.
    """

    model_config = {"extra": "forbid"}

    respondent_meta: dict[str, str | int | float | bool | None] | None = None
    answers: dict[str, str] | list[str] | None = None
    raw_text: str | None = Field(default=None, max_length=20_000)
    title: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _require_content(self) -> SurveyResponseItem:
        has_answers = bool(self.answers)
        if not has_answers and not (self.raw_text or "").strip():
            raise ValueError("response needs non-empty 'answers' or 'raw_text'")
        return self

    @field_validator("answers")
    @classmethod
    def _answers_bounded_and_nonempty(
        cls, v: dict[str, str] | list[str] | None
    ) -> dict[str, str] | list[str] | None:
        if v is None:
            return v
        if len(v) > _MAX_ANSWERS:
            raise ValueError(f"too many answers (max {_MAX_ANSWERS})")
        if isinstance(v, dict) and any(len(k) > _MAX_KEY_LEN for k in v):
            raise ValueError(f"answer key too long (max {_MAX_KEY_LEN} chars)")
        leaves = list(v.values()) if isinstance(v, dict) else v
        if any(not (s or "").strip() for s in leaves):
            raise ValueError("answers must not contain empty entries")
        if any(len(s) > _MAX_ANSWER_LEN for s in leaves):
            raise ValueError(f"answer too long (max {_MAX_ANSWER_LEN} chars)")
        return v

    @field_validator("respondent_meta")
    @classmethod
    def _meta_bounded(
        cls, v: dict[str, str | int | float | bool | None] | None
    ) -> dict[str, str | int | float | bool | None] | None:
        if v is None:
            return v
        if len(v) > _MAX_META_KEYS:
            raise ValueError(f"too many respondent_meta keys (max {_MAX_META_KEYS})")
        for k, val in v.items():
            if len(k) > _MAX_KEY_LEN:
                raise ValueError(f"respondent_meta key too long (max {_MAX_KEY_LEN})")
            if isinstance(val, str) and len(val) > _MAX_META_STR_LEN:
                raise ValueError(
                    f"respondent_meta value too long (max {_MAX_META_STR_LEN} chars)"
                )
        return v


class SurveyImportRequest(BaseModel):
    """Request body for ``POST /runs/{run_id}/survey/import`` (问卷调研接入).

    Real survey responses enter through here as ``source_mode="INGESTED"``
    rows that keep authoritative scoring weight — the honest counterpart of
    the SIMULATED fixture lane. PII is scrubbed by ``ingest.ingest_survey``
    before persistence. The batch is capped to keep a single request bounded.
    """

    survey_id: str = Field(min_length=1, max_length=64)
    responses: list[SurveyResponseItem] = Field(min_length=1, max_length=50)
