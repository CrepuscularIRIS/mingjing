"""5-field fan-out proof + survey-as-source smoke test (Task 17, Deliverable 2).

Drives ``build_graph`` with injected ``collect_fn`` / ``analyze_fn`` across ALL 5
schema fields for ONE competitor and verifies:

1. All 5 fields appear in the final latest-claims set, each schema-valid.
2. ``feature_tree`` has genuine structural depth (not a hollow one-liner):
   ≥2 ``categories``, non-empty ``features`` mapping, ``depth`` ≥ 2.
3. Each field's claim is backed by ≥1 real persisted source.
4. The run reaches the ``write`` phase with a non-empty report.
5. A pre-seeded survey source for ``user_sentiment`` can back a claim that
   the transparent scorer rates at least ``moderate`` / ``strong``.

All fixtures are SYNTHETIC — no network, no live LLM.
"""

import json

import pytest

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph
from mingjing.ingest import ingest_survey
from mingjing.qa.rules import qa_check
from mingjing.scoring import strength as score_strength

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPETITOR = "Orion"  # distinct from existing test fixtures

# All 5 schema fields that the demo requires.
ALL_FIELDS = [
    "pricing_model",
    "user_sentiment",
    "feature_tree",
    "user_persona",
    "swot",
]

# A statement substring that appears in BOTH fixture texts so the
# HALLUCINATED_SNIPPET gate never fires.
STATEMENT = "Orion delivers competitive value across all tiers"

# --- Fixture source A: on the competitor's own domain (→ "official") ---
# infer_source_type classifies a host as "official" when the competitor
# token ("orion") is a full dot-label of the hostname.
SOURCE_A_URL = "https://orion.example.com/about"
SOURCE_A_TEXT = (
    f"Official Orion site: {STATEMENT}. "
    "Pricing starts at $5/mo with a free tier. Monthly billing available. "
    "Enterprise $50/mo plan and Pro $10/mo plan offered. "
    "Collaboration features: real-time editing, comments, mentions. "
    "Analytics features: dashboards, custom reports. "
    "Integrations: Slack, Jira, GitHub, Zapier. "
    "Orion is positive for user sentiment with easy onboarding and competitive pricing. "
    "Mobile app limitations noted. "
    "Target users: SMB Operations Manager, Enterprise IT Admin. "
    "Supports workflow automation and compliance needs. "
    "Reduces manual data entry and poor visibility for teams. "
    "Strengths: robust API, strong brand recognition. "
    "Weaknesses: limited mobile app, high enterprise pricing. "
    "Opportunities: APAC market expansion, AI feature integrations. "
    "Threats: new SaaS entrants, commoditization of core features."
)

# --- Fixture source B: independent corroborating source ---
SOURCE_B_URL = "https://g2crowd.net/orion-review"
SOURCE_B_TEXT = (
    f"G2 review: {STATEMENT}. "
    "The Pro tier at $10/mo is competitive. Pro $10/mo plan available. "
    "Enterprise $50/mo available for large teams. "
    "Users praise the onboarding flow, easy onboarding experience. "
    "Feature depth includes 15+ integrations. "
    "Key persona: operations manager in mid-market. SMB Operations Manager in focus."
)

FIXTURE_SOURCES = [
    {
        "url": SOURCE_A_URL,
        "title": "Orion official",
        "text": SOURCE_A_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "fanout-A",
        "content_hash": "hashA",
        "fetched_at": 1.0,
    },
    {
        "url": SOURCE_B_URL,
        "title": "G2 Orion review",
        "text": SOURCE_B_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "fanout-B",
        "content_hash": "hashB",
        "fetched_at": 2.0,
    },
]

# Survey-backed sentiment statement — verbatim substring of survey raw_text.
SENTIMENT_STATEMENT = "Users report high satisfaction with Orion overall sentiment"

# ---------------------------------------------------------------------------
# Schema-valid claim values per field
# ---------------------------------------------------------------------------

# Map each field to a schema-valid value dict (all required sub-fields populated).
_VALID_VALUES: dict[str, dict] = {
    "pricing_model": {
        "tiers": ["Free", "Pro $10/mo", "Enterprise $50/mo"],
        "free_tier": True,
        "currency": "USD",
        "billing_period": "monthly",
    },
    "user_sentiment": {
        "overall": "positive",
        "positives": ["easy onboarding", "competitive pricing"],
        "negatives": ["mobile app limitations"],
        "sample_size": 120,
    },
    "feature_tree": {
        # Must satisfy: ≥2 categories, non-empty features, depth ≥ 2.
        "categories": ["Collaboration", "Analytics", "Integrations"],
        "features": {
            "Collaboration": ["real-time editing", "comments", "mentions"],
            "Analytics": ["dashboards", "custom reports"],
            "Integrations": ["Slack", "Jira", "GitHub", "Zapier"],
        },
        "depth": 3,
    },
    "user_persona": {
        "segments": ["SMB Operations Manager", "Enterprise IT Admin"],
        "needs": ["workflow automation", "compliance"],
        "pain_points": ["manual data entry", "poor visibility"],
    },
    "swot": {
        "strengths": ["robust API", "strong brand recognition"],
        "weaknesses": ["limited mobile app", "high enterprise pricing"],
        "opportunities": ["APAC market expansion", "AI feature integrations"],
        "threats": ["new SaaS entrants", "commoditization of core features"],
    },
}

# Statement per field — verbatim substring of SOURCE_A_TEXT or SOURCE_B_TEXT.
# Used to satisfy the HALLUCINATED_SNIPPET check (snippet must be in raw_text).
_STATEMENTS: dict[str, str] = {
    "pricing_model": "Pricing starts at $5/mo with a free tier",
    "user_sentiment": STATEMENT,
    "feature_tree": "Feature depth includes 15+ integrations",
    "user_persona": "Key persona: operations manager in mid-market",
    "swot": STATEMENT,
}


# ---------------------------------------------------------------------------
# Injected collect_fn — field-agnostic, round-aware
# ---------------------------------------------------------------------------


def _fake_collect_fn(
    query: str, *, cache: object, source_cap: int, mode: str = "live_first"
) -> list[dict]:
    """Return up to ``source_cap`` fixture sources (honest round-aware growth).

    Round 0 (cap=1): one source → analyst cannot corroborate → weak → revision.
    Round 1 (cap=2): two distinct-domain sources → enables strong evidence.
    """
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None  # type: ignore[union-attr]
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


# ---------------------------------------------------------------------------
# Injected analyze_fn — field-aware, returns schema-valid claims
# ---------------------------------------------------------------------------


def _fake_analyze_fn(
    db: object,
    run_id: str,
    *,
    field: str,
    competitor: str,
    evidence_text: str,
    source_ids: set,
    settings: object = None,
) -> dict:
    """Deterministic analyst: corroborate only when ≥2 distinct sources exist.

    With a single collected source the analyst cannot independently corroborate
    the claim, so ``evidence_ref`` is empty (→ weak). With two or more sources
    it cites them all (→ strong, since one is official). The statement is always
    a verbatim substring of the fixture text so the HALLUCINATED_SNIPPET gate
    passes.

    Each field returns a schema-VALID value (all required sub-fields populated).
    """
    ids = sorted(source_ids)
    evidence_ref = ids if len(ids) >= 2 else []
    statement = _STATEMENTS.get(field, STATEMENT)
    return {
        "statement": statement,
        "claim_type": "fact",
        "value": _VALID_VALUES[field],
        "evidence_ref": evidence_ref,
    }


# ---------------------------------------------------------------------------
# Helper: build and run the graph for all 5 fields
# ---------------------------------------------------------------------------


def _run_fanout_graph(tmp_path, *, extra_sources: list[dict] | None = None):
    """Build DB, optionally seed extra sources, run the graph, return (final, db, run_id)."""
    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(
        category="saas", competitors=[COMPETITOR], goal="5-field fanout proof"
    )

    # Pre-seed any extra sources (e.g. ingested survey sources) BEFORE the loop.
    if extra_sources:
        for src_row in extra_sources:
            db.append_source(src_row)

    with Cache(str(tmp_path / "cache.db")) as cache:
        cache.put(FetchResult(text=SOURCE_A_TEXT, url=SOURCE_A_URL, source_mode="LIVE"))
        cache.put(FetchResult(text=SOURCE_B_TEXT, url=SOURCE_B_URL, source_mode="LIVE"))

        deps = GraphDeps(
            db=db,
            cache=cache,
            settings=None,
            collect_fn=_fake_collect_fn,
            analyze_fn=_fake_analyze_fn,
        )
        graph = build_graph(deps=deps)

        final = graph.invoke(
            {
                "run_id": run_id,
                "db": db,
                "intake": {
                    "category": "saas",
                    "competitors": [COMPETITOR],
                    "goal": "5-field fanout proof",
                    "fields": ALL_FIELDS,
                },
            }
        )

    return final, db, run_id


# ---------------------------------------------------------------------------
# Test: 5-field fan-out
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_fanout_all_5_fields_offline(tmp_path) -> None:
    """Drive build_graph for ONE competitor across ALL 5 fields offline.

    Assertions:
    1. Run reaches ``write`` with a non-empty report.
    2. All 5 fields present in latest-claims set.
    3. Each field's final claim is schema-valid (no SCHEMA_GAP).
    4. Each field's final claim is bound to ≥1 real persisted source.
    5. ``feature_tree`` has genuine structural depth:
       ≥2 categories, non-empty features mapping, depth ≥ 2.
    6. Report references only backed claim ids.
    """
    final, db, run_id = _run_fanout_graph(tmp_path)

    # ----- 1. Reaches write (live graph then runs post-write synthesis:
    # write -> synthesis -> END, so terminal phase is "synthesis") -----
    assert final["phase"] in ("write", "synthesis"), f"got {final['phase']}"
    assert final.get("report"), "report body must not be empty"

    # ----- 2. All 5 fields present -----
    latest = db.latest_claims_for_run(run_id)
    covered_fields = {c["schema_field"] for c in latest}
    for field in ALL_FIELDS:
        assert field in covered_fields, (
            f"field {field!r} missing from latest claims; covered={covered_fields}"
        )

    # ----- 3. Each claim is schema-valid (no SCHEMA_GAP) -----
    claims_by_field = {c["schema_field"]: c for c in latest}
    for field in ALL_FIELDS:
        claim = claims_by_field[field]
        value = json.loads(claim.get("value_json") or "{}")
        evidence = json.loads(claim.get("evidence_json") or "[]")
        source_map = {}
        for ev in evidence:
            sid = ev.get("source_id")
            if sid:
                src = db.get_source(sid)
                if src:
                    source_map[sid] = {
                        "raw_text": src.get("raw_text") or "",
                        "source_type": src.get("source_type") or "web",
                        "url": src.get("url") or "",
                    }

        claimset = {
            "claims": [
                {
                    "id": claim["id"],
                    "competitor": claim.get("competitor"),
                    "schema_field": claim["schema_field"],
                    "claim_type": claim["claim_type"],
                    "statement": claim["statement"],
                    "value": value,
                    "evidence": evidence,
                }
            ],
            "sources": source_map,
            "coverage": {
                "required_fields": [field],
                "covered_fields": [field],
            },
        }
        issues = qa_check(claimset)
        schema_gaps = [i for i in issues if i.code.value == "SCHEMA_GAP"]
        assert not schema_gaps, (
            f"SCHEMA_GAP for field {field!r}: {[i.detail for i in schema_gaps]}"
        )

    # ----- 4. Each claim bound to ≥1 real persisted source -----
    for field in ALL_FIELDS:
        claim = claims_by_field[field]
        evidence = json.loads(claim.get("evidence_json") or "[]")
        assert evidence, f"claim for {field!r} has no evidence"
        for ev in evidence:
            sid = ev.get("source_id")
            assert sid, f"evidence item for {field!r} missing source_id"
            assert db.get_source(sid) is not None, (
                f"source {sid!r} for field {field!r} not in DB"
            )

    # ----- 5. feature_tree has genuine structural depth -----
    # Note: these assertions demonstrate that the analyst CAN populate rich
    # feature_tree structure (depth, categories). The negative test below
    # (test_feature_tree_missing_categories_triggers_schema_gap) proves the
    # system ENFORCES schema validity for feature_tree.
    ft_claim = claims_by_field["feature_tree"]
    ft_value = json.loads(ft_claim.get("value_json") or "{}")

    categories = ft_value.get("categories", [])
    assert len(categories) >= 2, (
        f"feature_tree.categories must have ≥2 entries; got {categories!r}"
    )

    features = ft_value.get("features")
    assert features, (
        f"feature_tree.features must be non-empty; got {features!r}"
    )

    depth = ft_value.get("depth")
    assert isinstance(depth, (int, float)) and int(depth) >= 2, (
        f"feature_tree.depth must be ≥2; got {depth!r}"
    )

    # ----- 6. Report references only backed claim ids -----
    passed_ids = {c["id"] for c in latest}
    report_lines = [line for line in final["report"].splitlines() if line.strip()]
    assert report_lines, "report must have at least one line"
    referenced = {
        line.split("]")[0].lstrip("[")
        for line in report_lines
        if "[" in line and "]" in line
    }
    if referenced:
        assert referenced <= passed_ids, (
            f"report references unknown ids: {referenced - passed_ids}"
        )


# ---------------------------------------------------------------------------
# Test: survey source backs user_sentiment claim at >= moderate strength
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_survey_source_backs_user_sentiment(tmp_path) -> None:
    """A pre-ingested survey source can back a user_sentiment claim at ≥ moderate.

    Approach: ingest a survey, then directly build a claim that cites the survey
    source (alongside a web source on a distinct domain), score the claim with
    the transparent scorer, and assert it reaches at least moderate.

    This is a focused scoring test — it does NOT need to drive the full loop
    because the loop's collect node cannot propagate the survey source_type
    through ``infer_source_type`` (which only returns official/web from URLs).
    The correct integration point is at the scoring layer, which treats
    ``source_type="survey"`` as AUTHORITATIVE.
    """
    from mingjing.collector import independence

    db = Database(str(tmp_path / "survey_score.db"))
    db.init_schema()
    run_id = db.create_run(
        category="saas",
        competitors=[COMPETITOR],
        goal="survey-backed sentiment scoring test",
    )

    # ----- 1. Ingest a synthetic survey for user_sentiment -----
    survey_responses = [
        {
            "respondent_meta": {"role": "Product Manager", "segment": "Enterprise"},
            "answers": {
                "q_overall": SENTIMENT_STATEMENT,
                "q_detail": "Orion users report high satisfaction overall",
            },
            "raw_text": SENTIMENT_STATEMENT,
        }
    ]
    survey_source_ids = ingest_survey(
        db, run_id, survey_responses, survey_id="SV-SENTIMENT-1"
    )
    assert survey_source_ids, "survey ingest must return at least one source_id"
    survey_sid = survey_source_ids[0]

    # Verify the survey source is persisted and authoritative.
    survey_src = db.get_source(survey_sid)
    assert survey_src is not None
    assert survey_src["source_type"] == "survey", (
        f"expected source_type='survey', got {survey_src['source_type']!r}"
    )

    # ----- 2. Persist a second, distinct-domain web source to corroborate -----
    import time
    import uuid

    web_sid = str(uuid.uuid4())
    db.append_source(
        {
            "id": web_sid,
            "run_id": run_id,
            "url": "https://g2reviews.net/orion-sentiment",
            "title": "G2 Orion sentiment review",
            "source_type": "web",
            "source_mode": None,
            "fetched_at": time.time(),
            "content_hash": None,
            "raw_text": SENTIMENT_STATEMENT,
            "meta_json": "{}",
        }
    )

    # ----- 3. Build source tuples for the scorer (survey + web, both supporting) -----
    survey_url = survey_src.get("url") or ""
    survey_domain = (
        independence.registrable_domain(survey_url) if survey_url else survey_sid
    )
    web_domain = independence.registrable_domain("https://g2reviews.net/orion-sentiment")

    source_tuples = [
        ("survey", "supports", survey_domain),   # authoritative
        ("web", "supports", web_domain),          # distinct domain corroboration
    ]

    scored = score_strength(sources=source_tuples, contradiction=False)
    assert scored in ("moderate", "strong"), (
        f"expected at least moderate strength for survey-backed claim, got {scored!r}"
    )

    # ----- 4. Survey source itself is authoritative (survey in AUTHORITATIVE_TYPES) -----
    from mingjing.scoring import AUTHORITATIVE_TYPES

    assert "survey" in AUTHORITATIVE_TYPES, (
        "'survey' must be in AUTHORITATIVE_TYPES for the authoritative gate to fire"
    )

    # ----- 5. With 2 distinct domains + 1 authoritative (survey) → strong -----
    # When survey_domain ≠ web_domain, we have ≥2 distinct supporting domains
    # with an authoritative source → strong.
    if survey_domain != web_domain:
        assert scored == "strong", (
            f"2 distinct domains with authoritative survey source should score strong; "
            f"got {scored!r} (survey_domain={survey_domain!r}, web_domain={web_domain!r})"
        )

    # ----- 6. Survey source persisted with correct locators -----
    cur = db._conn.execute(
        "SELECT * FROM evidence_chunks WHERE source_id = ?", (survey_sid,)
    )
    chunks = [dict(r) for r in cur.fetchall()]
    assert chunks, "survey source must have at least one evidence chunk"
    for chunk in chunks:
        locator = chunk.get("locator") or ""
        assert locator.startswith("survey:SV-SENTIMENT-1/q"), (
            f"survey chunk locator should be survey:SV-SENTIMENT-1/qN, got {locator!r}"
        )


# ---------------------------------------------------------------------------
# I4: feature_tree schema enforcement — NEGATIVE test
# ---------------------------------------------------------------------------


def test_feature_tree_missing_categories_triggers_schema_gap() -> None:
    """A feature_tree claim whose value has empty/missing categories triggers SCHEMA_GAP.

    This is a REAL system-level check using the actual qa.rules.qa_check gate.
    It proves the schema gate ENFORCES validity for feature_tree (I4), as opposed
    to the positive assertions in test_fanout_all_5_fields_offline which only
    demonstrate that the analyst CAN populate rich structure.

    We do NOT modify qa/rules.py, scoring.py, or qa/route.py — they are used as-is.
    """
    import uuid

    from mingjing.qa.rules import qa_check

    # A feature_tree claim with empty categories — schema-invalid.
    bad_claim_empty_cats = {
        "id": str(uuid.uuid4()),
        "competitor": "TestCo",
        "schema_field": "feature_tree",
        "claim_type": "fact",
        "statement": "TestCo has some features",
        "value": {
            "categories": [],          # empty list → SCHEMA_GAP
            "features": {"X": ["a"]},
            "depth": 2,
        },
        "evidence": [
            {
                "source_id": "src-1",
                "snippet": "TestCo has some features",
                "relevance": "supports",
            }
        ],
    }
    source_map = {
        "src-1": {
            "raw_text": "TestCo has some features and more",
            "source_type": "web",
            "url": "https://testco.io/features",
        }
    }
    claimset_empty = {
        "claims": [bad_claim_empty_cats],
        "sources": source_map,
        "coverage": {"required_fields": ["feature_tree"], "covered_fields": ["feature_tree"]},
    }
    issues_empty = qa_check(claimset_empty)
    schema_gaps_empty = [i for i in issues_empty if i.code.value == "SCHEMA_GAP"]
    assert schema_gaps_empty, (
        "Expected SCHEMA_GAP for feature_tree with empty categories; "
        f"got issues: {[str(i) for i in issues_empty]}"
    )

    # A feature_tree claim with missing categories key — also schema-invalid.
    bad_claim_missing_cats = {
        "id": str(uuid.uuid4()),
        "competitor": "TestCo",
        "schema_field": "feature_tree",
        "claim_type": "fact",
        "statement": "TestCo has some features",
        "value": {
            # categories key absent entirely
            "features": {"X": ["a"]},
            "depth": 2,
        },
        "evidence": [
            {
                "source_id": "src-1",
                "snippet": "TestCo has some features",
                "relevance": "supports",
            }
        ],
    }
    claimset_missing = {
        "claims": [bad_claim_missing_cats],
        "sources": source_map,
        "coverage": {"required_fields": ["feature_tree"], "covered_fields": ["feature_tree"]},
    }
    issues_missing = qa_check(claimset_missing)
    schema_gaps_missing = [i for i in issues_missing if i.code.value == "SCHEMA_GAP"]
    assert schema_gaps_missing, (
        "Expected SCHEMA_GAP for feature_tree with missing categories key; "
        f"got issues: {[str(i) for i in issues_missing]}"
    )
