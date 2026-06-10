"""Survey design and open-text PII scrubbing for competitive-analysis questionnaires.

This module provides two capabilities:

1. ``design_survey`` — pure, deterministic questionnaire generator that produces a
   structured 10-question competitive-analysis survey parameterised by competitor
   name and research goal. No network or LLM calls; demo-robust.

2. ``scrub_open_text`` — a STRONGER PII scrubber intended ONLY for survey open-text
   responses (Q5 NPS-rationale, Q10 open feedback).  Unlike ``ingest._redact_string``
   (which intentionally preserves names in evidence content), this scrubber is a
   best-effort regex pipeline that also catches CN national IDs, CN mobile/landline
   numbers, name tokens introduced by common trigger phrases, and 6-digit postal
   codes.

Important: ``scrub_open_text`` MUST NOT be used on evidence content (e.g. scraped
articles, interview transcripts) where preserving names is intentional.  It is only
applied to user-supplied free-text survey answers that are specifically marked
``pii_scrub=True`` in the questionnaire schema.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Re-use compiled patterns from ingest (email + international phone)
# ---------------------------------------------------------------------------
from .ingest import _EMAIL_PATTERN, _PHONE_PATTERN

# ---------------------------------------------------------------------------
# Additional PII patterns for the stronger open-text scrubber
# ---------------------------------------------------------------------------

# CN 18-digit national ID: 17 digits followed by a digit or X/x.
# Must run BEFORE the 6-digit ZIP pattern so an 18-digit string is
# consumed as a whole rather than having its first 6 digits matched as ZIP.
_CN_ID_PATTERN = re.compile(r"\b\d{17}[\dXx]\b")

# CN mobile (1[3-9] + 9 digits) and landline (area-code + 7-8 digits).
# Separate from the international _PHONE_PATTERN to ensure CN-local formats
# are reliably caught even when written without country code.
_CN_MOBILE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
_CN_LANDLINE_PATTERN = re.compile(r"\b0\d{2,3}-?\d{7,8}\b")

# Name trigger phrases: capture the token immediately following the phrase.
# The captured group (index 1) is the name token; the trigger phrase itself
# is kept while the name is replaced with [NAME].
# Only high-precision triggers. The broad English "I am"/"I'm" were dropped:
# in survey feedback they precede an adjective far more often than a name
# ("I am happy"), so they caused over-redaction. Known regex-not-NER limit: a
# multi-word name only has its FIRST token redacted
# ("my name is John Smith" → "my name is [NAME] Smith").
_NAME_TRIGGER_PATTERN = re.compile(
    r"(?:我叫|我是|my name is)\s*([^\s,，。.]{1,20})",
    re.IGNORECASE,
)

# 6-digit postal/ZIP code (CN postal codes are exactly 6 digits).
# Applied LAST so it cannot accidentally match a substring of an already-
# substituted longer token (placeholders like [EMAIL] contain no digits).
_ZIP_PATTERN = re.compile(r"\b\d{6}\b")

# ---------------------------------------------------------------------------
# Survey question template
# ---------------------------------------------------------------------------

_QUESTION_TEMPLATE: list[dict[str, Any]] = [
    {
        "id": "q1",
        "dimension": "qualification",
        "type": "single",
        "text": "您目前是否正在使用 {competitor}？",
        "options": ["是，主要使用", "是，偶尔使用", "曾经使用但已停止", "从未使用"],
        "field": None,
    },
    {
        "id": "q2",
        "dimension": "overall_satisfaction",
        "type": "likert5",
        "text": "您对 {competitor} 的整体满意度如何？",
        "scale": {"min": 1, "max": 5, "labels": ["非常不满意", "不满意", "一般", "满意", "非常满意"]},
        "field": "user_sentiment",
    },
    {
        "id": "q3",
        "dimension": "feature_satisfaction",
        "type": "likert5",
        "text": "针对您研究目标（{goal}），{competitor} 的功能满足程度如何？",
        "scale": {"min": 1, "max": 5, "labels": ["远未满足", "未满足", "基本满足", "满足", "完全满足"]},
        "field": "feature_tree",
    },
    {
        "id": "q4",
        "dimension": "nps",
        "type": "nps",
        "text": "您向同事或朋友推荐 {competitor} 的可能性有多大？（0 = 极不可能，10 = 极有可能）",
        "scale": {"min": 0, "max": 10},
        "field": "user_sentiment",
    },
    {
        "id": "q5",
        "dimension": "nps_rationale",
        "type": "open",
        "text": "请简要说明您给出上述推荐分数的原因。",
        "pii_scrub": True,
        "field": "user_sentiment",
    },
    {
        "id": "q6",
        "dimension": "feature_gaps",
        "type": "multi",
        "text": "与竞品相比，{competitor} 在哪些方面存在明显不足？（可多选）",
        "options": ["功能完整性", "性能/速度", "易用性", "价格", "客户支持", "集成能力", "数据安全", "其他"],
        "field": "feature_tree",
    },
    {
        "id": "q7",
        "dimension": "switching_intent",
        "type": "single",
        "text": "未来 12 个月内，您考虑从 {competitor} 切换到其他产品的可能性？",
        "options": ["极有可能", "有可能", "不确定", "不太可能", "极不可能"],
        "field": "pricing_model",
    },
    {
        "id": "q8",
        "dimension": "willingness_to_pay",
        "type": "single",
        "text": "您愿意为与 {competitor} 同等功能的产品每月支付多少费用？",
        "options": ["< ¥50", "¥50–¥200", "¥200–¥500", "¥500–¥1000", "> ¥1000", "不愿付费"],
        "field": "pricing_model",
    },
    {
        "id": "q9",
        "dimension": "switching_barrier",
        "type": "single",
        "text": "阻碍您切换产品的最主要障碍是什么？",
        "options": ["迁移成本高", "学习曲线陡峭", "团队习惯难改变", "合同锁定期", "无合适替代品", "其他"],
        "field": "user_persona",
    },
    {
        "id": "q10",
        "dimension": "open_feedback",
        "type": "open",
        "text": "关于 {competitor} 及您的研究目标（{goal}），您还有哪些意见或建议？",
        "pii_scrub": True,
        "field": "user_sentiment",
    },
]

_RESPONSE_SCHEMA: dict[str, Any] = {
    "q1": {"type": "string", "enum": ["是，主要使用", "是，偶尔使用", "曾经使用但已停止", "从未使用"]},
    "q2": {"type": "integer", "minimum": 1, "maximum": 5},
    "q3": {"type": "integer", "minimum": 1, "maximum": 5},
    "q4": {"type": "integer", "minimum": 0, "maximum": 10},
    "q5": {"type": "string"},
    "q6": {"type": "array", "items": {"type": "string"}},
    "q7": {"type": "string"},
    "q8": {"type": "string"},
    "q9": {"type": "string"},
    "q10": {"type": "string"},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def design_survey(
    competitor: str,
    goal: str,
    *,
    n: int = 10,
    survey_id: str = "SV-1",
) -> dict[str, Any]:
    """Generate a structured competitive-analysis questionnaire.

    Produces a deterministic, LLM-free 10-question survey template for
    competitive analysis, parameterised by the target competitor and
    research goal. The result encodes survey-design best practices:
    qualification gate (Q1), satisfaction scales (Q2–Q3), NPS + rationale
    (Q4–Q5), feature-gap multi-select (Q6), switching intent and WTP
    (Q7–Q8), barrier analysis (Q9), and open feedback (Q10).

    Questions Q5 and Q10 are open-text and carry ``pii_scrub=True``,
    indicating that ``scrub_open_text`` MUST be applied before persisting
    any free-text response to those questions.

    Args:
        competitor: Name of the product/company being analysed (e.g.
            ``"Notion"``).  Interpolated into question text where natural.
        goal: Research objective (e.g. ``"compare AI agents"``).
            Interpolated into Q3 and Q10 text.
        n: Number of questions to return (1–10, default 10).  Returns the
            first ``n`` questions of the fixed template.
        survey_id: Caller-assigned stable survey identifier
            (default ``"SV-1"``).

    Returns:
        A dict with keys:
        - ``survey_id`` — echoed from argument.
        - ``competitor`` — echoed from argument.
        - ``goal`` — echoed from argument.
        - ``questions`` — list of question dicts (at most ``n`` items).
        - ``response_schema`` — JSON-Schema-like dict keyed by question id.
    """
    n = max(1, min(n, len(_QUESTION_TEMPLATE)))
    questions: list[dict[str, Any]] = []
    for template_q in _QUESTION_TEMPLATE[:n]:
        q: dict[str, Any] = {}
        for k, v in template_q.items():
            if isinstance(v, str):
                q[k] = v.format(competitor=competitor, goal=goal)
            else:
                q[k] = v
        questions.append(q)

    # Restrict response_schema to only the returned questions.
    question_ids = {q["id"] for q in questions}
    response_schema = {k: v for k, v in _RESPONSE_SCHEMA.items() if k in question_ids}

    return {
        "survey_id": survey_id,
        "competitor": competitor,
        "goal": goal,
        "questions": questions,
        "response_schema": response_schema,
    }


def scrub_open_text(text: str | None) -> tuple[str, int]:
    """Scrub PII from survey open-text answers.

    A stronger, regex best-effort scrubber designed ONLY for survey
    free-text responses (questions marked ``pii_scrub=True`` in the
    survey schema, e.g. Q5 NPS rationale, Q10 open feedback).

    WARNING: Do NOT apply to evidence content (scraped articles, interview
    transcripts). Evidence content must preserve names for analysis;
    use ``ingest._redact_string`` for that path instead.

    Substitutions applied (in this order to avoid overlap issues):

    1. Email addresses → ``[EMAIL]``  (reused from ``ingest._EMAIL_PATTERN``)
    2. CN national ID (18 chars) → ``[ID]``  (before ZIP to consume all 18 digits)
    3. CN mobile ``1[3-9]XXXXXXXXX`` → ``[PHONE]``
    4. CN landline ``0XXX-XXXXXXX`` → ``[PHONE]``
    5. International phone (``ingest._PHONE_PATTERN``) → ``[PHONE]``
    6. Name tokens following trigger phrases (我叫/我是/my name is)
       → trigger phrase kept, name token replaced with ``[NAME]``
       (``I am``/``I'm`` are intentionally excluded — see the regex comment — to
       avoid redacting adjectives like "I am happy".)
    7. 6-digit postal codes → ``[ZIP]``  (last, so IDs/phones already gone)

    Args:
        text: Raw open-text survey answer.

    Returns:
        A tuple ``(scrubbed_text, pii_tokens_redacted_count)`` where
        ``pii_tokens_redacted_count`` is the total number of individual PII
        tokens replaced across all pattern types.
    """
    # Guard the empty/None case: a skipped open question yields None/"" on this
    # compliance path; never crash mid-pipeline scrubbing other fields.
    if not text:
        return (text or "", 0)

    count = 0
    result = text

    # 1. Email
    new_result, n = _EMAIL_PATTERN.subn("[EMAIL]", result)
    count += n
    result = new_result

    # 2. CN national ID (18 chars) — BEFORE zip to avoid partial match
    new_result, n = _CN_ID_PATTERN.subn("[ID]", result)
    count += n
    result = new_result

    # 3. CN mobile
    new_result, n = _CN_MOBILE_PATTERN.subn("[PHONE]", result)
    count += n
    result = new_result

    # 4. CN landline
    new_result, n = _CN_LANDLINE_PATTERN.subn("[PHONE]", result)
    count += n
    result = new_result

    # 5. International phone (from ingest) — after CN-specific patterns
    new_result, n = _PHONE_PATTERN.subn("[PHONE]", result)
    count += n
    result = new_result

    # 6. Name trigger phrases — keep trigger, replace name token
    def _replace_name(m: re.Match[str]) -> str:
        full = m.group(0)
        return full[: m.start(1) - m.start(0)] + "[NAME]"

    new_result, n = _NAME_TRIGGER_PATTERN.subn(_replace_name, result)
    count += n
    result = new_result

    # 7. 6-digit ZIP — last, after all longer digit-runs are consumed
    new_result, n = _ZIP_PATTERN.subn("[ZIP]", result)
    count += n
    result = new_result

    return result, count
