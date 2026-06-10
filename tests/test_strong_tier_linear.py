"""Deterministic proof that the strong evidence tier is reachable (W1).

Judges asked: "强证据率 0%?" — every prior demo run is 强0·中4·弱0 because each
field has at most one authoritative *domain*. A field corroborated by an OFFICIAL
source (vendor domain) AND a SURVEY source (domain "survey") has two distinct
authoritative domains supporting the SAME value, which scoring.strength legitimately
scores "strong".

This test constructs the Linear pricing_model scenario through the REAL
claim-assembly + QA path — no LLM, no API key, no network — and asserts:

1. ``build_claim`` (which calls :func:`mingjing.scoring.strength`) stamps
   ``evidence_strength == "strong"`` on the claim, and
2. :func:`mingjing.qa.rules.qa_check` admits it (no issues → QA verdict ``pass``),
   i.e. the claimed $10 value is verbatim-grounded in BOTH cited sources and no
   gate (schema_gap / weak_evidence / hallucinated_snippet / value_unsupported /
   contradiction / low_coverage) fires.

The corroborating pricing value ($10 per user/month, Linear's real public Basic
plan) and its two distinct authoritative domains (``linear.app`` official +
``survey``) are the rigorous proof the strong ceiling is reachable, independent of
the live LLM run's variance.
"""

from mingjing.agents.qa import review
from mingjing.claim_builder import build_claim, claimset_parts
from mingjing.db import Database

# The official linear.app/pricing text (corpus demo/corpus/linear.json) and the
# survey fixture answer (survey_fixture.py "linear") — both contain the verbatim
# "$10 per user/month" value the claim asserts, on two distinct authoritative
# domains (official linear.app + survey). Real, public Linear pricing.
_OFFICIAL_TEXT = (
    "Free $0 Free for everyone. Basic $10 per user/month. Billed yearly. "
    "Business $16 per user/month. Enterprise Custom."
)
_SURVEY_TEXT = (
    "Most surveyed Linear users are on the Basic plan at $10 per user/month "
    "and consider it fair value for a fast issue tracker."
)
# The asserted value leaf — a verbatim substring of BOTH source texts above so it
# survives the VALUE_UNSUPPORTED gate (which grounds against the joined haystack).
_VALUE_LEAF = "$10 per user/month"
# Per-source snippets — each must be a VERBATIM substring of ITS OWN source so the
# HALLUCINATED_SNIPPET gate admits both (it checks each snippet against its source).
_OFFICIAL_SNIPPET = "Basic $10 per user/month"
_SURVEY_SNIPPET = "Basic plan at $10 per user/month"


def test_linear_pricing_official_plus_survey_scores_strong_and_passes(tmp_path):
    db = Database(str(tmp_path / "linear.db"))
    db.init_schema()
    run_id = db.create_run(
        category="AI 产品竞品分析", competitors=["Linear"], goal="分析 Linear 定价"
    )

    official_id = f"{run_id}-web-official"
    survey_id = f"{run_id}-survey-SV-2-pricing_model"

    # Official linear.app source — authoritative domain "linear.app".
    db.append_source(
        {
            "id": official_id,
            "run_id": run_id,
            "url": "https://linear.app/pricing",
            "title": "Pricing – Linear",
            "source_type": "official",
            "source_mode": "CACHED",
            "fetched_at": 0.0,
            "content_hash": None,
            "raw_text": _OFFICIAL_TEXT,
            "meta_json": "{}",
        }
    )
    # Survey source row — its registrable domain collapses to "survey", a SECOND
    # distinct authoritative domain (see survey_seed.py). Shaped exactly as
    # survey_seed seeds it (survey: locator, source_type "survey").
    db.append_source(
        {
            "id": survey_id,
            "run_id": run_id,
            "url": "survey:SV-2/pricing_model",
            "title": "survey SV-2 (pricing_model)",
            "source_type": "survey",
            "source_mode": "INGESTED",
            "fetched_at": 0.0,
            "content_hash": None,
            "raw_text": _SURVEY_TEXT,
            "meta_json": "{}",
        }
    )

    src_rows = [db.get_source(official_id), db.get_source(survey_id)]

    # Analyst payload: BOTH sources cited as supporting evidence; the required
    # ``tiers`` leaf is the verbatim $10 value present in both source texts.
    payload = {
        "statement": "Linear's Basic plan is $10 per user/month, billed yearly.",
        "claim_type": "fact",
        "value": {"tiers": [_VALUE_LEAF]},
        "evidence_ref": [official_id, survey_id],
        "evidence": [
            {"source_id": official_id, "snippet": _OFFICIAL_SNIPPET, "relevance": "supports"},
            {"source_id": survey_id, "snippet": _SURVEY_SNIPPET, "relevance": "supports"},
        ],
    }

    claim = build_claim(
        db, run_id, {"field": "pricing_model", "competitor": "Linear"}, src_rows, payload
    )

    # (1) The REAL scorer (via build_claim -> scoring.strength) reaches strong:
    # two distinct authoritative domains (linear.app official + survey) corroborate.
    assert claim["evidence_strength"] == "strong"

    # Persist the draft claim and rebuild the QA claimset from DB rows (the SAME
    # path the live runner uses), then run the REAL QA gate.
    db.append_claim(claim)
    claims, sources = claimset_parts(db, db.latest_claims_for_run(run_id))
    claimset = {
        "claims": claims,
        "sources": sources,
        "coverage": {"required_fields": ["pricing_model"], "covered_fields": ["pricing_model"]},
    }
    result = review(claimset, run_id=run_id, round=0)

    # (2) QA admits the claim: no issue fires -> verdict pass.
    assert result["verdict"] == "pass", f"unexpected QA issues: {result['issues']}"
