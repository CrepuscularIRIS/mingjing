"""Tests for the analyst verbatim-evidence snippet prompt (Task 7).

Four offline tests — no network, no API key:

1. test_prompt_requires_verbatim_snippet
   Lock the prompt-config contract: the built analyst instruction string must
   contain the verbatim-snippet instruction.

2. test_verbatim_snippet_passes_grounding_round0
   A claim whose evidence snippet is a verbatim substring of the source raw_text
   (and whose value leaf appears in that text) PASSES both score_groundedness
   and the VALUE_UNSUPPORTED / HALLUCINATED_SNIPPET gates at round-0.

3. test_absent_or_paraphrased_snippet_is_rejected
   A claim whose snippet is NOT a substring of the source raw_text, or whose
   value leaf does not appear in any cited source, is flagged by the QA gate —
   proving the prompt change FEEDS the deterministic gate, not bypasses it.

4. test_value_leaf_absent_from_source_is_rejected
   A value leaf that is not present verbatim in any cited source is flagged by
   VALUE_UNSUPPORTED, confirming the gate catches fabricated sub-field values.
"""

from mingjing.agents.analyst import build_field_prompt
from mingjing.qa.groundedness import score_groundedness
from mingjing.qa.rules import IssueCode, _check_hallucinated_snippet, _check_value_unsupported

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claim(
    *,
    schema_field: str = "pricing_model",
    value: dict,
    evidence: list[dict],
) -> dict:
    return {
        "id": "c1",
        "competitor": "Acme",
        "schema_field": schema_field,
        "statement": "test statement",
        "claim_type": "fact",
        "value": value,
        "evidence": evidence,
    }


def _make_source(*, source_id: str, raw_text: str) -> dict[str, dict]:
    return {
        source_id: {
            "source_type": "web",
            "url": "https://example.com/pricing",
            "raw_text": raw_text,
        }
    }


# ---------------------------------------------------------------------------
# Test 1: prompt-config contract
# ---------------------------------------------------------------------------

def test_prompt_requires_verbatim_snippet() -> None:
    """The built analyst instruction must contain the verbatim-snippet instruction."""
    prompt = build_field_prompt(
        field="pricing_model",
        competitor="Acme",
        required_fields=["tier_name", "monthly_price"],
        sub_fields=["tier_name", "monthly_price", "billing_period"],
    )
    # Must contain a clear verbatim / copy-from-source directive.
    lower = prompt.lower()
    has_verbatim = "verbatim" in lower or "copy" in lower or "原文" in lower or "逐字" in lower
    assert has_verbatim, (
        "Analyst prompt must instruct the model to provide a verbatim snippet; "
        f"got prompt:\n{prompt}"
    )
    # Sanity: the prompt must still mention the evidence / source structure.
    assert "source_id" in prompt.lower() or "[source_id:" in prompt.lower(), (
        "Prompt must reference source_id labeling in evidence blocks"
    )


# ---------------------------------------------------------------------------
# Test 2: verbatim snippet → passes QA gates at round-0
# ---------------------------------------------------------------------------

def test_verbatim_snippet_passes_grounding_round0() -> None:
    """A claim with a verbatim snippet and matching value passes all QA gates.

    pricing_model required sub-field is 'tiers'; we use it with a value leaf
    ("Pro tier") that IS present verbatim in the source raw_text.
    """
    raw_text = (
        "Acme offers a Pro tier at $29 per month. "
        "Features include unlimited projects and priority support."
    )
    # Verbatim span from the source text.
    snippet = "Pro tier at $29 per month"
    source_id = "src-001"

    # 'tiers' is the required sub-field for pricing_model.
    claim = _make_claim(
        schema_field="pricing_model",
        value={"tiers": "Pro tier"},
        evidence=[
            {
                "source_id": source_id,
                "snippet": snippet,
                "relevance": "supports",
                "stance": "supports",
            }
        ],
    )
    sources = _make_source(source_id=source_id, raw_text=raw_text)

    # score_groundedness on the value dict against the source text.
    score = score_groundedness(value=claim["value"], cited_source_text=raw_text)
    assert score == 1.0, f"Expected perfect groundedness, got {score}"

    # HALLUCINATED_SNIPPET must not fire.
    hs_issues = _check_hallucinated_snippet(claim, sources)
    hs_codes = [i.code for i in hs_issues]
    assert IssueCode.HALLUCINATED_SNIPPET not in hs_codes, (
        f"Verbatim snippet should not trigger HALLUCINATED_SNIPPET; issues: {hs_issues}"
    )

    # VALUE_UNSUPPORTED must not fire ("Pro tier" is a substring of raw_text).
    vu_issues = _check_value_unsupported(claim, sources)
    vu_codes = [i.code for i in vu_issues]
    assert IssueCode.VALUE_UNSUPPORTED not in vu_codes, (
        f"Value with verbatim leaf should not trigger VALUE_UNSUPPORTED; issues: {vu_issues}"
    )


# ---------------------------------------------------------------------------
# Test 3: absent / paraphrased snippet is flagged by the QA gate
# ---------------------------------------------------------------------------

def test_absent_or_paraphrased_snippet_is_rejected() -> None:
    """A paraphrased or fabricated snippet is flagged by HALLUCINATED_SNIPPET."""
    raw_text = (
        "Acme offers a Pro tier at $29 per month. "
        "Features include unlimited projects and priority support."
    )
    # Paraphrased — does not appear verbatim in raw_text.
    paraphrased_snippet = "The Pro plan costs twenty-nine dollars monthly"
    source_id = "src-002"

    claim = _make_claim(
        schema_field="pricing_model",
        value={"tiers": "Pro tier"},
        evidence=[
            {
                "source_id": source_id,
                "snippet": paraphrased_snippet,
                "relevance": "supports",
                "stance": "supports",
            }
        ],
    )
    sources = _make_source(source_id=source_id, raw_text=raw_text)

    # HALLUCINATED_SNIPPET must fire because snippet is not in raw_text.
    hs_issues = _check_hallucinated_snippet(claim, sources)
    hs_codes = [i.code for i in hs_issues]
    assert IssueCode.HALLUCINATED_SNIPPET in hs_codes, (
        f"Paraphrased snippet should trigger HALLUCINATED_SNIPPET; issues: {hs_issues}"
    )


def test_value_leaf_absent_from_source_is_rejected() -> None:
    """A value leaf that does not appear in any cited source is flagged by VALUE_UNSUPPORTED.

    pricing_model required sub-field is 'tiers' (list); we set it to a string
    leaf that is NOT present in the raw_text to confirm the gate fires.
    """
    raw_text = "Acme offers a Starter tier at $9 per month."
    source_id = "src-003"

    # 'tiers' is the required sub-field for pricing_model (per active_field_schemas).
    # Value leaf "Enterprise plan" is not present verbatim in raw_text.
    claim = _make_claim(
        schema_field="pricing_model",
        value={"tiers": "Enterprise plan"},
        evidence=[
            {
                "source_id": source_id,
                "snippet": "Acme offers a Starter tier at $9 per month",
                "relevance": "supports",
                "stance": "supports",
            }
        ],
    )
    sources = _make_source(source_id=source_id, raw_text=raw_text)

    vu_issues = _check_value_unsupported(claim, sources)
    vu_codes = [i.code for i in vu_issues]
    assert IssueCode.VALUE_UNSUPPORTED in vu_codes, (
        f"Fabricated tier value should trigger VALUE_UNSUPPORTED; issues: {vu_issues}"
    )
