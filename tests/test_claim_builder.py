"""Unit tests for claim_builder.build_claim (M-4: null claim_type regression).

These tests run OFFLINE — no network or LLM calls are made. build_claim only
needs a db handle for supersede_target (which calls db.claims_for_run); we use
a real in-memory Database with init_schema() to match the repo's fixture style.
"""

import json

import pytest

from mingjing.claim_builder import build_claim, claimset_parts
from mingjing.db import Database


@pytest.fixture()
def db(tmp_path):
    d = Database(str(tmp_path / "claim_test.db"))
    d.init_schema()
    return d


# Minimal fake source row — must have at least id, url, raw_text, source_type.
_FAKE_SRC = {
    "id": "src-001",
    "url": "https://acme.example.com/pricing",
    "raw_text": "Acme pricing: free tier available and pro tier at $10/month.",
    "source_type": "official",
}

_TASK = {"field": "pricing_model", "competitor": "Acme"}


def test_null_claim_type_falls_back_to_fact(db):
    """An explicit JSON null for claim_type must produce 'fact', not None.

    Regression: before the `or "fact"` fix, `.get("claim_type", "fact")` would
    return None when the value was explicitly null, causing a NOT NULL
    IntegrityError on the claims table.
    """
    payload = {
        "claim_type": None,
        "statement": "Acme has a free tier.",
        "value": {"tiers": ["free", "pro"]},
        "evidence_ref": [],
    }
    result = build_claim(db, "run-1", _TASK, [_FAKE_SRC], payload)
    assert result["claim_type"] == "fact", (
        f"expected 'fact' for null claim_type, got {result['claim_type']!r}"
    )


def test_based_on_lineage_survives_build_and_claimset_parts(db):
    """Regression (Codex stop-review): an inference's based_on lineage must survive
    BOTH build_claim persistence AND claimset_parts decoding — otherwise it is
    dropped before QA and every inference looks lineage-less to the verifier."""
    payload = {
        "claim_type": "inference",
        "statement": "Acme likely targets SMB.",
        "value": {"strengths": ["smb focus"]},
        "evidence_ref": [],
        "based_on": ["C-PARENT"],
    }
    claim = build_claim(db, "run-lineage", _TASK, [_FAKE_SRC], payload)
    # build_claim carries the lineage instead of defaulting to [].
    assert claim["based_on"] == ["C-PARENT"]
    assert json.loads(claim["based_on_json"]) == ["C-PARENT"]
    # Persist and read it back through the exact shape QA consumes.
    db.append_claim(claim)
    latest = db.latest_claims_for_run("run-lineage")
    parts, _sources = claimset_parts(db, latest)
    assert parts[0]["based_on"] == ["C-PARENT"]


def test_build_claim_withholds_ungrounded_optional_value_leaf(db):
    """Regression (Codex stop-review, optional-sub-field bypass): build_claim must
    drop an LLM-fabricated value under an OPTIONAL sub-field that is absent from the
    cited sources, so it never reaches status=pass / the published report. The
    REQUIRED sub-field (grounded) is preserved."""
    src = {
        "id": "src-opt",
        "url": "https://acme.example.com/pricing",
        "raw_text": "Acme pricing: the pro tier is available.",
        "source_type": "official",
    }
    payload = {
        "claim_type": "fact",
        "statement": "Acme pricing.",
        "value": {
            "tiers": ["pro tier"],                       # required, grounded → kept
            "free_tier": "secret unlimited backdoor plan",  # optional, NOT in source → withheld
        },
        "evidence_ref": ["src-opt"],
    }
    claim = build_claim(db, "run-opt", {"field": "pricing_model", "competitor": "Acme"}, [src], payload)
    assert claim["value"].get("tiers") == ["pro tier"]
    assert "free_tier" not in claim["value"]            # ungrounded optional leaf withheld
    assert json.loads(claim["value_json"]) == claim["value"]  # persisted value matches


def test_missing_based_on_decodes_to_empty_list(db):
    """A claim with no lineage decodes to [] (not missing) so the QA integrity
    check treats it as an admitted, lineage-less inference rather than crashing."""
    payload = {
        "claim_type": "inference",
        "statement": "Acme is consumer-focused.",
        "value": {"strengths": ["consumer"]},
        "evidence_ref": [],
    }
    claim = build_claim(db, "run-nolineage", _TASK, [_FAKE_SRC], payload)
    assert claim["based_on"] == []
    db.append_claim(claim)
    parts, _ = claimset_parts(db, db.latest_claims_for_run("run-nolineage"))
    assert parts[0]["based_on"] == []


def test_explicit_claim_type_is_preserved(db):
    """When the payload provides a non-null claim_type it must be passed through."""
    payload = {
        "claim_type": "inference",
        "statement": "Acme likely increased pricing.",
        "value": {"tiers": ["pro"]},
        "evidence_ref": [],
    }
    result = build_claim(db, "run-2", _TASK, [_FAKE_SRC], payload)
    assert result["claim_type"] == "inference", (
        f"expected 'inference', got {result['claim_type']!r}"
    )


def test_build_claim_survives_non_string_raw_text(db):
    """Regression (Codex stop-review): a source row whose raw_text is a non-string
    (LLM/ingest/DB anomaly) must not crash build_claim. raw_text flows to
    paragraph_locator (re.split) and the cited_source_text " ".join — both raise
    TypeError on a non-str. build_claim runs OUTSIDE the analyze try/except, so a
    crash here kills the whole run."""
    payload = {
        "statement": "Acme has a free tier.",
        "value": {"tiers": ["free"]},
        "evidence_ref": ["src-bad"],
        "evidence": [{"source_id": "src-bad", "snippet": "free tier available"}],
    }
    for bad_raw in (999, ["a", "b"], {"k": 1}, True):
        src = {"id": "src-bad", "url": "https://x.example.com", "raw_text": bad_raw, "source_type": "web"}
        claim = build_claim(db, "run-badraw", _TASK, [src], payload)
        assert claim["id"]  # produced a claim, did not raise
        assert isinstance(claim["evidence"], list)
