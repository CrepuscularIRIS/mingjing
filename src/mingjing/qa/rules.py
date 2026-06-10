"""Deterministic QA verifier rules (plan Task 12, PURE test #2 / spec §13).

``qa_check`` runs six independent checks over a claimset and returns a flat list
of :class:`Issue`. A clean, strong, fully-covered claimset returns ``[]``.

The six checks, each emitting one :class:`~mingjing.schemas.IssueCode`:

1. ``SCHEMA_GAP``          — a claim omits a ``required`` sub-field for its field.
2. ``WEAK_EVIDENCE``       — :func:`mingjing.scoring.strength` scores the claim
                             ``"weak"`` from its evidence metadata.
3. ``HALLUCINATED_SNIPPET``— an evidence snippet is NOT a substring of the cited
                             source's raw text (the anti-fabrication gate).
4. ``CONTRADICTION``       — two claims on the same (competitor, field) carry
                             conflicting values. The verdict is computed from
                             evidence METADATA — never asked of an LLM as freeform
                             text — so an injected string cannot flip the tier
                             (prompt-injection safety).
5. ``LOW_COVERAGE``        — the fraction of required fields actually covered is
                             below :data:`COVERAGE_THRESHOLD`.
6. ``VALUE_UNSUPPORTED``   — a structured value string leaf under a **required**
                             sub-field is not found in any cited source's raw text
                             (value-level anti-fabrication, complements
                             HALLUCINATED_SNIPPET which only checks evidence
                             snippets). Only leaves under required sub-fields are
                             checked; optional sub-fields (e.g. billing_period,
                             currency) are ignored to avoid over-rejecting honest
                             paraphrases.

The input ``claimset`` is a plain dict (see the test module for the exact shape):
``{"claims": [...], "sources": {id: {...}}, "coverage": {...}}``. Each claim's
``evidence`` items are ``{"source_id", "snippet", "relevance"}``.
"""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .. import scoring
from ..collector import independence
from ..schemas import IssueCode, active_field_schemas

# Minimum fraction of required fields that must be covered before LOW_COVERAGE.
COVERAGE_THRESHOLD = 0.8

_WS_RUN = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return _WS_RUN.sub(" ", text or "").strip()


@dataclass(frozen=True)
class Issue:
    """A single QA finding. ``code`` is the load-bearing field the router reads."""

    code: IssueCode
    claim_id: str | None = None
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _evidence_tuples(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> list[tuple[str, str, str]]:
    """Build ``(source_type, relevance, registrable_domain)`` tuples for the scorer.

    The registrable domain is derived from each source's URL via
    :func:`mingjing.collector.independence.registrable_domain` so the scorer can
    dedupe supporting sources by independent domain. When a source carries no
    URL we fall back to its ``source_id`` so distinct ids still count as distinct
    voices rather than collapsing to one blank-domain bucket.
    """
    tuples: list[tuple[str, str, str]] = []
    for ev in claim.get("evidence", []):
        source_id = ev.get("source_id")
        src = sources.get(source_id, {})
        # SIMULATED (fixture-seeded) sources are grounding/display-only — they
        # never feed the tier scorer (scoring.contributes_to_tier).
        if not scoring.contributes_to_tier(src):
            continue
        source_type = src.get("source_type", "web")
        relevance = ev.get("relevance", "unrelated")
        url = src.get("url")
        domain = independence.registrable_domain(url) if url else ""
        if not domain:
            domain = str(source_id)
        tuples.append((source_type, relevance, domain))
    return tuples


def _check_schema_gap(claim: dict[str, Any]) -> list[Issue]:
    """Required sub-fields declared by FIELD_SCHEMAS must be present in value."""
    schema = active_field_schemas().get(claim.get("schema_field", ""))
    if schema is None:
        return []
    value = claim.get("value", {}) or {}
    missing = [f for f in schema["required"] if f not in value or value.get(f) in (None, "", [], {})]
    if missing:
        return [
            Issue(
                code=IssueCode.SCHEMA_GAP,
                claim_id=claim.get("id"),
                detail=f"missing required sub-fields: {missing}",
                meta={"missing": missing},
            )
        ]
    return []


def _check_weak_evidence(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]], contradiction: bool
) -> list[Issue]:
    """Run the transparent scorer; a weak tier is an issue (honest, not hidden)."""
    tier = scoring.strength(
        sources=_evidence_tuples(claim, sources), contradiction=contradiction
    )
    if tier == "weak":
        return [
            Issue(
                code=IssueCode.WEAK_EVIDENCE,
                claim_id=claim.get("id"),
                detail="evidence strength scored weak",
                meta={"strength": tier},
            )
        ]
    return []


def _check_hallucinated_snippet(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> list[Issue]:
    """Every cited snippet must be a verbatim substring of its source raw text."""
    issues: list[Issue] = []
    for ev in claim.get("evidence", []):
        snippet = ev.get("snippet", "")
        src = sources.get(ev.get("source_id"), {})
        raw = src.get("raw_text", "")
        # Normalize whitespace runs to single spaces on BOTH sides before the
        # pure substring check so a snippet that differs only in whitespace
        # (newlines, double spaces, tabs) is not falsely flagged hallucinated.
        norm_snippet = _normalize_ws(snippet)
        if norm_snippet and norm_snippet not in _normalize_ws(raw):
            issues.append(
                Issue(
                    code=IssueCode.HALLUCINATED_SNIPPET,
                    claim_id=claim.get("id"),
                    detail=f"snippet not found in source {ev.get('source_id')}",
                    meta={"source_id": ev.get("source_id"), "snippet": snippet},
                )
            )
    return issues


def _check_contradiction(claims: list[dict[str, Any]]) -> list[Issue]:
    """Two claims on the same (competitor, field) with conflicting values.

    The conflict is detected from the claims' structured ``value``/``statement``
    metadata — deterministically — never from a freeform LLM verdict, so an
    injected instruction in source text cannot suppress or fabricate a conflict.
    """
    issues: list[Issue] = []
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for c in claims:
        key = (c.get("competitor"), c.get("schema_field"))
        groups.setdefault(key, []).append(c)

    for key, group in groups.items():
        if len(group) < 2:
            continue
        # Conflict if the structured values (fallback: statements) are not all equal.
        signatures = {_value_signature(c) for c in group}
        if len(signatures) > 1:
            for c in group:
                issues.append(
                    Issue(
                        code=IssueCode.CONTRADICTION,
                        claim_id=c.get("id"),
                        detail=f"conflicting values for {key[1]} (competitor={key[0]})",
                        meta={"competitor": key[0], "schema_field": key[1]},
                    )
                )
    return issues


def _registrable_domain(url: str) -> str:
    """Registrable domain for a source URL (reuses the collector helper).

    Falls back to the bare netloc if the eTLD+1 reducer returns nothing, so a
    URL like ``https://a.example`` still yields a distinct, comparable domain.
    """
    domain = independence.registrable_domain(url or "")
    if domain:
        return domain
    from urllib.parse import urlparse

    return (urlparse(url or "").netloc or "").lower()


def _source_contradiction_domains(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> tuple[set[str], set[str]]:
    """Return ``(supports_domains, refutes_domains)`` for a claim's evidence.

    Each evidence item carries a per-source ``stance`` enum (``supports`` /
    ``refutes`` / ``neutral``) tagged by the analyst. The verdict is computed
    from these structured enums + the cited source domains — never from freeform
    source prose — so an injected instruction string cannot flip the result.
    A ``neutral`` stance contributes to neither set.
    """
    sup_domains: set[str] = set()
    ref_domains: set[str] = set()
    for ev in claim.get("evidence", []):
        sid = ev.get("source_id")
        src = sources.get(sid, {})
        # Simulated rows contribute to NEITHER side: synthetic data must not
        # manufacture a contradiction (tier cap) nor a corroborating voice.
        if not scoring.contributes_to_tier(src):
            continue
        dom = _registrable_domain(src.get("url", ""))
        stance = ev.get("stance", "supports")
        if stance == "refutes":
            ref_domains.add(dom)
        elif stance == "supports":
            sup_domains.add(dom)
    return sup_domains, ref_domains


def _check_source_contradiction(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> bool:
    """True if the claim's evidence has a supports AND a refutes on DISTINCT domains.

    Requires a supporting domain and a refuting domain that genuinely differ — a
    single site supporting and refuting itself (same registrable domain) is not a
    cross-source contradiction.
    """
    sup_domains, ref_domains = _source_contradiction_domains(claim, sources)
    return any(s != r for s in sup_domains for r in ref_domains)


def _value_signature(claim: dict[str, Any]) -> str:
    """A stable, comparable signature of a claim's asserted value."""
    value = claim.get("value")
    if value:
        # Canonicalize via JSON with sorted keys so nested-dict key ordering can
        # never create a spurious CONTRADICTION (two values equal up to key
        # order produce the same signature). ``default=str`` keeps it total.
        return json.dumps(value, sort_keys=True, default=str)
    return claim.get("statement", "")


def _collect_string_leaves(node: Any, leaves: list[str]) -> None:
    """Recursively collect string leaves from a dict/list value tree.

    Dict KEYS are ignored — only VALUES and list items are examined.
    Non-string scalars (int, float, bool, None) are skipped entirely.
    """
    if isinstance(node, dict):
        for v in node.values():
            _collect_string_leaves(v, leaves)
    elif isinstance(node, list):
        for item in node:
            _collect_string_leaves(item, leaves)
    elif isinstance(node, str):
        leaves.append(node)
    # int / float / bool / None: intentionally ignored


def _collect_numeric_leaves(node: Any, out: list[float]) -> None:
    """Recursively collect numeric (int/float) leaves from a dict/list value tree.

    Mirrors ``_collect_string_leaves``: dict KEYS are ignored — only VALUES and
    list items are examined. Booleans are EXCLUDED (bool is a subclass of int and
    is an interpretive flag, never a source-extracted magnitude) — checked FIRST.
    """
    if isinstance(node, bool):
        return  # interpretive flag — never a groundable magnitude
    if isinstance(node, dict):
        for v in node.values():
            _collect_numeric_leaves(v, out)
    elif isinstance(node, list):
        for item in node:
            _collect_numeric_leaves(item, out)
    elif isinstance(node, (int, float)):
        out.append(node)
    # str / None: intentionally ignored


def _is_checkable_leaf(leaf: str) -> bool:
    """Return True iff this string leaf should be verified against source text.

    Conservative rule: skip leaves that are
    - blank after strip,
    - shorter than 4 characters when measured on the raw-stripped leaf (before
      whitespace normalization) — pure short enums like "USD", "Y", …,
    - entirely non-alphabetic (e.g. "0", "10", "$25").

    A leaf that is 4+ chars (raw-stripped) and contains at least one letter is checkable.
    """
    stripped = leaf.strip()
    return len(stripped) >= 4 and any(c.isalpha() for c in stripped)


def _check_value_unsupported(
    claim: dict[str, Any], sources: dict[str, dict[str, Any]]
) -> list[Issue]:
    """VALUE_UNSUPPORTED: substantial string leaves under **required** sub-fields
    of claim.value must appear in the concatenated raw text of all cited sources
    (case/whitespace-insensitive).

    Only leaves under the field's required sub-fields (per FIELD_SCHEMAS) are
    checked; optional sub-fields are ignored entirely to avoid over-rejecting
    honest paraphrases (e.g. billing_period:"monthly" vs source "billed per month").

    Algorithm:
    1. Look up ``claim["schema_field"]`` in FIELD_SCHEMAS to get required sub-fields.
       If the field has no schema, no required list, or the value has no checkable
       leaves under required keys → emit nothing.
    2. Gather cited source texts; concatenate, normalize whitespace, lowercase.
    3. Collect all string leaves from ``value[k]`` for each required key k only
       (recurse into nested dicts/lists as before; keys themselves are skipped).
    4. A leaf is "checkable" iff it has ≥4 chars and at least one alphabetic char.
    5. A checkable leaf is "unsupported" when it is not a substring of haystack.
    6. If any unsupported leaves exist, emit ONE Issue (not one per leaf).
    7. If no checkable leaves exist under required keys, emit nothing.
    """
    value = claim.get("value")
    if not value:
        return []

    # Determine which sub-fields to check (required sub-fields only).
    schema = active_field_schemas().get(claim.get("schema_field", ""), {})
    required = schema.get("required", [])
    if not required:
        return []

    # Build haystack from all cited source raw texts.
    raw_parts: list[str] = []
    for ev in claim.get("evidence", []):
        src = sources.get(ev.get("source_id"), {})
        raw = src.get("raw_text") or ""
        if raw:
            raw_parts.append(raw)
    haystack = _normalize_ws(" ".join(raw_parts)).lower()

    if not haystack:
        return []

    # Collect string leaves only from required sub-field values.
    leaves: list[str] = []
    for key in required:
        sub_value = value.get(key)
        if sub_value is not None:
            _collect_string_leaves(sub_value, leaves)

    unsupported: list[str] = []
    for leaf in leaves:
        if not _is_checkable_leaf(leaf):
            continue
        normalized_leaf = _normalize_ws(leaf).lower()
        if normalized_leaf not in haystack:
            unsupported.append(leaf)

    # Ground NUMERIC leaves under required sub-fields too (symmetric to the
    # optional-number prune). A bare fabricated number must not reach status=pass
    # ungrounded. Whole-token equality (not substring) via _source_numbers, so
    # 99999 is not grounded by 12 / 120 / a date. DERIVED/structural sub-fields
    # (e.g. depth) are EXEMPT — their numbers are computed, not source verbatim.
    src_nums = _source_numbers(haystack)
    for key in required:
        if key in _DERIVED_NUMERIC_SUBFIELDS:
            continue
        sub_value = value.get(key)
        if sub_value is None:
            continue
        nums: list[float] = []
        _collect_numeric_leaves(sub_value, nums)
        for n in nums:
            target = _to_decimal(n)
            if target is None or target not in src_nums:
                # Render an integer-valued float as "120" (not "120.0") so the
                # diagnostic reads naturally alongside source numbers.
                unsupported.append(
                    str(int(n)) if float(n).is_integer() else str(n)
                )

    if not unsupported:
        return []

    return [
        Issue(
            code=IssueCode.VALUE_UNSUPPORTED,
            claim_id=claim.get("id"),
            detail=f"value required sub-fields not found in cited sources: {unsupported}",
            meta={"unsupported": unsupported},
        )
    ]


def _check_inference_lineage(
    claim: dict[str, Any], known_claim_ids: set[str]
) -> list[Issue]:
    """Validate an inference claim's ``based_on`` lineage INTEGRITY (not existence).

    An inference is confidence-labeled, NOT hard-gated: we do NOT value-verify it
    (no verbatim span — that would be a fake-verify) and we do NOT require it to
    declare a lineage. A lineage-less inference is admitted (the analyst pipeline
    does not always assert a dependency, and re-collecting cannot manufacture a
    claim-to-claim lineage, so rejecting it would be a futile loop).

    What we DO enforce is integrity: if a ``based_on`` lineage IS asserted, every id
    must reference a claim that actually exists in this run. A reference to a
    non-existent claim is a fabricated lineage and is flagged. SCHEMA_GAP is reused
    so the existing collector-routing applies.
    """
    based_on = claim.get("based_on") or []
    unknown = [cid for cid in based_on if cid not in known_claim_ids]
    if unknown:
        return [
            Issue(
                code=IssueCode.SCHEMA_GAP,
                claim_id=claim.get("id"),
                detail=f"inference based_on references unknown claims: {unknown}",
                meta={"reason": "inference_lineage_unknown", "unknown": unknown},
            )
        ]
    return []


# Optional numeric sub-fields that hold DERIVED/STRUCTURAL magnitudes (computed
# from the claim's own structure, e.g. the feature-tree depth) rather than a
# source-EXTRACTED fact. A derived number is legitimately NOT a verbatim source
# substring, so substring-grounding it would wrongly withhold valid data — these
# are exempt from numeric grounding (strings under them are still grounded).
_DERIVED_NUMERIC_SUBFIELDS = frozenset({"depth"})


# A numeric TOKEN in source text: optional comma thousands-groups + optional
# decimal. Matched as a whole token (not a substring) so "12" does NOT ground
# against "120"/"2012"/dates — a fabricated number can't ride a digit-substring.
_NUM_TOKEN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _to_decimal(n: Any) -> Decimal | None:
    """Exact Decimal for a numeric value/token, or None if not numeric.

    Uses ``Decimal(str(n))`` so comparison is EXACT — float equality would collapse
    distinct large integers past 2^53 (e.g. 9007199254740993 == ...992 as float64),
    letting a fabricated large number ride a different real one. ``Decimal`` keeps
    integers exact while still treating ``1200.0`` == ``1200`` and ``9.90`` == ``9.9``.
    """
    try:
        return Decimal(str(n))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _source_numbers(haystack: str) -> set[Decimal]:
    """All numeric tokens in ``haystack`` as exact Decimals (commas stripped)."""
    out: set[Decimal] = set()
    for tok in _NUM_TOKEN.findall(haystack):
        d = _to_decimal(tok.replace(",", ""))
        if d is not None:
            out.add(d)
    return out


def _ground_number(node: float, haystack: str) -> Any:
    """Keep a number iff it equals a whole numeric TOKEN present in the source.

    A fabricated EXTRACTED magnitude (sample_size, price, count) must not bypass
    grounding. Whole-token EXACT (Decimal) equality means a fabricated ``12`` is
    NOT grounded by ``120`` and distinct large integers do NOT collapse, while
    comma formatting (``1,200`` ~ ``1200``) and integer-valued floats
    (``1200.0`` ~ ``1200``) still match.
    """
    target = _to_decimal(node)
    if target is None:
        return node  # not numeric-coercible (shouldn't happen) — leave untouched
    return node if target in _source_numbers(haystack) else None


def _prune_node(node: Any, haystack: str, *, ground_numbers: bool) -> Any:
    """Recursively drop ungrounded checkable leaves from a value sub-tree.

    A string leaf is KEPT iff it is non-checkable (<4 chars / no alpha — short
    enums, codes) OR is a substring of the normalized cited-source ``haystack``.
    When ``ground_numbers`` is True, int/float leaves are also grounded (withheld
    if their string form is absent); when False (a DERIVED/structural sub-field)
    numbers pass through untouched. Booleans are interpretive flags (not
    substring-groundable) and always pass through. Lists drop pruned items; dicts
    drop emptied keys.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            cleaned = _prune_node(v, haystack, ground_numbers=ground_numbers)
            if cleaned not in (None, [], {}, ""):
                out[k] = cleaned
        return out
    if isinstance(node, list):
        kept: list[Any] = []
        for item in node:
            cleaned = _prune_node(item, haystack, ground_numbers=ground_numbers)
            if cleaned not in (None, ""):
                kept.append(cleaned)
        return kept
    if isinstance(node, str):
        if not _is_checkable_leaf(node):
            return node
        return node if _normalize_ws(node).lower() in haystack else None
    # bool is a subclass of int — check it FIRST; a boolean is an interpretive flag.
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)) and ground_numbers:
        return _ground_number(node, haystack)
    return node


def prune_unsupported_optional_leaves(
    value: Any, schema_field: str, cited_source_text: str
) -> Any:
    """Withhold ungrounded checkable leaves under OPTIONAL value sub-fields.

    The deterministic ``VALUE_UNSUPPORTED`` hard gate only governs REQUIRED
    sub-fields; OPTIONAL sub-field leaves are LLM-controlled and would otherwise
    reach the published report ungrounded. This returns a NEW value with such
    optional leaves removed (withheld) — NOT a hard reject — so a fabrication under
    an optional key (e.g. ``negatives``, ``pain_points``) never reaches
    ``status=pass`` while honest paraphrases are not futilely rejected. REQUIRED
    sub-fields are returned untouched (the gate, not this prune, governs them).
    """
    if not isinstance(value, dict):
        return value
    schema = active_field_schemas().get(schema_field or "", {})
    required = set(schema.get("required", []))
    haystack = _normalize_ws(cited_source_text or "").lower()
    pruned: dict[str, Any] = {}
    for key, sub in value.items():
        if key in required:
            pruned[key] = sub  # required: governed by the hard gate, never pruned here
            continue
        # Ground numbers under EXTRACTED-magnitude sub-fields (sample_size, price…);
        # EXEMPT derived/structural ones (depth) whose numbers aren't source verbatim.
        ground_numbers = key not in _DERIVED_NUMERIC_SUBFIELDS
        cleaned = _prune_node(sub, haystack, ground_numbers=ground_numbers)
        if cleaned not in (None, [], {}, ""):
            pruned[key] = cleaned
    return pruned


def _check_low_coverage(coverage: dict[str, Any]) -> list[Issue]:
    """Fraction of required fields covered must meet COVERAGE_THRESHOLD."""
    required = coverage.get("required_fields", []) or []
    if not required:
        return []
    covered = set(coverage.get("covered_fields", []) or [])
    ratio = len([f for f in required if f in covered]) / len(required)
    if ratio < COVERAGE_THRESHOLD:
        return [
            Issue(
                code=IssueCode.LOW_COVERAGE,
                detail=f"coverage {ratio:.2f} below threshold {COVERAGE_THRESHOLD}",
                meta={"ratio": ratio, "threshold": COVERAGE_THRESHOLD},
            )
        ]
    return []


def qa_check(claimset: dict[str, Any]) -> list[Issue]:
    """Run all verifier checks over ``claimset`` and return found issues.

    Seven deterministic check families — schema_gap, weak_evidence,
    hallucinated_snippet, value_unsupported, inference_lineage,
    contradiction (claim-vs-claim AND source-vs-source), low_coverage —
    emitting six ``IssueCode`` values (inference-lineage integrity reuses
    SCHEMA_GAP so the existing collector routing applies).

    Returns an empty list for a clean, strong, fully-covered claimset.
    """
    claims: list[dict[str, Any]] = claimset.get("claims", [])
    sources: dict[str, dict[str, Any]] = claimset.get("sources", {})
    coverage: dict[str, Any] = claimset.get("coverage", {})

    issues: list[Issue] = []

    # Contradiction is computed once (per group) and also feeds the scorer cap.
    contradiction_issues = _check_contradiction(claims)
    contradicted_ids = {i.claim_id for i in contradiction_issues}

    # Source-vs-source contradiction: a single claim whose evidence carries both
    # a `supports` and a `refutes` stance from distinct domains. OR'd into the
    # contradicted-id set so the existing scoring.strength(contradiction=True)
    # cap fires; the verdict is count-driven over structured stance enums, never
    # freeform prose, so an injected string cannot flip it.
    for claim in claims:
        sup_domains, ref_domains = _source_contradiction_domains(claim, sources)
        if any(s != r for s in sup_domains for r in ref_domains):
            cid = claim.get("id")
            contradicted_ids.add(cid)
            contradiction_issues.append(
                Issue(
                    code=IssueCode.CONTRADICTION,
                    claim_id=cid,
                    detail="source-vs-source: supports & refutes from distinct domains",
                    meta={
                        "supports_domains": sorted(sup_domains),
                        "refutes_domains": sorted(ref_domains),
                    },
                )
            )

    # Known claim ids in this run — used to validate inference lineage integrity.
    known_claim_ids = {c.get("id") for c in claims if c.get("id")}

    for claim in claims:
        issues.extend(_check_schema_gap(claim))
        issues.extend(
            _check_weak_evidence(
                claim, sources, contradiction=claim.get("id") in contradicted_ids
            )
        )
        # Value-grounding is UNCONDITIONAL — it runs for every claim regardless of
        # claim_type. ``claim_type`` is LLM-CONTROLLED (the analyst emits it in its
        # JSON), so letting "inference" exempt a claim from value-grounding would let
        # the LLM self-exempt from verification — a direct violation of "LLM proposes,
        # code decides". These checks only inspect leaves under REQUIRED structured
        # sub-fields (substring of cited sources); a genuine inference's interpretive
        # reasoning lives in ``statement`` (ungated free text), so checking concrete
        # structured value leaves is real grounding, not a fake-verify.
        issues.extend(_check_hallucinated_snippet(claim, sources))
        issues.extend(_check_value_unsupported(claim, sources))
        # ``claim_type`` may only ADD requirements, never remove them: an inference
        # ALSO needs sound lineage integrity (an asserted based_on must reference a
        # claim that exists in this run; a lineage-less inference is admitted).
        if claim.get("claim_type") == "inference":
            issues.extend(_check_inference_lineage(claim, known_claim_ids))

    issues.extend(contradiction_issues)
    issues.extend(_check_low_coverage(coverage))
    return issues
