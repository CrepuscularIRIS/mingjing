"""Unit tests for coerce_payload_shape (M5).

The live model sometimes returns a bare JSON array for list-valued fields such
as user_persona.  coerce_payload_shape wraps the list into a proper claim-object
dict so the downstream isinstance(payload, dict) guard does not silently drop the
field.
"""

from mingjing.agents.analyst import coerce_payload_shape


def test_coerce_list_payload_wraps_under_required_subfield() -> None:
    """A list payload for a known field is wrapped under its first required sub-field."""
    result = coerce_payload_shape([{"segment": "SMB"}], "user_persona")
    assert isinstance(result, dict)
    assert result["claim_type"] == "inference"
    assert result["value"] == {"segments": [{"segment": "SMB"}]}
    assert result["evidence_ref"] == []


def test_coerce_dict_payload_unchanged() -> None:
    """A normal dict payload passes through without modification."""
    original = {
        "statement": "Pro costs $10.",
        "claim_type": "fact",
        "value": {"price": 10},
        "evidence_ref": ["S1"],
    }
    result = coerce_payload_shape(original, "pricing_model")
    assert result is original


def test_coerce_list_unknown_field_uses_items_key() -> None:
    """An unknown field has no required sub-fields; the fallback key is 'items'."""
    result = coerce_payload_shape([1, 2], "nonexistent")
    assert isinstance(result, dict)
    assert result["value"] == {"items": [1, 2]}
    assert result["claim_type"] == "inference"
    assert result["evidence_ref"] == []


def test_coerce_empty_list_returns_empty_dict() -> None:
    """An empty list returns {} so the analyze-node guard skips it (claim_skipped)."""
    result = coerce_payload_shape([], "user_persona")
    assert result == {}
    assert not result
