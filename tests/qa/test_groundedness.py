from mingjing.qa.groundedness import score_groundedness


def test_groundedness_blind_to_reasoning_only_value_and_source():
    # Checker sees ONLY (value leaves, cited source text). Fully supported → 1.0.
    score = score_groundedness(
        value={"plan_name": "Pro", "price": "$20/mo"},
        cited_source_text="The Pro plan costs $20/mo.",
    )
    assert score == 1.0


def test_groundedness_partial_when_one_leaf_absent():
    # 'Premium' is checkable (>=4 chars) and present; 'best in class enterprise'
    # is checkable but absent. ('Pro' would be sub-threshold under the gate's
    # >=4-char checkable rule, so we use a >=4-char supported leaf to mirror the
    # deterministic VALUE_UNSUPPORTED notion of a checkable leaf.)
    score = score_groundedness(
        value={"plan_name": "Premium", "tagline": "best in class enterprise"},
        cited_source_text="The Premium plan exists.",
    )
    assert 0.0 < score < 1.0  # 'Premium' supported, 'best in class enterprise' not


def test_groundedness_zero_when_nothing_supported():
    assert score_groundedness(value={"x": "wholly invented phrase"},
                              cited_source_text="unrelated text") == 0.0


def test_groundedness_one_when_no_checkable_leaves():
    # All leaves sub-threshold (<4 chars / no alpha) → nothing to disprove → 1.0.
    assert score_groundedness(value={"code": "US", "n": "10"},
                              cited_source_text="anything at all") == 1.0


def test_groundedness_zero_when_source_empty_but_leaves_checkable():
    assert score_groundedness(value={"plan": "Premium tier"},
                              cited_source_text="") == 0.0


# --- Parity guards: the advisory scorer MUST agree with the deterministic gate ---
# These enforce the module's "byte-for-byte identical to the gate" contract via CI
# rather than by docstring prose. If rules.py ever tightens its checkable/normalize
# notions, the advisory score and the VALUE_UNSUPPORTED veto would silently diverge
# — these tests fail first. Importing rules.py here (in a test) is fine; only the
# production module stays dependency-lean.

def test_checkable_parity_with_gate():
    from mingjing.qa import rules
    from mingjing.qa.groundedness import _checkable
    samples = ["", "USD", "Pro", "Y", "  abc ", "Premium", "0", "10",
               "$25", "a1b2", "  ", "four", "1234", "n/a", "co"]
    for s in samples:
        assert _checkable(s) == rules._is_checkable_leaf(s), s


def test_normalize_parity_with_gate():
    from mingjing.qa import rules
    from mingjing.qa.groundedness import _WS
    samples = ["The  Pro\tplan", "  MixedCase  ", "a\n\nb", "", "   ", "X"]
    for s in samples:
        advisory = _WS.sub(" ", s).strip().lower()
        gate = rules._normalize_ws(s).lower()
        assert advisory == gate, s


def test_leaves_parity_with_gate():
    from mingjing.qa import rules
    from mingjing.qa.groundedness import _leaves
    trees = [
        {"a": "hello", "b": 3, "c": [{"d": "world"}, None, "x"]},
        {"nested": {"k": ["one", 2, "two"]}, "skip_int": 5, "skip_none": None},
        [],
        {},
        "bare string",
    ]
    for tree in trees:
        gate_leaves: list[str] = []
        rules._collect_string_leaves(tree, gate_leaves)
        assert _leaves(tree) == gate_leaves, tree
