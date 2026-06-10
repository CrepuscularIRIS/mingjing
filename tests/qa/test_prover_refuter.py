from mingjing.qa.prover_refuter import adjudicate


def test_prover_and_refuter_agree_keeps_confidence():
    # Both verdicts agree the claim holds → confidence retained, no contradiction.
    r = adjudicate(prover_supports=True, refuter_refutes=False, base_tier="strong")
    assert r["confidence"] == "strong"
    assert r["contradiction"] is False


def test_refuter_dissent_downgrades_and_flags_contradiction():
    r = adjudicate(prover_supports=True, refuter_refutes=True, base_tier="strong")
    assert r["confidence"] in ("moderate", "weak")  # downgraded
    assert r["contradiction"] is True               # feeds ContradictionCard


def test_neither_supports_collapses_to_weak():
    # Prover can't support but refuter actively refutes → weak AND a contradiction
    # is still surfaced (the exact signal that feeds ContradictionCard).
    r = adjudicate(prover_supports=False, refuter_refutes=True, base_tier="moderate")
    assert r["confidence"] == "weak"
    assert r["contradiction"] is True


def test_unknown_base_tier_falls_back_to_moderate():
    # Garbage base_tier defaults to "moderate" before any adjustment.
    r = adjudicate(prover_supports=True, refuter_refutes=False, base_tier="bogus")
    assert r["confidence"] == "moderate"
    assert r["contradiction"] is False


def test_both_false_collapses_to_weak_without_contradiction():
    # Prover can't support and refuter finds nothing → weak, but not a contradiction.
    r = adjudicate(prover_supports=False, refuter_refutes=False, base_tier="strong")
    assert r["confidence"] == "weak"
    assert r["contradiction"] is False
