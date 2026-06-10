"""Curated, competitor-keyed survey/interview fixture.

Per-field answer text is REAL-shaped demo data (we never synthesize responses for
arbitrary competitors). Each field's value is a self-contained string usable as a
source ``raw_text`` so a claim's value can be grounded in it (value ⊆ text). Keyed
to the demo competitor the corpus already uses (Notion). PII is embedded in
open-text so ``scrub_open_text`` visibly does work.
"""

from typing import Any

# field -> self-contained answer text (the groundable content for that field).
DEMO_FIXTURE: dict[str, dict[str, Any]] = {
    "notion": {
        "survey": {
            "survey_id": "SV-1",
            "fields": {
                # Open-text feedback carrying PII (email + phone) so the survey
                # open-text scrubber (scrub_open_text) demonstrably redacts it
                # to [EMAIL]/[PHONE] while the groundable sentiment survives.
                "user_sentiment": (
                    "Across 30 surveyed Notion users overall satisfaction is high; "
                    "respondents praise flexibility but several call the mobile app slow. "
                    "One respondent (zhangwei@example.com, reached at 138-0013-8000) "
                    "wrote that the mobile app is slow."
                ),
                "feature_tree": (
                    "Respondents rate databases and templates as Notion's strongest "
                    "features; AI writing assist is the most-requested gap."
                ),
                "pricing_model": (
                    "Most respondents report the Pro plan at $10/mo and consider it fair value."
                ),
            },
        },
        "interview": {
            "interview_id": "IV-1",
            "fields": {
                "user_persona": (
                    "Interviewee, an operations manager, describes the core Notion "
                    "persona as a cross-functional team lead consolidating docs and tasks."
                ),
            },
        },
    },
    "linear": {
        "survey": {
            "survey_id": "SV-2",
            "fields": {
                # Corroborates the SAME pricing value the official linear.app/pricing
                # page states (Basic at $10 per user/month), giving pricing_model a
                # SECOND authoritative domain ("survey") so scoring.strength reaches
                # "strong" (official + survey = two distinct authoritative domains).
                # Self-contained: the groundable value substring lives in this text.
                "pricing_model": (
                    "Most surveyed Linear users are on the Basic plan at $10 per "
                    "user/month and consider it fair value for a fast issue tracker."
                ),
            },
        },
    },
}


def fixture_for(competitor: str | None) -> dict[str, Any] | None:
    """Return the curated fixture for ``competitor`` (case-insensitive), or None."""
    if not competitor:
        return None
    return DEMO_FIXTURE.get(competitor.strip().lower())
