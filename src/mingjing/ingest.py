"""Survey and interview source ingest (Task 17).

Provides two ingest functions for primary-research data collected by humans and
a pure anonymization helper. All ingested data is persisted via the append-only
DB layer and is OFFLINE (no network or LLM).

Privacy invariant: respondent identity fields (name, email, phone) are stripped
or redacted before any data reaches the DB. ``anonymize_respondent_meta`` is
the single gate that enforces this invariant — callers MUST pass their
respondent metadata through it before persisting.

Source-type assignments:
- ``ingest_survey``    → ``source_type="survey"`` (AUTHORITATIVE for scoring)
- ``ingest_interview`` → ``source_type="interview"``

Locator scheme:
- Survey evidence chunk:    ``survey:<survey_id>/q<n>``
- Interview evidence chunk: ``interview:<interview_id>/seg<n>``
"""

import json
import re
import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# PII regex patterns used by anonymize_respondent_meta
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

_PHONE_PATTERN = re.compile(
    r"""
    (?:
        \+?1?[\s.\-]?        # optional country code (US/CA)
        \(?[2-9]\d{2}\)?     # area code
        [\s.\-]?
        \d{3}
        [\s.\-]?
        \d{4}
    )
    |
    (?:
        \+?[1-9]\d{0,3}      # international prefix (UK +44, CN +86, etc.)
        [\s.\-]?
        \d{1,4}
        [\s.\-]
        \d{3,4}
        [\s.\-]
        \d{3,4}
    )
    """,
    re.VERBOSE,
    # Known limitation: targets US/UK/CN international formats; some local EU
    # and non-standard formats may not be caught (NER would be required).
)

# Keys whose presence means the value is identity data (drop entirely).
# Known limitation: arbitrary free-text NAME *values* under unrecognized keys
# (e.g. {"feedback": "Jane Doe says..."}) cannot be caught without NER.
# The key-name allowlist below is the primary mitigation.
_IDENTITY_KEY_RE = re.compile(
    r"(name|email|phone|mobile|cell|tel|firstname|lastname|surname|fullname"
    r"|respondent|speaker|interviewer|interviewee|participant"
    r"|contact_person|contact|user|author)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def _redact_string(value: str) -> str:
    """Redact email and phone patterns within a string value.

    Used for both meta values (Rule 2 of ``anonymize_respondent_meta``) and
    free-text answer/segment content (I2 requirement).  Only email and phone
    patterns are removed; name tokens in free-text are NOT removed because
    answer content is evidence material — removing names would destroy meaning.
    NER-based name removal in free text is a known, documented limitation.
    """
    cleaned = _EMAIL_PATTERN.sub("[REDACTED]", value)
    cleaned = _PHONE_PATTERN.sub("[REDACTED]", cleaned)
    return cleaned


def _anonymize_value(value: Any) -> Any:
    """Recursively anonymize a value (string, int/float, dict, list, or other).

    - str: redact email/phone patterns.
    - int/float: stringify, redact phone patterns if matched, else keep original.
    - dict: recurse via :func:`anonymize_respondent_meta` (drops identity keys too).
    - list: recurse element-by-element.
    - other: return as-is (new value, no shared reference issues for scalars).
    """
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, (int, float)):
        as_str = str(value)
        if _PHONE_PATTERN.search(as_str):
            return "[REDACTED]"
        return value
    if isinstance(value, dict):
        return anonymize_respondent_meta(value)
    if isinstance(value, list):
        return [_anonymize_value(item) for item in value]
    return value


def anonymize_respondent_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Return a NEW dict with identity fields removed and PII values redacted.

    Rules applied **recursively** at every nesting level:

    1. Drop any key whose name matches ``name``, ``email``, ``phone``,
       ``mobile``, ``cell``, ``tel``, ``firstname``, ``lastname``,
       ``surname``, ``fullname``, ``respondent``, ``speaker``,
       ``interviewer``, ``interviewee``, ``participant``,
       ``contact_person``, ``contact``, ``user``, or ``author``
       (case-insensitive substring match).
    2. For surviving string values, substitute email-shaped and phone-shaped
       substrings with ``"[REDACTED]"`` so PII stored under a non-obvious key
       is also scrubbed.
    3. For surviving int/float values, stringify and apply phone pattern; if
       matched, replace with ``"[REDACTED]"``, otherwise keep original value.
    4. For surviving dict values, recurse (identity keys are dropped at every
       nesting level, not just the top level).
    5. For surviving list values, recurse element-by-element.

    The input dict is **never mutated** — entirely new structures are returned
    at every level (no shared references with the input).

    Known limitation: arbitrary free-text NAME *values* under unrecognized
    keys (e.g. ``{"feedback": "Jane Doe says..."}`` ) cannot be caught without
    NER. The key-name allowlist above is the primary mitigation for known
    identity-field names.

    Args:
        meta: Raw respondent metadata dict from the collection instrument.

    Returns:
        A new dict safe to persist (no name / email / phone survives at any
        nesting depth).
    """
    result: dict[str, Any] = {}
    for key, value in meta.items():
        # Rule 1: drop identity-named keys entirely (at every nesting level).
        if _IDENTITY_KEY_RE.search(str(key)):
            continue
        # Rules 2-5: anonymize the value recursively.
        result[key] = _anonymize_value(value)
    return result


# ---------------------------------------------------------------------------
# Ingest functions
# ---------------------------------------------------------------------------


def ingest_survey(
    db: Any,
    run_id: str,
    responses: list[dict[str, Any]],
    *,
    survey_id: str,
) -> list[str]:
    """Ingest survey responses as ``source_type="survey"`` artifacts.

    Each response is persisted as one SourceDoc row in ``sources`` and its
    answers become individual evidence chunks with locators
    ``survey:<survey_id>/q<n>``.

    Privacy: every ``respondent_meta`` dict is passed through
    :func:`anonymize_respondent_meta` before it reaches the DB.
    Additionally, ``raw_text`` and each answer/chunk text are passed through
    :func:`mingjing.survey.scrub_open_text` before persistence — the stronger
    open-text scrubber for user-submitted survey free-text. It redacts email,
    phone, CN national ID, postal codes, and names that follow an explicit
    trigger phrase (我叫 / my name is). Arbitrary free-text names WITHOUT a
    trigger phrase are still preserved (regex-not-NER limitation), since survey
    answers are also analysis material for sentiment scoring.

    Args:
        db: A :class:`~mingjing.db.Database` instance.
        run_id: The owning run id.
        responses: A list of response dicts. Recognised keys:

            - ``respondent_meta`` (dict) — anonymized automatically.
            - ``answers`` (dict | list) — question-keyed or ordered answers
              that each become a separate evidence chunk.
            - ``raw_text`` (str) — free-text of the full response; used when
              no structured ``answers`` are present, and also stored as the
              source's ``raw_text``.
            - ``title`` (str) — optional descriptive title.

        survey_id: A stable caller-assigned survey identifier (e.g. ``"SV-1"``).

    Returns:
        A list of persisted ``source_id`` strings (one per response).
    """
    # Lazy import: survey.py imports the PII regexes from this module, so a
    # top-level import here would be circular. By call time both modules are
    # fully loaded.
    from .survey import scrub_open_text

    source_ids: list[str] = []
    now = time.time()

    for resp_idx, response in enumerate(responses):
        source_id = str(uuid.uuid4())
        raw_text = scrub_open_text(response.get("raw_text"))[0]
        title = (
            response.get("title")
            or f"Survey {survey_id} response {resp_idx + 1}"
        )
        anon_meta = anonymize_respondent_meta(
            response.get("respondent_meta") or {}
        )

        db.append_source(
            {
                "id": source_id,
                "run_id": run_id,
                # Locator-style url: registrable_domain collapses every
                # survey:* locator to the literal domain "survey", so N
                # respondents of one survey count as ONE independent voice —
                # without this (url=None) the QA tuple-builder falls back to
                # per-source-id domains and two respondents alone could mint
                # a second "independent domain". Mirrors survey_seed.py.
                "url": f"survey:{survey_id}/r{resp_idx + 1}",
                "title": title,
                "source_type": "survey",
                "source_mode": "INGESTED",
                "fetched_at": now,
                "content_hash": None,
                "raw_text": raw_text,
                "meta_json": json.dumps(anon_meta, ensure_ascii=False),
            }
        )

        # Persist per-question evidence chunks from structured answers.
        answers = response.get("answers")
        if isinstance(answers, dict):
            for q_idx, (_q_key, answer) in enumerate(
                answers.items(), start=1
            ):
                chunk_text = scrub_open_text(str(answer))[0] if answer is not None else ""
                if not chunk_text:
                    continue
                db.append_evidence_chunk(
                    {
                        "id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "source_id": source_id,
                        "locator": f"survey:{survey_id}/q{q_idx}",
                        "text": chunk_text,
                        "content_hash": None,
                    }
                )
        elif isinstance(answers, list):
            for q_idx, answer in enumerate(answers, start=1):
                chunk_text = scrub_open_text(str(answer))[0] if answer is not None else ""
                if not chunk_text:
                    continue
                db.append_evidence_chunk(
                    {
                        "id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "source_id": source_id,
                        "locator": f"survey:{survey_id}/q{q_idx}",
                        "text": chunk_text,
                        "content_hash": None,
                    }
                )
        elif raw_text:
            # No structured answers — persist the full raw text as one chunk.
            db.append_evidence_chunk(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "source_id": source_id,
                    "locator": f"survey:{survey_id}/q1",
                    "text": raw_text,
                    "content_hash": None,
                }
            )

        source_ids.append(source_id)

    return source_ids


def ingest_interview(
    db: Any,
    run_id: str,
    transcript: list[dict[str, Any]],
    *,
    interview_id: str,
) -> list[str]:
    """Ingest an interview transcript as ``source_type="interview"`` artifacts.

    The transcript is a list of segment dicts (one per speaker turn or logical
    section). Each segment with non-empty text becomes a SourceDoc row and an
    evidence chunk with locator ``interview:<interview_id>/seg<n>``.

    Privacy: every ``speaker_meta`` dict is passed through
    :func:`anonymize_respondent_meta` before it reaches the DB.
    Additionally, segment ``text`` (stored as both ``raw_text`` and chunk
    text) has email and phone patterns redacted before persistence.
    Free-text CONTENT is preserved except for redacted email/phone PII;
    name tokens in segment text are NOT removed (segment content is evidence
    material — NER-based name removal in free text is a known, documented
    limitation).

    Args:
        db: A :class:`~mingjing.db.Database` instance.
        run_id: The owning run id.
        transcript: A list of segment dicts. Recognised keys:

            - ``speaker_meta`` (dict) — anonymized automatically.
            - ``text`` (str) — the spoken/written content (required; segments
              with empty text are skipped).
            - ``title`` (str) — optional descriptive title.

        interview_id: A stable caller-assigned interview identifier
            (e.g. ``"INT-1"``).

    Returns:
        A list of persisted ``source_id`` strings (one per non-empty segment).
    """
    source_ids: list[str] = []
    now = time.time()

    for seg_idx, segment in enumerate(transcript, start=1):
        text = segment.get("text") or ""
        if not text:
            continue

        redacted_text = _redact_string(text)
        source_id = str(uuid.uuid4())
        title = (
            segment.get("title")
            or f"Interview {interview_id} segment {seg_idx}"
        )
        anon_meta = anonymize_respondent_meta(
            segment.get("speaker_meta") or {}
        )

        db.append_source(
            {
                "id": source_id,
                "run_id": run_id,
                # Same collapse rule as the survey path: one interview = one
                # independent voice regardless of segment count.
                "url": f"interview:{interview_id}/s{seg_idx}",
                "title": title,
                "source_type": "interview",
                "source_mode": "INGESTED",
                "fetched_at": now,
                "content_hash": None,
                "raw_text": redacted_text,
                "meta_json": json.dumps(anon_meta, ensure_ascii=False),
            }
        )

        db.append_evidence_chunk(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "source_id": source_id,
                "locator": f"interview:{interview_id}/seg{seg_idx}",
                "text": redacted_text,
                "content_hash": None,
            }
        )

        source_ids.append(source_id)

    return source_ids
