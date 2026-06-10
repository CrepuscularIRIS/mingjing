"""Offline pricing_model strong-path proof (Task 16, Deliverable 2).

Drives ``build_graph`` with injected ``collect_fn`` / ``analyze_fn`` for the
``pricing_model`` field to prove that the pricing happy path is REAL and not
"schema theater":

- Fixture (i): competitor's OFFICIAL pricing page (host label = competitor
  token) whose ``raw_text`` lists "Pro tier $10/month".
- Fixture (ii): a second DISTINCT-domain corroborating source.
- The injected ``analyze_fn`` returns a claim whose ``value`` includes ``tiers``
  (schema-required) and whose snippet is a verbatim substring of the fixture
  text.

Assertions:
1. Final latest claim for ``pricing_model`` has ``evidence_strength == "strong"``.
2. Schema is valid — ``tiers`` is populated, so no ``SCHEMA_GAP``.
3. QA verdict is ``"pass"`` on the final round.

This is marked ``@pytest.mark.slow`` because it drives the full LangGraph loop.
"""

import json
import re

import pytest

from mingjing.collector.cache import Cache
from mingjing.collector.fetch import FetchResult
from mingjing.db import Database
from mingjing.graph import GraphDeps, build_graph
from mingjing.qa.rules import qa_check

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

COMPETITOR = "Acme"
FIELD = "pricing_model"

# Statement that is a verbatim substring of BOTH fixture texts.
STATEMENT = "Pro tier $10 per month"

# Fixture (i): official Acme pricing page (host label "acme" in registrable domain)
OFFICIAL_URL = "https://acme.example.com/pricing"
OFFICIAL_TEXT = f"Official Acme pricing: {STATEMENT}, billed monthly. Pro tier $10/month for teams. Pro $10/month available."

# Fixture (ii): independent corroborating source on a distinct registrable domain
CORROBORATE_URL = "https://techreviews.net/acme-pricing"
CORROBORATE_TEXT = f"Third-party review confirms: {STATEMENT}, available in annual and monthly billing."

FIXTURE_SOURCES = [
    {
        "url": OFFICIAL_URL,
        "title": "Acme official pricing",
        "text": OFFICIAL_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "pfix-official",
        "content_hash": "hash_official",
        "fetched_at": 1.0,
    },
    {
        "url": CORROBORATE_URL,
        "title": "TechReviews Acme pricing",
        "text": CORROBORATE_TEXT,
        "source_mode": "LIVE",
        "fetched": True,
        "source_id": "pfix-corroborate",
        "content_hash": "hash_corroborate",
        "fetched_at": 2.0,
    },
]


# ---------------------------------------------------------------------------
# Injected callables
# ---------------------------------------------------------------------------


def _fake_collect_fn(query: str, *, cache, source_cap: int, mode: str = "live_first"):
    """Return up to ``source_cap`` fixture sources (round-aware, honest growth).

    Round 0 (cap=1): only the official source — analyst can't corroborate.
    Round 1 (cap=2): both sources — enables strong evidence.
    """
    import uuid

    out = []
    for fixture in FIXTURE_SOURCES[:source_cap]:
        cached = cache.get(fixture["url"]) if cache is not None else None
        text = cached.text if cached is not None else fixture["text"]
        out.append({**fixture, "text": text, "source_id": str(uuid.uuid4())})
    return out


def _fake_analyze_fn(
    db, run_id, *, field, competitor, evidence_text, source_ids, settings=None
):
    """Deterministic analyst for pricing_model.

    With one source: cite nothing (weak, will trigger revision).
    With two or more: cite all, include required ``tiers`` sub-field in value.
    The statement is a verbatim substring of both fixture texts.
    """
    ids = sorted(source_ids)
    if len(ids) >= 2:
        evidence_ref = ids
    else:
        evidence_ref = []
    return {
        "statement": STATEMENT,
        "claim_type": "fact",
        "value": {
            "tiers": ["Pro $10/month"],
            "free_tier": False,
            "currency": "USD",
            "billing_period": "monthly",
        },
        "evidence_ref": evidence_ref,
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_pricing_model_strong_path_offline(tmp_path) -> None:
    """pricing_model happy path: official + corroborate => strong, schema valid, QA pass."""

    db = Database(str(tmp_path / "run.db"))
    db.init_schema()
    run_id = db.create_run(
        category="saas", competitors=[COMPETITOR], goal="pricing research"
    )

    with Cache(str(tmp_path / "cache.db")) as cache:
        # Seed the cache so _fake_collect_fn can read from it.
        cache.put(FetchResult(text=OFFICIAL_TEXT, url=OFFICIAL_URL, source_mode="LIVE"))
        cache.put(
            FetchResult(
                text=CORROBORATE_TEXT, url=CORROBORATE_URL, source_mode="LIVE"
            )
        )

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
                    "goal": "pricing research",
                    "fields": [FIELD],
                },
            }
        )

    # ----- 1. Graph reaches write phase and emits a non-empty report (the live
    # graph then runs the post-write synthesis node: write -> synthesis -> END) -----
    assert final["phase"] in ("write", "synthesis"), f"got {final['phase']}"
    assert final.get("report"), "report body must not be empty"

    # ----- 2. Retrieve the final latest claim for pricing_model ----------
    latest = db.latest_claims_for_run(run_id)
    pricing_claims = [c for c in latest if c["schema_field"] == FIELD]
    assert pricing_claims, f"no {FIELD} claim found in DB; all latest={latest}"

    final_claim = pricing_claims[0]

    # ----- 3. evidence_strength == "strong" -----
    assert final_claim["evidence_strength"] == "strong", (
        f"expected strong, got {final_claim['evidence_strength']!r}"
    )

    # ----- 4. Schema valid: tiers populated, no SCHEMA_GAP -----
    value = json.loads(final_claim.get("value_json") or "{}")
    assert "tiers" in value and value["tiers"], (
        f"tiers must be populated in value; got value={value}"
    )

    # Re-run the QA rules directly to confirm no SCHEMA_GAP issue for this claim.
    evidence = json.loads(final_claim.get("evidence_json") or "[]")
    sources = {}
    for ev in evidence:
        src = db.get_source(ev["source_id"])
        if src:
            sources[ev["source_id"]] = {
                "raw_text": src.get("raw_text") or "",
                "source_type": src.get("source_type") or "web",
                "url": src.get("url") or "",
            }

    claimset = {
        "claims": [
            {
                "id": final_claim["id"],
                "competitor": final_claim.get("competitor"),
                "schema_field": final_claim["schema_field"],
                "claim_type": final_claim["claim_type"],
                "statement": final_claim["statement"],
                "value": value,
                "evidence": evidence,
            }
        ],
        "sources": sources,
        "coverage": {
            "required_fields": [FIELD],
            "covered_fields": [FIELD],
        },
    }

    issues = qa_check(claimset)
    schema_gaps = [i for i in issues if i.code.value == "SCHEMA_GAP"]
    assert not schema_gaps, f"unexpected SCHEMA_GAP issues: {schema_gaps}"

    # ----- 5. QA verdict on the final run state is "pass" -----
    assert final.get("verdict") == "pass", (
        f"expected verdict=pass, got {final.get('verdict')!r}"
    )

    # ----- 6. The snippet in evidence is a substring of the fixture text -----
    ws = re.compile(r"\s+")
    for ev in evidence:
        if ev.get("relevance") != "supports":
            continue
        snippet = ev.get("snippet", "")
        src = db.get_source(ev["source_id"])
        raw = (src.get("raw_text") or "") if src else ""
        # Normalize whitespace to match the rules.py logic.
        norm_snip = ws.sub(" ", snippet).strip()
        norm_raw = ws.sub(" ", raw).strip()
        assert norm_snip in norm_raw, (
            f"snippet not found in source raw text.\n"
            f"snippet: {snippet!r}\n"
            f"raw (first 200): {raw[:200]!r}"
        )

    # ----- 7. Weak -> strong transition is visible across versions -----
    all_claims = sorted(db.claims_for_run(run_id), key=lambda c: c["version"])
    strengths = [c["evidence_strength"] for c in all_claims]
    assert strengths[-1] == "strong", f"final strength must be strong; got {strengths}"
    rank = {"weak": 0, "moderate": 1, "strong": 2}
    assert any(rank[s] < rank["strong"] for s in strengths[:-1]), (
        f"an earlier version must be weaker; got {strengths}"
    )
