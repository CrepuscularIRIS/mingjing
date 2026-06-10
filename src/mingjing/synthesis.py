"""Synthesis projection + the post-write synthesis driver.

``project_synthesis`` is pure: it enforces that every factual report sentence is
backed by passed claim ids (mirroring ``writer.render_report``).

``run_synthesis`` is the impure driver wired into the graph AFTER the write node.
It reads the QA-passed claim ledger, drives <=3 schema LLM calls (split to avoid
MiniMax JSON truncation), projects the merged payload, and persists it to the
append-only ``syntheses`` table. It is **NON-FATAL**: any exception logs a trace
event and returns without raising, so the run still completes and the frontend
falls back to the deterministic ledger.
"""
import logging
from typing import Any

from .llm import call_llm

logger = logging.getLogger(__name__)

_SCAFFOLD_SECTIONS = {"intelligence_gap", "key_assumptions"}

# Shared instruction shared by all three prompt builders. Sentences must be shaped
# {text, claim_ids:[...]} and may cite ONLY ids that appear in the provided ledger.
_CITATION_RULES = (
    "Return ONLY a single JSON object — no prose, no markdown fences.\n"
    "Every factual sentence MUST be an object shaped"
    ' {"text": "<sentence>", "claim_ids": ["<id>", ...]}.\n'
    "You may cite ONLY claim ids that appear in the LEDGER below; never invent ids."
)


def _keep(sentence: dict, passed: set[str], *, scaffold: bool) -> bool:
    ids = sentence.get("claim_ids") or []
    if scaffold and not ids:
        return True  # gap/assumption framing may be uncited
    return bool(ids) and set(ids) <= passed


def build_withheld_disclosure(run_id: str, db: Any) -> list[dict[str, Any]]:
    """Enumerate claims withheld from the report + WHY (issue codes), per run.

    Closes "Architecture closure ③": a ``write_partial`` must NOT be silent.
    Flagged claims correctly STAY ``draft`` (withheld from the ``status="pass"``
    report); this reader lists exactly those withheld claims so a consumer can
    audit what is missing.

    A claim is disclosed when (a) its latest version is NOT ``status="pass"``
    (i.e. it never got promoted — it was withheld) AND (b) the LAST QA round
    flagged it with at least one issue code. Each entry joins the claim to its
    final-round issue codes and round number.

    This is advisory/reporting ONLY: it does NOT promote claims or alter any
    verdict/route decision. Defensive: missing/empty rows -> ``[]``.

    Args:
        run_id: The run to disclose withheld claims for.
        db: Open database handle (source of truth).

    Returns:
        ``[{"claim_id": str, "issue_codes": [str, ...], "round": int}, ...]``,
        sorted by ``claim_id`` for stable output. Empty when nothing was
        withheld (or the run has no qc_reports / claims).
    """
    last_round = db.last_round_issues_for_run(run_id)
    if not last_round:
        return []
    # Only claims that were actually withheld (latest version not promoted).
    not_passed = {
        c["id"]
        for c in db.latest_claims_for_run(run_id)
        if c.get("status") != "pass"
    }
    disclosure = [
        {
            "claim_id": claim_id,
            "issue_codes": info["issue_codes"],
            "round": info["round"],
        }
        for claim_id, info in last_round.items()
        if claim_id in not_passed
    ]
    return sorted(disclosure, key=lambda d: d["claim_id"])


def project_synthesis(
    *, payload: dict[str, Any], passed_claim_ids: set[str]
) -> dict[str, Any]:
    passed = set(passed_claim_ids)
    out: dict[str, Any] = {}
    referenced: set[str] = set()

    def _norm(s: dict) -> dict:
        # Normalize a kept sentence so the persisted shape ALWAYS carries a
        # list ``claim_ids`` (scaffold sentences may omit it) — consumers can
        # rely on the field existing and being a list.
        ids = s.get("claim_ids")
        ids = ids if isinstance(ids, list) else []
        return {**s, "claim_ids": ids}

    def proj_list(items: Any, scaffold: bool) -> list[dict]:
        kept = [_norm(s) for s in (items or []) if _keep(s, passed, scaffold=scaffold)]
        for s in kept:
            referenced.update(s["claim_ids"])
        return kept

    # single-sentence sections
    for key in ("bluf",):
        s = payload.get(key)
        if s and _keep(s, passed, scaffold=False):
            normed = _norm(s)
            out[key] = normed
            referenced.update(normed["claim_ids"])
    # swot quadrants
    swot = payload.get("swot") or {}
    out["swot"] = {
        q: proj_list(swot.get(q), scaffold=False)
        for q in ("strengths", "weaknesses", "opportunities", "threats")
    }
    # list sections
    out["comparison"] = proj_list(payload.get("comparison"), scaffold=False)
    out["recommendations"] = proj_list(payload.get("recommendations"), scaffold=False)
    out["intelligence_gap"] = proj_list(payload.get("intelligence_gap"), scaffold=True)
    out["key_assumptions"] = proj_list(payload.get("key_assumptions"), scaffold=True)
    out["referenced_claim_ids"] = sorted(referenced)
    return out


def brief_sentence_count(payload: dict[str, Any] | None) -> int:
    """Count the real, claim-backed brief sentences in a projected synthesis.

    "Real brief" means cited analysis sentences a reader would see as the
    synthesis output: BLUF, the four SWOT quadrants, comparison, and
    recommendations. Scaffold-only keys (``withheld``, ``referenced_claim_ids``,
    ``intelligence_gap``/``key_assumptions`` framing) do NOT count — a payload
    carrying only those is an honest *empty* synthesis, not a produced brief.

    This is the single source of truth for the trace's real-vs-empty decision so
    ``synthesis_done`` only fires when a brief actually exists.

    Args:
        payload: A projected synthesis dict (e.g. from ``db.get_synthesis``), or
            ``None``/empty when no synthesis was persisted.

    Returns:
        The number of brief sentences (>= 0). ``0`` means honest-empty.
    """
    if not payload or not isinstance(payload, dict):
        return 0
    count = 0
    if payload.get("bluf"):
        count += 1
    swot = payload.get("swot") or {}
    if isinstance(swot, dict):
        for quadrant in ("strengths", "weaknesses", "opportunities", "threats"):
            items = swot.get(quadrant)
            if isinstance(items, list):
                count += len(items)
    for key in ("comparison", "recommendations"):
        items = payload.get(key)
        if isinstance(items, list):
            count += len(items)
    return count


def _format_ledger(passed: list[dict[str, Any]]) -> str:
    """Render the passed-claim ledger the model cites from.

    One line per claim: ``id | field | statement | strength | admiralty``. The
    ``admiralty`` token is included only when present on the claim row (Task 3
    may attach it); otherwise it is omitted so the line stays clean.
    """
    lines = []
    for c in passed:
        parts = [
            str(c.get("id", "")),
            str(c.get("schema_field", "")),
            str(c.get("statement", "")),
            str(c.get("evidence_strength", "")),
        ]
        admiralty = c.get("admiralty")
        if admiralty:
            parts.append(str(admiralty))
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _ledger_block(ledger: str) -> str:
    return f"{_CITATION_RULES}\n\nLEDGER (cite only these ids):\n{ledger}"


# Appended to the user message when report_language == "zh". Synthesis sentences
# cite already-passed (TRUSTED) claim_ids and are NOT substring-checked against
# source text, so writing them in Chinese carries no QA-grounding risk.
_ZH_SYNTH_INSTRUCTION = (
    "\n\nOUTPUT LANGUAGE: write the 'text' of every sentence object in Simplified "
    "Chinese (简体中文). Keep claim_ids unchanged and keep product / brand names as-is."
)


def _lang_suffix(language: str) -> str:
    return _ZH_SYNTH_INSTRUCTION if language == "zh" else ""


def _swot_comparison_messages(ledger: str, language: str = "en") -> list[dict[str, Any]]:
    """Call A — SWOT quadrants + the comparison matrix."""
    return [
        {
            "role": "system",
            "content": (
                "You are a competitive-intelligence synthesis analyst. "
                "From the verified claim ledger, produce a SWOT analysis and a "
                "competitor comparison matrix."
            ),
        },
        {
            "role": "user",
            "content": (
                'Return JSON with keys "swot" (object with arrays "strengths", '
                '"weaknesses", "opportunities", "threats") and "comparison" (array). '
                "Each array element is a cited sentence object.\n\n"
                + _ledger_block(ledger)
                + _lang_suffix(language)
            ),
        },
    ]


def _bluf_recs_messages(ledger: str, language: str = "en") -> list[dict[str, Any]]:
    """Call B — BLUF (bottom line up front) + recommendations."""
    return [
        {
            "role": "system",
            "content": (
                "You are a competitive-intelligence synthesis analyst. "
                "From the verified claim ledger, write a single BLUF sentence and "
                "a list of actionable recommendations."
            ),
        },
        {
            "role": "user",
            "content": (
                'Return JSON with keys "bluf" (a single cited sentence object) and '
                '"recommendations" (array of cited sentence objects).\n\n'
                + _ledger_block(ledger)
                + _lang_suffix(language)
            ),
        },
    ]


def _gap_assumptions_messages(ledger: str, language: str = "en") -> list[dict[str, Any]]:
    """Call C — intelligence gaps + key assumptions (scaffold; may be uncited)."""
    return [
        {
            "role": "system",
            "content": (
                "You are a competitive-intelligence synthesis analyst. "
                "Identify intelligence gaps (what the ledger does NOT yet cover) "
                "and the key assumptions underlying the analysis."
            ),
        },
        {
            "role": "user",
            "content": (
                'Return JSON with keys "intelligence_gap" (array) and '
                '"key_assumptions" (array) of sentence objects. These framing '
                "sentences MAY omit claim_ids when no specific claim applies.\n\n"
                + _ledger_block(ledger)
                + _lang_suffix(language)
            ),
        },
    ]


def run_synthesis(db: Any, run_id: str, settings: Any) -> None:
    """Drive the post-write synthesis pass and persist the projected payload.

    NON-FATAL: the entire body is wrapped so any exception logs a trace event and
    returns without raising — the run still completes and the frontend falls back
    to the deterministic ledger. Splits the work into <=3 schema LLM calls to
    avoid MiniMax JSON truncation. Passed claims are TRUSTED, so they are NOT sent
    as ``untrusted_content``.

    Args:
        db: Open database handle (source of truth).
        run_id: The run to synthesize over.
        settings: Optional pre-loaded settings forwarded to ``call_llm``.
    """
    try:
        passed = [
            c for c in db.latest_claims_for_run(run_id) if c.get("status") == "pass"
        ]
        if not passed:
            # No passed claims, but a fully-rejected partial run must still NOT
            # be silent: persist a minimal payload that enumerates the withheld
            # claims (else the frontend's intelligence-gap empty state hides why).
            try:
                withheld = build_withheld_disclosure(run_id, db)
            except Exception:  # noqa: BLE001 — disclosure is advisory; never fatal
                logger.exception(
                    "withheld-claims disclosure failed for run_id=%s; omitting",
                    run_id,
                )
                withheld = []
            if withheld:
                db.append_synthesis(run_id, {"withheld": withheld})
            return  # empty -> frontend shows the intelligence-gap empty state
        ledger = _format_ledger(passed)
        language = getattr(settings, "report_language", "en")
        payload: dict[str, Any] = {}
        for builder in (
            _swot_comparison_messages,
            _bluf_recs_messages,
            _gap_assumptions_messages,
        ):
            part = call_llm(
                db,
                run_id,
                agent="synthesis",
                messages=builder(ledger, language),
                schema=True,
                settings=settings,
            )
            if isinstance(part, dict):
                payload.update(part)
        projected = project_synthesis(
            payload=payload, passed_claim_ids={c["id"] for c in passed}
        )
        # Non-silent honest partial: enumerate withheld (draft/rejected) claims +
        # their final-round issue codes. Advisory/reporting only — never promotes
        # a claim or alters a verdict. Defensive so a disclosure failure does not
        # break the synthesis payload.
        try:
            projected["withheld"] = build_withheld_disclosure(run_id, db)
        except Exception:  # noqa: BLE001 — disclosure is advisory; never fatal
            logger.exception(
                "withheld-claims disclosure failed for run_id=%s; omitting", run_id
            )
            projected["withheld"] = []
        db.append_synthesis(run_id, projected)
    except Exception:  # noqa: BLE001 — synthesis is non-fatal; the ledger is the fallback
        logger.exception(
            "synthesis failed for run_id=%s; falling back to deterministic ledger",
            run_id,
        )
