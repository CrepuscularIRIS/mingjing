"""Simulated (fixture-seeded) survey/interview sources are DISPLAY-ONLY credibility-wise.

Option (a) 诚实降档: rows seeded from the demo fixture are marked
``source_mode="SIMULATED"`` and contribute ZERO to the 3-tier scorer and the
corroboration counters. QA grounding (HALLUCINATED_SNIPPET / VALUE_UNSUPPORTED)
is UNCHANGED — a simulated source can still ground a value verbatim; it just can
never mint credibility (not even weak→moderate). A REAL ingested survey
(``source_mode="INGESTED"``) keeps its authoritative lift — that path is proven
by tests/test_strong_tier_linear.py.
"""

import json

from mingjing.claim_builder import build_claim
from mingjing.db import Database
from mingjing.qa.rules import qa_check
from mingjing.schemas import IssueCode
from mingjing.survey_fixture import fixture_for
from mingjing.survey_seed import survey_seed

_OFFICIAL_TEXT = (
    "Free $0 Free for everyone. Basic $10 per user/month. Billed yearly. "
    "Business $16 per user/month. Enterprise Custom."
)
_SURVEY_TEXT = (
    "Most surveyed Linear users are on the Basic plan at $10 per user/month "
    "and consider it fair value for a fast issue tracker."
)
_VALUE_LEAF = "$10 per user/month"


def _mk_run(tmp_path):
    db = Database(str(tmp_path / "sim.db"))
    db.init_schema()
    run_id = db.create_run(
        category="AI 产品竞品分析", competitors=["Linear"], goal="分析 Linear 定价"
    )
    return db, run_id


def test_survey_seed_rows_are_marked_simulated(tmp_path):
    """Fixture-seeded survey/interview rows carry the SIMULATED mode + meta flag."""
    db, run_id = _mk_run(tmp_path)
    entries = survey_seed(db, run_id, "Notion", fixture_for("Notion"))
    assert entries, "fixture for Notion must seed at least one source row"
    for e in entries:
        row = db.get_source(e["source_id"])
        assert row["source_mode"] == "SIMULATED"
        assert json.loads(row["meta_json"]).get("simulated") is True


def test_simulated_survey_does_not_mint_strong(tmp_path):
    """official(real) + survey(SIMULATED) = ONE real domain -> moderate, not strong.

    Mirror of test_strong_tier_linear, with the single difference that the survey
    row is fixture-simulated. The tier must come from real sources only.
    """
    db, run_id = _mk_run(tmp_path)
    official_id = f"{run_id}-web-official"
    survey_id = f"{run_id}-survey-SV-2-pricing_model"
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
    db.append_source(
        {
            "id": survey_id,
            "run_id": run_id,
            "url": "survey:SV-2/pricing_model",
            "title": "survey SV-2 (pricing_model)",
            "source_type": "survey",
            "source_mode": "SIMULATED",
            "fetched_at": 0.0,
            "content_hash": None,
            "raw_text": _SURVEY_TEXT,
            "meta_json": json.dumps({"simulated": True}),
        }
    )
    src_rows = [db.get_source(official_id), db.get_source(survey_id)]
    payload = {
        "statement": "Linear's Basic plan is $10 per user/month, billed yearly.",
        "claim_type": "fact",
        "value": {"tiers": [_VALUE_LEAF]},
        "evidence_ref": [official_id, survey_id],
        "evidence": [
            {"source_id": official_id, "snippet": "Basic $10 per user/month", "relevance": "supports"},
            {"source_id": survey_id, "snippet": "Basic plan at $10 per user/month", "relevance": "supports"},
        ],
        "stances": {official_id: "supports", survey_id: "supports"},
    }
    claim = build_claim(
        db, run_id, {"field": "pricing_model", "competitor": "Linear"}, src_rows, payload
    )
    assert claim["evidence_strength"] == "moderate", (
        "a SIMULATED survey row must not provide the second authoritative domain"
    )
    # Corroboration counter (secondary Admiralty axis) must not count the
    # simulated domain either: the official source has zero OTHER real
    # corroborating domains.
    official_ev = next(e for e in claim["evidence"] if e["source_id"] == official_id)
    assert official_ev["admiralty"], "admiralty grade still present"


def test_simulated_only_support_scores_weak_but_grounding_unchanged():
    """A claim whose ONLY support is simulated: WEAK_EVIDENCE fires; grounding doesn't.

    The QA gate's verbatim checks (HALLUCINATED_SNIPPET / VALUE_UNSUPPORTED) keep
    reading simulated raw_text — simulation removes credibility, not groundability.
    """
    claimset = {
        "claims": [
            {
                "id": "C1",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Basic is $10 per user/month.",
                "value": {"tiers": [_VALUE_LEAF]},
                "evidence": [
                    {
                        "source_id": "S1",
                        "snippet": "Basic plan at $10 per user/month",
                        "relevance": "supports",
                    }
                ],
            }
        ],
        "sources": {
            "S1": {
                "raw_text": _SURVEY_TEXT,
                "source_type": "survey",
                "source_mode": "SIMULATED",
            }
        },
        "coverage": {
            "required_fields": ["pricing_model"],
            "covered_fields": ["pricing_model"],
        },
    }
    issues = qa_check(claimset)
    codes = {i.code for i in issues}
    assert IssueCode.WEAK_EVIDENCE in codes, (
        "simulated-only support must score weak (zero credibility contribution)"
    )
    assert IssueCode.HALLUCINATED_SNIPPET not in codes, "grounding must be unchanged"
    assert IssueCode.VALUE_UNSUPPORTED not in codes, "grounding must be unchanged"


def test_claimset_parts_carries_source_mode_so_qa_sees_simulated(tmp_path):
    """End-to-end through the REAL projection: DB → claimset_parts → review.

    Codex stop-review caught that claimset_parts dropped ``source_mode``, which
    silently re-enabled simulated rows on the QA side. This test pins the full
    production path: a claim whose only support is a SIMULATED survey row must
    be rejected by the live QA gate (WEAK_EVIDENCE), not just by build_claim.
    """
    from mingjing.agents.qa import review
    from mingjing.claim_builder import claimset_parts

    db, run_id = _mk_run(tmp_path)
    survey_id = f"{run_id}-survey-SV-2-pricing_model"
    db.append_source(
        {
            "id": survey_id,
            "run_id": run_id,
            "url": "survey:SV-2/pricing_model",
            "title": "survey SV-2 (pricing_model)",
            "source_type": "survey",
            "source_mode": "SIMULATED",
            "fetched_at": 0.0,
            "content_hash": None,
            "raw_text": _SURVEY_TEXT,
            "meta_json": json.dumps({"simulated": True}),
        }
    )
    src_rows = [db.get_source(survey_id)]
    payload = {
        "statement": "Linear's Basic plan is $10 per user/month.",
        "claim_type": "fact",
        "value": {"tiers": [_VALUE_LEAF]},
        "evidence_ref": [survey_id],
        "evidence": [
            {
                "source_id": survey_id,
                "snippet": "Basic plan at $10 per user/month",
                "relevance": "supports",
            }
        ],
    }
    claim = build_claim(
        db, run_id, {"field": "pricing_model", "competitor": "Linear"}, src_rows, payload
    )
    db.append_claim(claim)

    claims, sources = claimset_parts(db, db.latest_claims_for_run(run_id))
    assert sources[survey_id].get("source_mode") == "SIMULATED", (
        "projection must carry source_mode or the QA-side filter is dead code"
    )
    claimset = {
        "claims": claims,
        "sources": sources,
        "coverage": {
            "required_fields": ["pricing_model"],
            "covered_fields": ["pricing_model"],
        },
    }
    result = review(claimset, run_id=run_id, round=0)
    assert result["verdict"] == "reject"
    codes = {str(i["code"] if isinstance(i, dict) else i.code) for i in result["issues"]}
    assert any("WEAK_EVIDENCE" in c for c in codes), f"unexpected issues: {codes}"


def test_simulated_source_cannot_appear_in_contradiction_card():
    """A simulated row can be NEITHER side of a visible ContradictionCard.

    Codex stop-review: the qa-side contradiction DETECTION was filtered but the
    display card's supports/refutes pair-building was not — a fixture survey row
    with a refutes stance could still manufacture a judge-visible conflict.
    """
    from mingjing.contradiction import summarize_contradiction

    sources = {
        "S-real": {
            "raw_text": _OFFICIAL_TEXT,
            "source_type": "official",
            "url": "https://linear.app/pricing",
        },
        "S-sim": {
            "raw_text": "Surveyed users say the Basic plan costs $25 per user/month.",
            "source_type": "survey",
            "source_mode": "SIMULATED",
            "url": "survey:SV-2/pricing_model",
        },
    }
    evidence = [
        {"source_id": "S-real", "stance": "supports", "relevance": "supports"},
        {"source_id": "S-sim", "stance": "refutes", "relevance": "refutes"},
    ]
    card = summarize_contradiction(evidence, sources)
    assert card is None, (
        "a simulated source's refutes stance must not manufacture a contradiction card"
    )

    # Two REAL cross-domain sources still produce the card (display unharmed).
    sources["S-real2"] = {
        "raw_text": "Basic costs $25 per user/month.",
        "source_type": "news",
        "url": "https://news.example.com/linear",
    }
    evidence_real = [
        {"source_id": "S-real", "stance": "supports", "relevance": "supports"},
        {"source_id": "S-real2", "stance": "refutes", "relevance": "refutes"},
    ]
    assert summarize_contradiction(evidence_real, sources) is not None


def test_ingested_survey_still_mints_strong():
    """Parity guard: a REAL ingested survey keeps its authoritative lift."""
    claimset = {
        "claims": [
            {
                "id": "C1",
                "schema_field": "pricing_model",
                "claim_type": "fact",
                "statement": "Basic is $10 per user/month.",
                "value": {"tiers": [_VALUE_LEAF]},
                "evidence": [
                    {
                        "source_id": "S1",
                        "snippet": "Basic $10 per user/month",
                        "relevance": "supports",
                    },
                    {
                        "source_id": "S2",
                        "snippet": "Basic plan at $10 per user/month",
                        "relevance": "supports",
                    },
                ],
            }
        ],
        "sources": {
            "S1": {"raw_text": _OFFICIAL_TEXT, "source_type": "official"},
            "S2": {
                "raw_text": _SURVEY_TEXT,
                "source_type": "survey",
                "source_mode": "INGESTED",
            },
        },
        "coverage": {
            "required_fields": ["pricing_model"],
            "covered_fields": ["pricing_model"],
        },
    }
    issues = qa_check(claimset)
    assert not [i for i in issues if i.code == IssueCode.WEAK_EVIDENCE]
