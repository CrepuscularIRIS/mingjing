"""Analyst agent — thin orchestration that turns sources into claims.

The Analyst makes one LLM call per field via :func:`mingjing.llm.call_llm`,
ALWAYS passing the fetched source text as ``untrusted_content`` so the
prompt-injection envelope (Task 13) quarantines it inside an ``<UNTRUSTED>``
block. The model returns a JSON claim payload (statement + evidence chunk ids).

This agent needs a live key/network and is exercised in the demo runs; only its
importability is unit-tested.
"""

import json
import logging
from typing import Any

from ..db import Database
from ..llm import call_llm
from ..schemas import active_field_schemas
from ..text_safety import sanitize_entity_name

logger = logging.getLogger(__name__)

# TRUST LIMITATION (demo scope — partially addressed):
# The "value MUST include required sub-fields" instruction below pressures the
# LLM to assert sub-fields even when source text lacks them.  The QA pipeline
# now verifies *value* content via VALUE_UNSUPPORTED: it checks that string
# leaves under REQUIRED sub-fields are substrings of cited source raw_text.
# Optional sub-fields (e.g. billing_period, currency) are not verified to avoid
# over-rejecting honest paraphrases.  The source-verbatim instruction below
# further reduces the revision loop by discouraging paraphrasing.
_FIELD_INSTRUCTION = (
    "You are the Analyst. From the evidence below, extract claims for the "
    "schema_field '{field}' about '{competitor}'. Each evidence block is prefixed "
    "with a line like '[source_id: <id>]'; use those exact ids. Return ONLY JSON "
    'of the form {{"statement": str, "claim_type": "fact"|"inference", '
    '"value": object, "evidence_ref": [source_id, ...], '
    '"evidence": [{{\"source_id\": str, \"snippet\": str, \"relevance\": str}}]}}. '
    "Cite only ids present in the evidence. "
    "The 'value' object MUST include ALL of these required sub-fields for '{field}': "
    "{required_fields}. The full set of sub-fields for '{field}' is: {sub_fields}. "
    "IMPORTANT: your response MUST be a SINGLE JSON object (dict), never a "
    "top-level JSON array; if a field has list-valued data (e.g. user_persona "
    "segments), place that list INSIDE the 'value' object under its sub-field key. "
    "For all string values inside the 'value' object, prefer SOURCE-VERBATIM spans: "
    "copy phrasing directly from the evidence text rather than paraphrasing, and "
    "never invent figures, tier names, or labels not present in the source. "
    "FORMAT CONSISTENCY: express each 'value' sub-field as the FULL verbatim "
    "phrase including currency symbol and unit when the source states them "
    "(e.g. '$10 per user/month', NOT the bare number 10), so the same sub-field "
    "is comparable across competitors in the report matrix. "
    "VERBATIM SNIPPET REQUIREMENT: for each cited source, the 'snippet' field in "
    "the evidence list MUST be a verbatim copy of the exact span from THAT source's "
    "text that contains (or directly supports) the claim's value — copy it "
    "character-for-character from the provided evidence block, do NOT paraphrase, "
    "summarize, or invent the snippet. If no source contains the value verbatim, "
    "do not assert the claim. "
    "Also include a 'stances' object mapping each cited source_id to a stance of "
    '"supports", "refutes", or "neutral" describing how that source relates to '
    "the claim's value: 'supports' if the source corroborates the value, "
    "'refutes' if it asserts a conflicting value, 'neutral' if it is merely "
    "context. Example: {{\"stances\": {{\"<id>\": \"supports\"}}}}."
)

# Appended (only when report_language == "zh") so the human-facing narrative is
# Chinese WITHOUT breaking QA grounding: the `statement` prose is translated, but
# `value` sub-fields and `snippet`s — the strings the QA gate substring-checks
# against source raw_text — MUST stay verbatim. Translating a value would make it
# unverifiable and the claim would be rejected (VALUE_UNSUPPORTED / HALLUCINATED).
_ZH_OUTPUT_INSTRUCTION = (
    " OUTPUT LANGUAGE: write the 'statement' field and each evidence 'relevance' "
    "description in Simplified Chinese (简体中文). CRITICAL EXCEPTION — do NOT "
    "translate evidence: every string inside the 'value' object and every "
    "'snippet' MUST stay VERBATIM from the source text (product names, prices, "
    "tier names, figures, and quoted spans remain character-for-character copies "
    "of the evidence). A translated value cannot be verified against the source "
    "and the claim will be rejected."
)


def build_field_prompt(
    *,
    field: str,
    competitor: str,
    required_fields: list[str],
    sub_fields: list[str],
    language: str = "en",
) -> str:
    """Return the analyst instruction string for ``field`` / ``competitor``.

    Pure helper — no I/O, no LLM call — so tests can assert the prompt text
    without standing up any infrastructure.  :func:`analyze_field` calls this
    function; it delegates to the :data:`_FIELD_INSTRUCTION` template.

    Args:
        field: The schema field being extracted (e.g. ``"pricing_model"``).
        competitor: The competitor under analysis.
        required_fields: List of required sub-field names for this field.
        sub_fields: Full list of sub-field names for this field.

    Returns:
        The formatted analyst instruction string.
    """
    # Sanitize the competitor at the trust boundary: in Discovery Mode the name
    # can originate from an attacker-influenceable search result, and it is
    # interpolated into the TRUSTED instruction. Collapsing whitespace + dropping
    # control chars neutralizes newline-delimited prompt injection regardless of
    # source (QA still contains any residue; this removes the surface).
    prompt = _FIELD_INSTRUCTION.format(
        field=field or "",
        competitor=sanitize_entity_name(competitor),
        required_fields=json.dumps(required_fields),
        sub_fields=json.dumps(sub_fields),
    )
    if language == "zh":
        prompt += _ZH_OUTPUT_INSTRUCTION
    return prompt


def coerce_payload_shape(payload: Any, field: str) -> Any:
    """Coerce a list-shaped analyst payload into the expected claim-object dict.

    The live model occasionally returns a bare JSON array (e.g. a list of
    persona segments) instead of the {statement, claim_type, value, evidence_ref}
    object.  Rather than silently dropping the field, wrap the list under the
    field's first required sub-field inside `value`, as an inference claim.
    Non-list payloads are returned unchanged.

    Empty-list special case: ``[]`` returns ``{}`` (falsy) so the analyze-node
    guard (``if not isinstance(payload, dict) or not payload``) skips it and
    emits ``claim_skipped`` rather than writing a zero-evidence, empty-statement
    claim to the DB.

    Args:
        payload: The parsed return value from the model (may be a list or dict).
        field: The schema field name, used to look up the required sub-field key.

    Returns:
        ``{}`` when ``payload`` is an empty list (so the analyze guard skips it);
        a well-shaped claim dict when ``payload`` is a non-empty list; otherwise
        ``payload`` unchanged.
    """
    if not isinstance(payload, list):
        return payload
    if not payload:
        return {}
    schema_info = active_field_schemas().get(field, {})
    required = schema_info.get("required", [])
    key = required[0] if required else "items"
    return {
        "statement": "",
        "claim_type": "inference",
        "value": {key: payload},
        "evidence_ref": [],
    }


def filter_evidence_refs(
    payload: dict[str, Any], valid_source_ids: set[str]
) -> dict[str, Any]:
    """Drop ``evidence_ref`` entries whose source_id is not a provided source.

    The LLM may hallucinate or emit empty/unknown source ids; passing those
    downstream would let a fabricated citation masquerade as evidence. This
    pure helper returns a NEW payload whose ``evidence_ref`` list contains only
    ids present in ``valid_source_ids`` (preserving order, dropping blanks).

    Args:
        payload: The parsed claim payload from the model.
        valid_source_ids: The set of source ids actually supplied to the model.

    Returns:
        A shallow copy of ``payload`` with a cleaned ``evidence_ref`` list.
    """
    cleaned = dict(payload)
    refs = cleaned.get("evidence_ref")
    if isinstance(refs, list):
        cleaned["evidence_ref"] = [
            ref for ref in refs if ref and ref in valid_source_ids
        ]
    return cleaned


def analyze_field(
    db: Database,
    run_id: str,
    *,
    field: str,
    competitor: str,
    evidence_text: str,
    source_ids: set[str] | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Produce a claim payload for one ``field`` from fetched ``evidence_text``.

    The fetched text is passed as ``untrusted_content`` so :func:`call_llm`
    wraps it with the prompt-injection envelope; the trusted instruction stays
    in the top-level message stream.

    Args:
        db: Database handle for ``llm_calls`` logging.
        run_id: Owning run id.
        field: The schema field being analyzed.
        competitor: The competitor under analysis.
        evidence_text: Concatenated fetched source text (untrusted).
        source_ids: The ids of the sources actually supplied. When given, any
            ``evidence_ref`` the model returns that is not in this set is
            dropped so a hallucinated/empty citation never flows downstream.
        settings: Optional pre-loaded settings.

    Returns:
        The parsed JSON claim payload from the model, with evidence refs
        validated against ``source_ids`` when provided.
    """
    schema_info = active_field_schemas().get(field, {})
    required_fields = schema_info.get("required", [])
    sub_fields = schema_info.get("sub_fields", [])
    # Output language comes from settings (live runs default to "zh" via
    # Settings.load()); absent settings (some test paths) fall back to English so
    # the prompt is unchanged. Value/snippet verbatim grounding is unaffected.
    language = getattr(settings, "report_language", "en")
    instruction = build_field_prompt(
        field=field,
        competitor=competitor,
        required_fields=required_fields,
        sub_fields=sub_fields,
        language=language,
    )
    payload = call_llm(
        db,
        run_id,
        agent="analyst",
        messages=[{"role": "user", "content": instruction}],
        schema=True,
        settings=settings,
        untrusted_content=evidence_text,
    )
    payload = coerce_payload_shape(payload, field)
    if source_ids is not None and isinstance(payload, dict):
        payload = filter_evidence_refs(payload, source_ids)
    return payload
