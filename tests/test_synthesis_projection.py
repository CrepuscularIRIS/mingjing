from mingjing.synthesis import project_synthesis

PAYLOAD = {
  "bluf": {"text": "Acme leads on price.", "claim_ids": ["c1"]},
  "swot": {"strengths": [{"text": "Low price", "claim_ids": ["c1"]},
                          {"text": "Big install base", "claim_ids": ["c9"]}]},  # c9 not passed
  "recommendations": [{"text": "Match the free tier.", "claim_ids": ["c2"]}],
  "intelligence_gap": [{"text": "Enterprise pricing unknown.", "claim_ids": []}],  # non-factual scaffold ok
}


def test_unbacked_sentence_dropped():
    out = project_synthesis(payload=PAYLOAD, passed_claim_ids={"c1", "c2"})
    strengths = out["swot"]["strengths"]
    assert all(set(s["claim_ids"]) <= {"c1", "c2"} for s in strengths)
    assert not any("install base" in s["text"] for s in strengths)  # c9 dropped


def test_referenced_ids_subset_of_passed():
    out = project_synthesis(payload=PAYLOAD, passed_claim_ids={"c1", "c2"})
    assert set(out["referenced_claim_ids"]) <= {"c1", "c2"}


def test_projection_is_deterministic():
    a = project_synthesis(payload=PAYLOAD, passed_claim_ids={"c1", "c2"})
    b = project_synthesis(payload=PAYLOAD, passed_claim_ids={"c1", "c2"})
    assert a == b


def test_scaffold_with_valid_id_is_kept_and_referenced():
    payload = {
        "intelligence_gap": [
            {"text": "Pricing partially confirmed.", "claim_ids": ["c1"]}
        ],
    }
    out = project_synthesis(payload=payload, passed_claim_ids={"c1", "c2"})
    gap = out["intelligence_gap"]
    assert len(gap) == 1
    assert gap[0]["claim_ids"] == ["c1"]
    assert "c1" in out["referenced_claim_ids"]


def test_comparison_with_partially_invalid_ids_dropped():
    payload = {
        "comparison": [
            {"text": "Acme beats Beta on uptime.", "claim_ids": ["c1", "c9"]}
        ],
    }
    out = project_synthesis(payload=payload, passed_claim_ids={"c1", "c2"})
    assert out["comparison"] == []  # not all ids backed -> dropped
    assert "c9" not in out["referenced_claim_ids"]
    assert "c1" not in out["referenced_claim_ids"]


def test_kept_sentences_always_have_claim_ids_list():
    """Scaffold sentences may omit claim_ids in the raw payload; the projection
    must normalize every KEPT sentence to carry a list claim_ids so consumers
    (the frontend) never dereference an undefined field."""
    payload = {
        "bluf": {"text": "Backed bottom line", "claim_ids": ["c1"]},
        "intelligence_gap": [{"text": "We do not know enterprise pricing."}],  # no claim_ids
        "key_assumptions": [{"text": "Assume pricing is current.", "claim_ids": None}],  # null
    }
    out = project_synthesis(payload=payload, passed_claim_ids={"c1"})
    assert out["bluf"]["claim_ids"] == ["c1"]
    for s in out["intelligence_gap"] + out["key_assumptions"]:
        assert isinstance(s["claim_ids"], list)
