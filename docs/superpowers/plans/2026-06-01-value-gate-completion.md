# Value-Gate Completion (required-numeric grounding) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Close the last bounded LLM-reachable hole in the deterministic value gate — bare NUMERIC leaves under REQUIRED sub-fields are currently never grounded (the hard gate's `_collect_string_leaves` skips int/float), so a fabricated required number could reach `status=pass`. Extend the hard gate to ground required numeric leaves by whole-token equality, with the derived-structural exemption.

**Architecture:** `_check_value_unsupported` (qa/rules.py) is the required-sub-field hard gate (emits `VALUE_UNSUPPORTED` → reject). It already grounds string leaves (substring) under required sub-fields. We add: collect numeric leaves under required sub-fields (excluding `_DERIVED_NUMERIC_SUBFIELDS`), ground each by whole-token numeric equality (reuse `_source_numbers`/the `_NUM_TOKEN` logic added for the optional prune), and add ungrounded ones to the unsupported list. No new IssueCode; same reject/route path. Booleans stay interpretive (skipped). In practice the analyst emits required magnitudes string-embedded (`tiers: ["Pro $10/mo"]`) which the string check already grounds, so this rarely fires — it closes the theoretical bare-number hole symmetric to the optional fix, and preempts the next review.

**Tech Stack:** Python 3.12 · pytest · existing `qa/rules.py` (`_check_value_unsupported`, `_source_numbers`, `_NUM_TOKEN`, `_DERIVED_NUMERIC_SUBFIELDS`, `_collect_string_leaves`, `_is_checkable_leaf`, `_normalize_ws`).

---

## Task 1: Ground required-sub-field numeric leaves (whole-token, derived-exempt)

**Files:**
- Modify: `src/mingjing/qa/rules.py` (`_check_value_unsupported`)
- Test: `tests/test_qa_rules.py`

- [ ] **Step 1: Write failing tests** (append to tests/test_qa_rules.py)

```python
def test_required_numeric_leaf_must_be_grounded():
    """A bare fabricated NUMBER under a REQUIRED sub-field is hard-gated
    (VALUE_UNSUPPORTED) when it is not a whole numeric token in the cited source —
    symmetric to the optional-number prune, but a reject (required can't be withheld)."""
    from mingjing.qa.rules import qa_check
    from mingjing.schemas import IssueCode
    claimset = {
        "claims": [{
            "id": "RN1", "schema_field": "feature_tree", "claim_type": "fact",
            "competitor": "X",
            # categories is REQUIRED; embed a bare fabricated count number in it.
            "value": {"categories": [{"name": "Collaboration", "count": 99999}]},
            "evidence": [{"source_id": "s1", "snippet": "Collaboration features.", "relevance": "direct"}],
        }],
        "sources": {"s1": {"raw_text": "Collaboration features across 12 tools.", "source_type": "official", "url": "https://x.com"}},
        "coverage": {"required_fields": [], "covered_fields": []},
    }
    codes = {i.code for i in qa_check(claimset)}
    assert IssueCode.VALUE_UNSUPPORTED in codes  # 99999 not a source token → flagged


def test_required_numeric_leaf_grounded_passes():
    """A required number present as a whole token in the source is NOT flagged."""
    from mingjing.qa.rules import qa_check
    from mingjing.schemas import IssueCode
    claimset = {
        "claims": [{
            "id": "RN2", "schema_field": "feature_tree", "claim_type": "fact",
            "competitor": "X",
            "value": {"categories": [{"name": "Collaboration", "count": 12}]},
            "evidence": [{"source_id": "s1", "snippet": "12 tools.", "relevance": "direct"}],
        }],
        "sources": {"s1": {"raw_text": "Collaboration features across 12 tools.", "source_type": "official", "url": "https://x.com"}},
        "coverage": {"required_fields": [], "covered_fields": []},
    }
    vu = [i for i in qa_check(claimset) if i.code == IssueCode.VALUE_UNSUPPORTED]
    assert vu == []  # 12 IS a whole source token → grounded
```

- [ ] **Step 2: Run, verify FAIL** — `uv run pytest tests/test_qa_rules.py -k "required_numeric" -v`. The first test FAILS (numbers under required are not currently grounded).

- [ ] **Step 3: Implement** — in `_check_value_unsupported`, after the string-leaf loop, also collect+ground numeric leaves under required sub-fields. Reuse a numeric-leaf collector (mirror `_collect_string_leaves` but for int/float, bool excluded) and `_source_numbers(haystack)`. EXEMPT sub-fields in `_DERIVED_NUMERIC_SUBFIELDS`. Add ungrounded numbers (as their string form) to the existing `unsupported` list so a single `VALUE_UNSUPPORTED` issue is emitted. Keep behavior identical for string leaves.

- [ ] **Step 4: Run, verify PASS + full qa suites** — `uv run pytest tests/test_qa_rules.py tests/test_qa.py -v` then `uv run pytest -q`. New tests pass; full suite stays green (was 507). Report exact count.

- [ ] **Step 5: Commit**

```bash
git add src/mingjing/qa/rules.py tests/test_qa_rules.py
git commit -m "fix(qa): ground required-sub-field numeric leaves (whole-token, derived-exempt) — close symmetric value-gate hole"
```

## Self-Review
- Spec coverage: required numeric leaves grounded by whole-token equality (Task 1); derived-exempt; bool excluded; string behavior unchanged; same VALUE_UNSUPPORTED reject path. ✓
- Out of scope (documented): coincidental numeric equality (inherent, needs span-binding); string paraphrase (substring by design).
