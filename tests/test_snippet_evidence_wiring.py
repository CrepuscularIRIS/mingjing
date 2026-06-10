"""Regression: the analyst's verbatim snippet must actually reach the claim.

The T7 prompt instructs the model to return evidence:[{source_id, snippet, ...}],
but snippet_for originally only read payload["snippets"] (a dict keyed by source
id that the prompt never asks for), so the model's verbatim span was discarded and
snippet_for always fell back to statement-in-raw / raw[:200]. This wires the
evidence-list snippet into the claim (still gated by the QA HALLUCINATED_SNIPPET
check, which verifies the snippet is a substring of the source raw_text).
"""

from mingjing.claim_builder import build_claim, relevance, snippet_for
from mingjing.qa.rules import _normalize_ws, qa_check
from mingjing.schemas import IssueCode


def test_reads_verbatim_snippet_from_evidence_list():
    payload = {
        "statement": "Notion has tiered pricing",
        "evidence": [
            {"source_id": "s1", "snippet": "Pro tier costs $10/mo", "relevance": "supports"},
        ],
    }
    src = {"id": "s1", "raw_text": "Notion: Pro tier costs $10/mo billed monthly. More text."}
    assert snippet_for(payload, src) == "Pro tier costs $10/mo"


def test_snippets_dict_still_takes_precedence_when_present():
    # Backward compat: the legacy `snippets` dict wins if provided.
    payload = {
        "snippets": {"s1": "from dict"},
        "evidence": [{"source_id": "s1", "snippet": "from list"}],
    }
    src = {"id": "s1", "raw_text": "from dict and from list both present"}
    assert snippet_for(payload, src) == "from dict"


def test_falls_back_to_statement_when_no_matching_evidence_snippet():
    payload = {
        "statement": "Acme is a SaaS",
        "evidence": [{"source_id": "OTHER", "snippet": "unrelated"}],
    }
    src = {"id": "s1", "raw_text": "Background: Acme is a SaaS company founded in 2010."}
    assert snippet_for(payload, src) == "Acme is a SaaS"


def test_evidence_entry_without_snippet_falls_through():
    payload = {"statement": "X", "evidence": [{"source_id": "s1"}]}  # no snippet key
    src = {"id": "s1", "raw_text": "X marks the spot"}
    assert snippet_for(payload, src) == "X"


def test_non_string_evidence_snippet_does_not_crash_and_falls_back():
    """Regression: the LLM may emit a non-string `snippet` (list/number/null).
    snippet_for is typed `-> str`; a non-string must be ignored (fall back), never
    returned — else paragraph_locator/_norm runs re.sub on a non-str → TypeError
    crashes build_claim (which is outside the analyze try/except → crashes the run)."""
    raw = "Acme is a SaaS company."
    for bad in (["a", "b"], 42, {"x": 1}, True):
        payload = {"statement": "Acme is a SaaS", "evidence": [{"source_id": "s1", "snippet": bad}]}
        out = snippet_for(payload, {"id": "s1", "raw_text": raw})
        assert isinstance(out, str), f"snippet_for must return str, got {type(out)} for {bad!r}"
        assert out == "Acme is a SaaS"  # statement-in-raw fallback


def test_non_string_snippets_dict_value_does_not_crash():
    """Same hardening for the legacy `snippets` dict path."""
    payload = {"statement": "X here", "snippets": {"s1": ["not", "a", "string"]}}
    out = snippet_for(payload, {"id": "s1", "raw_text": "X here and more"})
    assert isinstance(out, str) and out == "X here"


def test_non_string_statement_in_fallback_does_not_crash():
    """The fallback `statement in raw` crashes if statement is non-string
    (`42 in "abc"` → TypeError). snippet_for must stay total → str."""
    raw = "Some source text about pricing."
    for bad_stmt in (42, ["a"], {"k": 1}, True, 3.14):
        payload = {"statement": bad_stmt}  # no usable snippet → hits fallback
        out = snippet_for(payload, {"id": "s1", "raw_text": raw})
        assert isinstance(out, str), f"non-str statement {bad_stmt!r} must not crash/return non-str"
        assert out == raw[:200]


def test_non_string_or_missing_raw_text_does_not_crash():
    """raw_text may be missing/None/non-str; snippet_for must still return a str."""
    for bad_raw in (None, 999, ["x"], {"a": 1}):
        out = snippet_for({"statement": "anything"}, {"id": "s1", "raw_text": bad_raw})
        assert isinstance(out, str)
    # entirely empty payload + source_row
    assert snippet_for({}, {"id": "s1"}) == ""


# --- G5: the deterministic relevance contract (why QA never over-rejects via
# a stray relevance string) ------------------------------------------------------
#
# qa._evidence_tuples scores strength from evidence[i]["relevance"], and only
# "supports" counts toward a domain. If the analyst's free-text relevance leaked
# through, a genuinely-supporting source tagged e.g. "direct" would be scored as
# non-supporting and the claim wrongly flagged WEAK_EVIDENCE. claim_builder.relevance
# is the deterministic gate that overwrites the LLM value: it emits exactly
# "supports" (source is in the supporting set) or "unrelated" — never "direct" or any
# other free-text label — so that false-reject path is unreachable in production.
def test_production_relevance_is_only_supports_or_unrelated():
    assert relevance("s1", {"s1"}) == "supports"
    assert relevance("s2", {"s1"}) == "unrelated"
    # exhaustive: every (source, supporting-set) outcome is one of the two literals
    for sid, supporting in [("a", set()), ("a", {"a"}), ("a", {"b"}), ("a", {"a", "b"})]:
        assert relevance(sid, supporting) in ("supports", "unrelated")


# --- G21a (revised after Codex BLOCKING findings): the snippet contract is
# VERBATIM-OR-REJECT. The analyst candidate is returned UNCHANGED; the QA
# HALLUCINATED_SNIPPET gate verifies it is a real substring of raw_text. We do NOT
# rewrite a non-verbatim snippet to a "best-match" source span — token-overlap
# grounding cannot separate a genuine reworded paraphrase from a fabrication (both
# can share only the competitor name / ~20% of CJK bigrams), so any substitution
# would mask fabrications behind real source text. Paraphrases are rejected and the
# claim is re-collected/revised; value grounding (VALUE_UNSUPPORTED) is independent.


def _is_verbatim_substring(snippet: str, raw: str) -> bool:
    """Mirror the QA HALLUCINATED_SNIPPET gate: whitespace-normalized substring,
    NO lowercasing (qa.rules._check_hallucinated_snippet semantics)."""
    norm = _normalize_ws(snippet)
    return bool(norm) and norm in _normalize_ws(raw)


def test_paraphrased_snippet_returned_as_is_for_gate_to_reject():
    """A paraphrased evidence snippet (not verbatim in raw_text) is returned AS-IS
    so the QA HALLUCINATED_SNIPPET gate rejects it — never silently rewritten to a
    real source span (which would mask the fact the analyst did not actually quote)."""
    raw = (
        "飞书是字节跳动旗下的一站式协作平台，集成即时通讯、日历、云文档与会议功能。"
        "飞书的付费版本按用户席位计费，提供标准版与旗舰版两档方案。"
    )
    paraphrase = "飞书按席位收费并有两个付费档位"  # not a verbatim substring of raw
    payload = {
        "statement": "飞书提供标准版与旗舰版两档方案",
        "evidence": [{"source_id": "s1", "snippet": paraphrase, "relevance": "supports"}],
    }
    out = snippet_for(payload, {"id": "s1", "raw_text": raw})
    assert out == paraphrase, "non-verbatim snippet must be returned unchanged"
    assert not _is_verbatim_substring(out, raw), (
        "the paraphrase is NOT a verbatim span, so the gate will reject it"
    )


def test_verbatim_snippet_admitted_as_is():
    """A candidate snippet that IS a verbatim span of raw_text is returned unchanged."""
    raw = "飞书的付费版本按用户席位计费，提供标准版与旗舰版两档方案。"
    verbatim = "提供标准版与旗舰版两档方案"
    payload = {
        "statement": "飞书有两档付费方案",
        "evidence": [{"source_id": "s1", "snippet": verbatim, "relevance": "supports"}],
    }
    assert snippet_for(payload, {"id": "s1", "raw_text": raw}) == verbatim


def test_verbatim_snippet_with_whitespace_diff_admitted_as_is():
    """A candidate verbatim under whitespace normalization (collapsed runs) is
    admitted as-is — the gate normalizes whitespace, so snippet_for must agree."""
    raw = "Pro tier costs\n\n$10  per   month, billed annually."
    candidate = "Pro tier costs $10 per month"  # differs only by whitespace runs
    payload = {
        "statement": "Pro tier is $10/mo",
        "evidence": [{"source_id": "s1", "snippet": candidate, "relevance": "supports"}],
    }
    out = snippet_for(payload, {"id": "s1", "raw_text": raw})
    assert out == candidate
    assert _is_verbatim_substring(out, raw)


def _src_qa(text: str, source_type: str = "official") -> dict:
    return {"raw_text": text, "source_type": source_type}


def test_verbatim_evidence_snippet_passes_hallucinated_snippet_gate():
    """End-to-end: a claim whose analyst snippet IS a verbatim quote of the source,
    built via build_claim (which calls snippet_for) then run through qa_check, must
    NOT raise HALLUCINATED_SNIPPET — the verbatim quote is admitted unchanged."""
    from mingjing.db import Database

    db = Database(":memory:")
    db.init_schema()
    raw = (
        "Acme offers a Free tier and a Pro tier. "
        "The Pro tier costs $10 per month, billed annually."
    )
    src_rows = [
        {
            "id": "S1",
            "url": "https://acme.example.com/pricing",
            "raw_text": raw,
            "source_type": "official",
        }
    ]
    payload = {
        "statement": "Acme has a Pro tier",
        # verbatim quote — a real substring of raw
        "evidence": [
            {"source_id": "S1", "snippet": "The Pro tier costs $10 per month", "relevance": "supports"}
        ],
        "evidence_ref": ["S1"],
        "value": {"tiers": ["Pro tier"]},
    }
    claim = build_claim(db, "run-g21a", {"field": "pricing_model", "competitor": "Acme"}, src_rows, payload)

    chosen = claim["evidence"][0]["snippet"]
    assert chosen == "The Pro tier costs $10 per month", "verbatim snippet returned unchanged"
    assert _is_verbatim_substring(chosen, raw)

    claimset = {
        "claims": [claim],
        "sources": {"S1": _src_qa(raw, "official")},
        "coverage": {"required_fields": ["pricing_model"], "covered_fields": ["pricing_model"]},
    }
    codes = {i.code for i in qa_check(claimset)}
    assert IssueCode.HALLUCINATED_SNIPPET not in codes, (
        "a verbatim snippet must not trip the HALLUCINATED_SNIPPET gate"
    )


def test_nonverbatim_snippet_is_rejected_by_hallucinated_snippet_gate():
    """The companion to the above: a non-verbatim (paraphrased) analyst snippet,
    built via build_claim, MUST trip HALLUCINATED_SNIPPET — proving snippet_for did
    not silently rewrite it to a real span to sneak it past the gate."""
    from mingjing.db import Database

    db = Database(":memory:")
    db.init_schema()
    raw = (
        "Acme offers a Free tier and a Pro tier. "
        "The Pro tier costs $10 per month, billed annually."
    )
    src_rows = [
        {"id": "S1", "url": "https://acme.example.com/pricing", "raw_text": raw, "source_type": "official"}
    ]
    payload = {
        "statement": "Acme has a Pro tier",
        # paraphrase sharing only the competitor name — NOT a verbatim substring
        "evidence": [
            {"source_id": "S1", "snippet": "Acme charges ten dollars monthly", "relevance": "supports"}
        ],
        "evidence_ref": ["S1"],
        "value": {"tiers": ["Pro tier"]},
    }
    claim = build_claim(db, "run-g21a2", {"field": "pricing_model", "competitor": "Acme"}, src_rows, payload)
    assert claim["evidence"][0]["snippet"] == "Acme charges ten dollars monthly", (
        "non-verbatim snippet must be returned unchanged, not rewritten"
    )
    claimset = {
        "claims": [claim],
        "sources": {"S1": _src_qa(raw, "official")},
        "coverage": {"required_fields": ["pricing_model"], "covered_fields": ["pricing_model"]},
    }
    codes = {i.code for i in qa_check(claimset)}
    assert IssueCode.HALLUCINATED_SNIPPET in codes, (
        "a non-verbatim snippet must trip HALLUCINATED_SNIPPET (no silent grounding)"
    )


def test_fabricated_snippet_zero_overlap_is_not_masked():
    """Codex BLOCKING regression (G21a): a FABRICATED snippet that shares no
    distinctive content with the source must NOT be silently replaced by a real
    source slice — it must reach the QA HALLUCINATED_SNIPPET gate and be rejected.

    The first G21a cut scored overlap on the shared CHARACTER SET, so any English
    fabrication shared common letters with any English source and got grounded to
    raw[:200], masking the hallucination. snippet_for must instead detect that no
    real span shares distinctive content (words/CJK bigrams) and return the
    candidate UNCHANGED so the gate catches it."""
    from mingjing.db import Database

    db = Database(":memory:")
    db.init_schema()
    raw = "Acme offers a Free tier for small teams."
    src_rows = [
        {"id": "S1", "url": "https://acme.example.com/pricing", "raw_text": raw, "source_type": "official"}
    ]
    fabricated = "Phantom Platinum Plan includes SOC2 and HIPAA guarantees"
    payload = {
        "statement": "Acme has pricing information",
        "evidence": [{"source_id": "S1", "snippet": fabricated, "relevance": "supports"}],
        "evidence_ref": ["S1"],
        # grounded required value leaf so VALUE_UNSUPPORTED does NOT fire — isolates
        # the snippet-grounding path (the only gate that should catch the fabrication)
        "value": {"tiers": ["Free tier"]},
    }
    # Unit: snippet_for must NOT convert a zero-overlap fabrication into a real span.
    assert snippet_for(payload, {"id": "S1", "raw_text": raw}) == fabricated, (
        "a fabricated snippet sharing no distinctive content must be returned as-is"
    )

    # End-to-end: build_claim + qa_check must flag HALLUCINATED_SNIPPET.
    claim = build_claim(db, "run-fab", {"field": "pricing_model", "competitor": "Acme"}, src_rows, payload)
    claimset = {
        "claims": [claim],
        "sources": {"S1": _src_qa(raw, "official")},
        "coverage": {"required_fields": ["pricing_model"], "covered_fields": ["pricing_model"]},
    }
    codes = {i.code for i in qa_check(claimset)}
    assert IssueCode.HALLUCINATED_SNIPPET in codes, (
        "a fabricated (zero-overlap) snippet must trip HALLUCINATED_SNIPPET, not be masked"
    )


def test_value_unsupported_still_strict_after_snippet_grounding():
    """The snippet fix must NOT bypass value grounding: a claim whose REQUIRED
    value leaf is absent from the cited source STILL triggers VALUE_UNSUPPORTED."""
    from mingjing.db import Database

    db = Database(":memory:")
    db.init_schema()
    raw = "Acme offers a Free tier and a Pro tier billed monthly."
    src_rows = [
        {"id": "S1", "url": "https://acme.example.com/pricing", "raw_text": raw, "source_type": "official"}
    ]
    payload = {
        "statement": "Acme has a Phantom Platinum Plan",
        "evidence": [{"source_id": "S1", "snippet": "Acme has a secret plan", "relevance": "supports"}],
        "evidence_ref": ["S1"],
        # fabricated required value leaf absent from raw_text
        "value": {"tiers": ["Phantom Platinum Plan"]},
    }
    claim = build_claim(db, "run-vu", {"field": "pricing_model", "competitor": "Acme"}, src_rows, payload)
    claimset = {
        "claims": [claim],
        "sources": {"S1": _src_qa(raw, "official")},
        "coverage": {"required_fields": ["pricing_model"], "covered_fields": ["pricing_model"]},
    }
    codes = {i.code for i in qa_check(claimset)}
    assert IssueCode.VALUE_UNSUPPORTED in codes, (
        "ungrounded required value leaf must still fail VALUE_UNSUPPORTED"
    )
