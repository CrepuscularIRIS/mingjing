"""Deterministic "范围与方法 (Scope & Methodology)" report projection (M4).

A professional competitive-intelligence report opens by disclosing WHAT was
analyzed and HOW (ICD-203 transparency / Infomineo narrative). This module
builds that section as a PURE, deterministic projection over already-persisted
ledger data — **no LLM, no DB queries, no network**. The caller (``api.py``)
performs the ledger reads (run row, source rows, withheld disclosure,
credibility panel, trace events) it already does for sibling endpoints and
passes them here; this module only projects.

The honesty contract:
- ``source_stats.independent_domains`` reuses the SAME registrable-domain
  normalization as the scorer (``collector.independence.registrable_domain``)
  and the SAME simulated-source exclusion (``scoring.contributes_to_tier``), so
  the disclosed independent-source count can never diverge from what the 3-tier
  scorer actually counted.
- ``method.rule_count`` is derived from ``len(IssueCode)`` — the real number of
  deterministic QA check families — never a hardcoded literal.
- A SIMULATED source triggers a FIXED disclosure that synthetic questionnaire
  data is display-only and does not earn credibility tiers.
"""

from __future__ import annotations

from typing import Any

from .collector import independence
from .schemas import IssueCode
from .scoring import contributes_to_tier

# A discovery run is identifiable by these trace event types emitted by the
# bounded ``discover`` pre-step (see ``runner._discover_competitors_best_effort``).
_DISCOVERY_EVENT_TYPES = frozenset({"competitors_discovered", "discovery_started"})

# Fixed, honest disclosure appended when any SIMULATED source is present.
_SIMULATED_DISCLOSURE = (
    "模拟问卷数据仅作展示, 不参与可信度分档"
)

# Per-mode one-line inclusion reason (deterministic; competitor name interpolated).
_DIRECTED_REASON = "由用户指定纳入分析"
_DISCOVERY_REASON = "由有界发现 (Discovery) 预筛选纳入"

# Seven deterministic check families (see ``qa/rules.py:qa_check`` docstring)
# map onto ``len(IssueCode)`` issue codes. The family count is structural to
# qa_check; update BOTH this constant and that docstring if a family is added.
_CHECK_FAMILY_COUNT = 7

# The fixed, honest method statements describing how every conclusion is gated.
# ``{fam}``/``{n}`` are filled with the real family / IssueCode counts at build
# time so the report can never drift from the slide-deck phrasing (7 → 6).
_METHOD_STATEMENTS = (
    "证据准入由 {fam} 项确定性校验裁定 (映射 {n} 类 QA 判定码), 全程无 LLM 参与真值裁定 (LLM 仅提议, 代码裁决)",
    "证据强度分 3 档 (强/中/弱), 依据独立可注册域名数量与权威来源类型 (官方/问卷/访谈)",
    "每条证据片段逐字核验: 必须是来源原文的子串, 否则拒绝 (verbatim-or-reject)",
    "结论仅投影 QA 通过的断言; 未通过项保留并在'未纳入项'中诚实披露原因",
)


def _detect_mode(trace_events: list[dict[str, Any]] | None) -> str:
    """Return ``"discovery"`` when a discovery trace event is present, else ``"directed"``.

    A run is discovery-mode iff the bounded ``discover`` pre-step left a
    ``discovery_started`` / ``competitors_discovered`` trace event; otherwise the
    competitor list came straight from the user (directed mode).
    """
    for ev in trace_events or []:
        if (ev.get("event_type") or "") in _DISCOVERY_EVENT_TYPES:
            return "discovery"
    return "directed"


def _build_competitors(
    run: dict[str, Any] | None, mode: str
) -> list[dict[str, str]]:
    """Project the competitor roster with a one-line inclusion reason per mode."""
    names = list((run or {}).get("competitors") or [])
    reason = _DISCOVERY_REASON if mode == "discovery" else _DIRECTED_REASON
    return [{"name": str(name), "reason": reason} for name in names]


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Stable insertion-ordered ``{value: count}`` tally over ``rows[key]``.

    Missing/blank values are skipped so the tally only reflects declared metadata.
    """
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value in (None, ""):
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _independent_domains(sources: list[dict[str, Any]]) -> int:
    """Count distinct registrable domains across credibility-eligible sources.

    Reuses the scorer's own helpers so the disclosed number matches the verdict:
    SIMULATED rows are excluded (``contributes_to_tier``) and the remaining URLs
    are reduced to registrable domains (``independence.registrable_domain``).
    Sources without a URL contribute no domain (cannot be an independent voice).
    """
    domains: set[str] = set()
    for src in sources:
        if not contributes_to_tier(src):
            continue
        url = src.get("url")
        if not url:
            continue
        domain = independence.registrable_domain(url)
        if domain:
            domains.add(domain)
    return len(domains)


def _build_source_stats(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Source-corpus statistics: total, mode/type distributions, independent domains."""
    return {
        "total": len(sources),
        "by_source_mode": _count_by(sources, "source_mode"),
        "by_source_type": _count_by(sources, "source_type"),
        "independent_domains": _independent_domains(sources),
    }


def _build_excluded(
    sources: list[dict[str, Any]],
    withheld: list[dict[str, Any]],
    credibility: dict[str, Any],
) -> dict[str, Any]:
    """The honest "未纳入项及原因" block.

    - ``withheld_count`` / ``issue_codes``: how many conclusions were withheld
      from the report and the de-duped set of issue codes that withheld them.
    - ``uncovered_fields``: schema fields with no admitted claim (coverage gaps;
      names only — never values, so no leak).
    - ``disclosures``: fixed honesty sentences (currently: the SIMULATED note,
      present only when a SIMULATED source exists).
    """
    codes: set[str] = set()
    for entry in withheld or []:
        for code in entry.get("issue_codes") or []:
            codes.add(str(code))

    disclosures: list[str] = []
    if any((src.get("source_mode") == "SIMULATED") for src in sources):
        disclosures.append(_SIMULATED_DISCLOSURE)

    return {
        "withheld_count": len(withheld or []),
        "issue_codes": sorted(codes),
        "uncovered_fields": list((credibility or {}).get("uncovered_fields") or []),
        "disclosures": disclosures,
    }


def _build_method() -> dict[str, Any]:
    """Fixed, honest methodology statements + the real QA rule-family count."""
    rule_count = len(IssueCode)
    return {
        "rule_count": rule_count,
        "statements": [
            s.format(fam=_CHECK_FAMILY_COUNT, n=rule_count) for s in _METHOD_STATEMENTS
        ],
    }


def build_scope_methodology(
    *,
    run: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    withheld: list[dict[str, Any]],
    credibility: dict[str, Any],
    trace_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the deterministic "范围与方法" report section from ledger data.

    Args:
        run: The run row (``get_run`` shape) — ``competitors`` list, ``category``,
            ``goal``, ``status``. ``None`` degrades to an empty directed scope.
        sources: All source rows for the run (``sources_for_run`` shape).
        withheld: The withheld-disclosure list
            (``synthesis.build_withheld_disclosure`` shape):
            ``[{"claim_id", "issue_codes": [...], "round"}, ...]``.
        credibility: The credibility panel (``qa.credibility.credibility_panel``
            shape) — used for ``proposed/admitted/withheld`` counts and the
            ``uncovered_fields`` coverage-gap names.
        trace_events: The run's trace events (``trace_events_for_run`` shape);
            their event types decide directed vs discovery mode. ``None`` ⇒ directed.

    Returns:
        A JSON-serializable dict with keys ``mode``, ``competitors``,
        ``source_stats``, ``excluded``, ``method``, and an ``admission`` summary.
    """
    mode = _detect_mode(trace_events)
    cred = credibility or {}
    return {
        "mode": mode,
        "competitors": _build_competitors(run, mode),
        "source_stats": _build_source_stats(sources),
        "admission": {
            "proposed_claims": int(cred.get("proposed_claims") or 0),
            "admitted_claims": int(cred.get("admitted_claims") or 0),
            "withheld_claims": int(cred.get("withheld_claims") or 0),
        },
        "excluded": _build_excluded(sources, withheld, cred),
        "method": _build_method(),
    }


def scope_methodology_for_run(db: Any, run_id: str) -> dict[str, Any]:
    """Assemble the scope/methodology section for a run from the DB (read-only).

    Reuses the SAME ledger-read paths the ``/withheld`` and ``/credibility``
    endpoints already use — ``synthesis.build_withheld_disclosure``,
    ``api_helpers.load_credibility_inputs`` + ``qa.credibility.credibility_panel``
    — so no business logic is duplicated. Then delegates to the pure
    :func:`build_scope_methodology` projector. The caller (``api.py``) does a
    single-line call.

    Args:
        db: The open :class:`~mingjing.db.Database` (source of truth).
        run_id: The run identifier (assumed to exist; the caller 404s first).

    Returns:
        The ``build_scope_methodology`` projection dict.
    """
    # Local imports keep this module free of an api_helpers/synthesis import
    # cycle at module load (api_helpers imports several heavy submodules).
    from .api_helpers import load_credibility_inputs
    from .qa.credibility import credibility_panel
    from .synthesis import build_withheld_disclosure

    return build_scope_methodology(
        run=db.get_run(run_id),
        sources=db.sources_for_run(run_id),
        withheld=build_withheld_disclosure(run_id, db),
        credibility=credibility_panel(**load_credibility_inputs(db, run_id)),
        trace_events=db.trace_events_for_run(run_id),
    )
