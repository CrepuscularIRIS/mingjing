"""Human-labeled QA-gate calibration set (Task M6).

Loads ``tests/fixtures/qa_calibration.json`` — 43 hand-labeled claimsets whose
``expected_codes`` were reasoned from ``src/mingjing/qa/rules.py`` and
``src/mingjing/scoring.py`` (NOT by running ``qa_check`` and copying its output).

It then runs the real :func:`mingjing.qa.rules.qa_check` over each case and:

1. asserts ``expected == actual`` per case (the gate behaves exactly as labeled);
2. computes per-:class:`~mingjing.schemas.IssueCode` precision/recall over the set;
3. computes claimset-level admit/withhold (binary) precision/recall/accuracy,
   where "withhold" = the gate emitted at least one issue (verdict ``reject``)
   and "admit" = it emitted none (verdict ``pass``).

A ``known_gaps`` array in the fixture (currently empty) holds any case where the
labeler judged the gate's true behavior a genuine gap rather than a label error;
such cases assert the gate's CURRENT behavior (documented, not corrected here) so
the suite stays green while the gap is reported transparently in CALIBRATION.md.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from mingjing.qa.rules import qa_check
from mingjing.schemas import IssueCode

_FIXTURE = Path(__file__).parent / "fixtures" / "qa_calibration.json"

# Every code that appears in the gate, so per-code metrics report a full table
# (a code that never fires still gets a row, avoiding a silently-missing rule).
_ALL_CODES: tuple[str, ...] = tuple(c.value for c in IssueCode)


def _load() -> dict[str, Any]:
    with _FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


def _actual_codes(claimset: dict[str, Any]) -> set[str]:
    """The set of distinct IssueCode strings the gate emits for ``claimset``."""
    return {issue.code.value for issue in qa_check(claimset)}


def _case_index() -> dict[str, dict[str, Any]]:
    data = _load()
    return {case["id"]: case for case in data["cases"]}


def test_fixture_shape_and_coverage() -> None:
    """The fixture meets the M6 coverage contract (counts, labels, sub-fields)."""
    data = _load()
    cases = data["cases"]
    assert data.get("labeled_by") == "human-review 2026-06-10"
    assert len(cases) >= 40, f"expected >=40 cases, found {len(cases)}"

    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"

    # Every case mirrors the qa_check input contract.
    for c in cases:
        assert set(c) >= {"id", "description", "claimset", "expected_codes"}
        assert c["description"].strip(), f"{c['id']} needs a description"
        cs = c["claimset"]
        assert set(cs) == {"claims", "sources", "coverage"}, c["id"]
        for code in c["expected_codes"]:
            assert code in _ALL_CODES, f"{c['id']} unknown code {code}"

    # >=10 clean (empty expected_codes).
    clean = [c for c in cases if not c["expected_codes"]]
    assert len(clean) >= 10, f"need >=10 clean cases, found {len(clean)}"

    # Each of the 7 code names appears as a positive >=3 times. (IssueCode has 6
    # members; SCHEMA_GAP doubles as the inference-lineage code, so it is the 7th
    # *behavioral* class the task enumerates. We assert >=3 on every IssueCode.)
    per_code_pos: dict[str, int] = defaultdict(int)
    for c in cases:
        for code in set(c["expected_codes"]):
            per_code_pos[code] += 1
    for code in _ALL_CODES:
        assert per_code_pos[code] >= 3, f"{code} has only {per_code_pos[code]} positives (<3)"

    # >=8 boundary / near-miss cases (ids prefixed BOUNDARY-).
    boundary = [c for c in cases if c["id"].startswith("BOUNDARY-")]
    assert len(boundary) >= 8, f"need >=8 boundary cases, found {len(boundary)}"


@pytest.mark.parametrize("case_id", list(_case_index().keys()))
def test_each_case_matches_label(case_id: str) -> None:
    """Per case: the gate's emitted codes equal the human label.

    A case listed in ``known_gaps`` instead asserts the gate's CURRENT behavior
    (the gap is documented in CALIBRATION.md, not silently corrected by editing
    rules.py — the铁律 forbids weakening the gate).
    """
    data = _load()
    case = _case_index()[case_id]
    known_gaps = {g["id"] for g in data.get("known_gaps", [])}
    actual = _actual_codes(case["claimset"])
    expected = set(case["expected_codes"])

    if case_id in known_gaps:
        gap = next(g for g in data["known_gaps"] if g["id"] == case_id)
        # The gap entry records the gate's true behavior; assert exactly that.
        assert actual == set(gap["actual_codes"]), (
            f"{case_id} known-gap actual drifted from documented behavior"
        )
        return

    assert actual == expected, (
        f"{case_id}: expected {sorted(expected)} got {sorted(actual)} "
        f"-- {case['description']}"
    )


def _confusion() -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Compute per-code TP/FP/FN and the binary admit/withhold confusion matrix.

    Cases in ``known_gaps`` are EXCLUDED from the precision/recall population:
    they measure a labeler-acknowledged gate gap, not gate accuracy against a
    trusted label, so folding them in would distort the headline numbers.

    Returns:
        ``(per_code, binary)`` where ``per_code[code]`` has ``tp/fp/fn`` and
        ``binary`` has ``tp/fp/fn/tn`` for the withhold-positive convention
        (positive = "withhold" = gate emitted >=1 issue).
    """
    data = _load()
    known_gaps = {g["id"] for g in data.get("known_gaps", [])}

    per_code: dict[str, dict[str, int]] = {
        code: {"tp": 0, "fp": 0, "fn": 0} for code in _ALL_CODES
    }
    binary = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

    for case in data["cases"]:
        if case["id"] in known_gaps:
            continue
        expected = set(case["expected_codes"])
        actual = _actual_codes(case["claimset"])

        for code in _ALL_CODES:
            in_exp = code in expected
            in_act = code in actual
            if in_exp and in_act:
                per_code[code]["tp"] += 1
            elif in_act and not in_exp:
                per_code[code]["fp"] += 1
            elif in_exp and not in_act:
                per_code[code]["fn"] += 1

        # Binary: positive class = "withhold" (gate found >=1 issue).
        exp_withhold = bool(expected)
        act_withhold = bool(actual)
        if exp_withhold and act_withhold:
            binary["tp"] += 1
        elif act_withhold and not exp_withhold:
            binary["fp"] += 1
        elif exp_withhold and not act_withhold:
            binary["fn"] += 1
        else:
            binary["tn"] += 1

    return per_code, binary


def _precision(tp: int, fp: int) -> float:
    return tp / (tp + fp) if (tp + fp) else 1.0


def _recall(tp: int, fn: int) -> float:
    return tp / (tp + fn) if (tp + fn) else 1.0


def test_binary_admit_withhold_metrics_are_perfect_on_calibration_set() -> None:
    """Claimset-level admit/withhold precision/recall/accuracy on the labeled set.

    With zero ``known_gaps`` every case matches its label, so all three metrics
    are 1.0. Should a real gap ever be recorded, that case is excluded from this
    population (see ``_confusion``) and the assertion still reflects gate
    accuracy on the trusted-label subset.
    """
    _per_code, binary = _confusion()
    tp, fp, fn, tn = binary["tp"], binary["fp"], binary["fn"], binary["tn"]
    total = tp + fp + fn + tn
    assert total >= 40

    precision = _precision(tp, fp)
    recall = _recall(tp, fn)
    accuracy = (tp + tn) / total

    assert precision == 1.0, f"admit/withhold precision {precision} (fp={fp})"
    assert recall == 1.0, f"admit/withhold recall {recall} (fn={fn})"
    assert accuracy == 1.0, f"accuracy {accuracy} (fp={fp}, fn={fn})"


def test_per_code_precision_recall_are_perfect_on_calibration_set() -> None:
    """Per-IssueCode precision/recall on the labeled set.

    Each code's positives (>=3, asserted in test_fixture_shape_and_coverage) give
    a real denominator; with zero known_gaps each is 1.0/1.0.
    """
    per_code, _binary = _confusion()
    for code, c in per_code.items():
        p = _precision(c["tp"], c["fp"])
        r = _recall(c["tp"], c["fn"])
        assert p == 1.0, f"{code} precision {p} (tp={c['tp']} fp={c['fp']})"
        assert r == 1.0, f"{code} recall {r} (tp={c['tp']} fn={c['fn']})"


def test_emit_metrics_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the full calibration scoreboard (visible with ``pytest -s``).

    Not an assertion of new behavior — it surfaces the precision/recall numbers
    that back the CALIBRATION.md table so the doc and the suite can never silently
    diverge.
    """
    per_code, binary = _confusion()
    lines = ["QA calibration scoreboard", "per-IssueCode  P / R  (tp,fp,fn)"]
    for code, c in per_code.items():
        p = _precision(c["tp"], c["fp"])
        r = _recall(c["tp"], c["fn"])
        lines.append(
            f"  {code:<22} {p:.2f} / {r:.2f}  ({c['tp']},{c['fp']},{c['fn']})"
        )
    tp, fp, fn, tn = binary["tp"], binary["fp"], binary["fn"], binary["tn"]
    total = tp + fp + fn + tn
    lines.append(
        f"binary admit/withhold  P={_precision(tp, fp):.2f} "
        f"R={_recall(tp, fn):.2f} acc={(tp + tn) / total:.2f} "
        f"(tp={tp},fp={fp},fn={fn},tn={tn},n={total})"
    )
    report = "\n".join(lines)
    print(report)
    captured = capsys.readouterr()
    assert "calibration scoreboard" in captured.out
