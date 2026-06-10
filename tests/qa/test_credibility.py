from mingjing.qa.credibility import credibility_panel


def test_panel_computes_groundedness_citation_and_repair_delta():
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 1.0}, {"id": "C2", "groundedness": 0.5}],
        total_claims=3,
        required_fields=["pricing_model", "feature_tree"],
        covered_fields=["pricing_model"],
        round_indices=[1, 2],
        # PAIRED: one claim revised 0.40 -> 0.75 (its OWN before vs after).
        claim_version_groundedness={"C1": [0.40, 0.75]},
    )
    assert panel["avg_groundedness"] == 0.75       # (1.0 + 0.5) / 2
    assert panel["claim_admission_rate"] == round(2 / 3, 3)
    assert panel["coverage"] == 0.5
    assert panel["repair_delta"] == 0.35           # 0.75 - 0.40 on the repaired claim


def test_admission_waterfall_and_coverage_gaps():
    """Advisory waterfall + coverage-gap fields surface 少而精 honestly."""
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 1.0}, {"id": "C2", "groundedness": 0.5}],
        total_claims=5,
        required_fields=["pricing_model", "feature_tree", "swot"],
        covered_fields=["pricing_model"],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.4, 0.8]},
    )
    # proposed → admitted → withheld; distinct latest-version claims, no double count
    assert panel["proposed_claims"] == 5
    assert panel["admitted_claims"] == 2
    assert panel["withheld_claims"] == 3
    # coverage gaps: field NAMES only, bounded to required, schema order preserved
    assert panel["covered_fields"] == ["pricing_model"]
    assert panel["uncovered_fields"] == ["feature_tree", "swot"]


def test_waterfall_withheld_never_negative():
    """Defensive: admitted can't exceed proposed → withheld floors at 0."""
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 1.0}],
        total_claims=0,
        required_fields=[],
        covered_fields=[],
        round_indices=[1],
    )
    assert panel["withheld_claims"] == 0


def test_empty_passed_claims_no_zero_division():
    panel = credibility_panel(
        passed_claims=[],
        total_claims=5,
        required_fields=["a"],
        covered_fields=[],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.1, 0.2]},
    )
    assert panel["avg_groundedness"] == 0.0
    assert panel["claim_admission_rate"] == 0.0
    assert panel["coverage"] == 0.0


def test_total_claims_zero_admission_is_zero():
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 1.0}],
        total_claims=0,
        required_fields=["a"],
        covered_fields=["a"],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.1, 0.9]},
    )
    assert panel["claim_admission_rate"] == 0.0


def test_empty_required_fields_coverage_is_zero():
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 0.8}],
        total_claims=1,
        required_fields=[],
        covered_fields=["a"],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.1, 0.5]},
    )
    assert panel["coverage"] == 0.0


def test_single_round_repair_delta_is_zero():
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 0.8}],
        total_claims=1,
        required_fields=["a"],
        covered_fields=["a"],
        round_indices=[1],  # one version level observed
        # No claim has >=2 versions -> nothing was repaired -> delta 0.0.
        claim_version_groundedness={"C1": [0.6]},
    )
    assert panel["repair_delta"] == 0.0
    assert panel["rounds"] == 1


def test_repair_delta_ignores_unrevised_claims():
    """RC1: a claim that never revised (single version) does NOT contribute to
    repair_delta, even when its groundedness differs from a repaired claim's."""
    panel = credibility_panel(
        passed_claims=[{"id": "A", "groundedness": 1.0}, {"id": "B", "groundedness": 1.0}],
        total_claims=2,
        required_fields=["a"],
        covered_fields=["a"],
        round_indices=[1, 2],
        # A: single high version (never revised). B: 0.0 -> 1.0 (repaired).
        claim_version_groundedness={"A": [1.0], "B": [0.0, 1.0]},
    )
    # Paired lift on the only repaired claim B: 1.0 - 0.0 = 1.0. The OLD
    # mean-of-means would have been [mean(1.0,0.0), mean(1.0)] = [0.5, 1.0] -> 0.5.
    assert panel["repair_delta"] == 1.0


def test_repair_delta_averages_multiple_repaired_claims():
    """Multiple repaired claims: mean of each claim's own first->last lift."""
    panel = credibility_panel(
        passed_claims=[],
        total_claims=0,
        required_fields=[],
        covered_fields=[],
        round_indices=[1, 2],
        # B lift 0.6, C lift 0.2; D never revised (ignored). mean(0.6, 0.2)=0.4.
        claim_version_groundedness={"B": [0.2, 0.8], "C": [0.5, 0.7], "D": [0.9]},
    )
    assert panel["repair_delta"] == 0.4


def test_claim_missing_groundedness_defaults_to_zero():
    panel = credibility_panel(
        passed_claims=[{"id": "C1"}, {"id": "C2", "groundedness": 1.0}],
        total_claims=2,
        required_fields=["a"],
        covered_fields=["a"],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.2, 0.4]},
    )
    assert panel["avg_groundedness"] == 0.5  # (0.0 + 1.0) / 2


# ---------------------------------------------------------------------------
# is_tier_upgrade: honest weak→strong signal (a TRUE tier increase, not just a
# groundedness scalar bump). GA3.
# ---------------------------------------------------------------------------


def _panel(claim_version_strengths):
    """credibility_panel with neutral KPIs, varying only the tier history."""
    return credibility_panel(
        passed_claims=[],
        total_claims=0,
        required_fields=[],
        covered_fields=[],
        round_indices=[],
        claim_version_strengths=claim_version_strengths,
    )


def test_tier_upgrade_weak_to_moderate_is_true():
    assert _panel({"C1": ["weak", "moderate"]})["is_tier_upgrade"] is True


def test_tier_upgrade_weak_to_strong_is_true():
    assert _panel({"C1": ["weak", "strong"]})["is_tier_upgrade"] is True


def test_tier_upgrade_moderate_to_strong_is_true():
    assert _panel({"C1": ["moderate", "strong"]})["is_tier_upgrade"] is True


def test_tier_upgrade_same_tier_is_false():
    # Even a positive groundedness delta within one tier is NOT a tier upgrade.
    assert _panel({"C1": ["moderate", "moderate"]})["is_tier_upgrade"] is False


def test_tier_upgrade_single_version_is_false():
    assert _panel({"C1": ["strong"]})["is_tier_upgrade"] is False


def test_tier_upgrade_downgrade_only_is_false():
    assert _panel({"C1": ["strong", "weak"]})["is_tier_upgrade"] is False


def test_tier_upgrade_dip_then_recover_above_start_is_true():
    # strong→weak→strong: the weak→strong leg is still a strict increase.
    assert _panel({"C1": ["strong", "weak", "strong"]})["is_tier_upgrade"] is True


def test_tier_upgrade_any_one_claim_triggers():
    panel = _panel({"C1": ["moderate", "moderate"], "C2": ["weak", "moderate"]})
    assert panel["is_tier_upgrade"] is True


def test_tier_upgrade_empty_history_is_false():
    assert _panel({})["is_tier_upgrade"] is False


def test_tier_upgrade_unknown_tier_strings_ignored():
    # Non-tier strings must not raise and must not count as an upgrade.
    assert _panel({"C1": ["weak", "???"]})["is_tier_upgrade"] is False


def test_tier_upgrade_omitted_arg_defaults_false():
    # Backward compatible: callers that don't pass the new kwarg get False.
    panel = credibility_panel(
        passed_claims=[{"id": "C1", "groundedness": 0.8}],
        total_claims=1,
        required_fields=["a"],
        covered_fields=["a"],
        round_indices=[1, 2],
        claim_version_groundedness={"C1": [0.4, 0.9]},
    )
    assert panel["is_tier_upgrade"] is False
