# mingjing/tests/test_demo_feedback_loop.py
"""Integration: the curated demo drives a genuinely-real weak->strong improvement.

The curated collect_fn stages a thin round-0 source and a strong round-1 source.
The collect node's cap grows each revision round (``source_cap = 1 + round``), so
round 0 fetches only the thin source and a later round fetches the authoritative
one too. The staged analyst can only *cite* (back) a source whose text actually
supports the claim, so in round 0 it returns an empty ``evidence_ref`` -- the REAL
scorer then scores the claim ``weak`` (zero supporting domains) and QA rejects with
``WEAK_EVIDENCE``, which the REAL router dispatches to the collector for a re-fetch.
In the next round the authoritative source is present, the analyst cites it, the
REAL scorer promotes the claim and QA passes. Nothing about the verdict is
hardcoded -- the improvement is produced entirely by the real collect/analyze/QA/
route/scoring/write logic; the staged analyst only mirrors what evidence it sees.
"""

import tempfile

import pytest

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.demo.corpus import make_demo_collect_fn
from mingjing.graph_nodes import build_query
from mingjing.runner import make_run_executor


def _settings(db_path: str, cache_path: str) -> Settings:
    return Settings(
        minimax_base_url="http://unused",
        minimax_api_key="unused",
        minimax_model="staged",
        mode="cache_first",
        rate_limiting_enabled=True,
        db_path=db_path,
        cache_db_path=cache_path,
        per_field_source_cap=3,
        min_source_chars=0,
        fetch_timeout_s=8.0,
        revise_round_cap=2,
        budget_calls_max=40,
        llm_max_tokens=8000,
        llm_timeout_s=90.0,
        depth="quick",
        deep_collect_workers=8,
        fetch_budget_per_run=60,
        firecrawl_api_key="",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
    )


# The required sub-field value the staged analyst reports for pricing_model. It
# is copied verbatim into the round-1 source text so the REAL VALUE_UNSUPPORTED
# substring check (it scans ALL cited source raw text) passes once that source
# is fetched.
_TIER_FACT = "Acme Pro tier costs 10 USD per month"


def _corpus():
    key = build_query("Acme", "pricing_model")
    return {
        key: {
            "competitor": "Acme",
            "field": "pricing_model",
            "sources": [
                # round 0 (source_cap=1): thin blurb with NO pricing fact. The
                # analyst cannot back a tier claim from it, so it cites nothing
                # -> the REAL scorer scores the claim weak (zero supporting
                # domains) -> WEAK_EVIDENCE -> router dispatches to collector.
                {"url": "https://thin.example/a", "title": "blurb", "source_type": "web",
                 "text": "Acme is a productivity tool people like."},
                # round 1 (source_cap=2): authoritative, distinct domain, carries
                # the verbatim required fact. Now the analyst can cite it AND the
                # thin source for two distinct supporting domains (one official)
                # -> the REAL scorer promotes the claim to strong -> QA passes.
                {"url": "https://acme.example/pricing", "title": "Pricing", "source_type": "official",
                 "text": f"{_TIER_FACT}, billed annually. Acme is a productivity tool people like."},
            ],
        }
    }


def _parse_evidence_blocks(evidence_text: str) -> dict[str, str]:
    """Split graph_nodes' labeled evidence into ``{source_id: block_text}``.

    The collect/analyze node formats evidence as blocks joined by a blank line,
    each prefixed by a ``[source_id: <id>]`` header (see graph_nodes.py ~L214):

        [source_id: abc]\n<raw text of abc>\n\n[source_id: def]\n<raw text of def>

    Parsing per-source lets the staged analyst cite ONLY the sources whose own
    block actually carries the fact -- an honest citation, not a blanket one.
    """
    blocks: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []
    for line in evidence_text.splitlines():
        if line.startswith("[source_id: ") and line.endswith("]"):
            if current_id is not None:
                blocks[current_id] = "\n".join(current_lines)
            current_id = line[len("[source_id: ") : -1].strip()
            current_lines = []
        elif current_id is not None:
            current_lines.append(line)
    if current_id is not None:
        blocks[current_id] = "\n".join(current_lines)
    return blocks


def _staged_analyze_fn(db, run_id, *, field, competitor, evidence_text, source_ids, settings):
    """Deterministic stand-in for the analyst (cites ONLY sources it can back).

    It parses the labeled evidence into per-source blocks and cites ONLY the
    source ids whose OWN block contains the verbatim tier fact -- never the thin
    source. So round 0 (thin source only, no tier fact) cites NOTHING -> the REAL
    scorer scores the claim weak (zero supporting domains) -> QA rejects with
    WEAK_EVIDENCE -> the REAL router re-fetches via the collector (WEAK_EVIDENCE
    routes to the collector, growing source_cap = 1 + round). A later round
    (authoritative source fetched) cites just that one source whose block carries
    the verbatim span, and the REAL scorer promotes the claim. The verdict is
    decided by the real rules, not here.

    The 'tiers' sub-field is always reported (so there is never a SCHEMA_GAP);
    this keeps the loop driven purely by the VALUE_UNSUPPORTED citation path
    rather than mixing in a second evidence-gap code. (Both SCHEMA_GAP and
    VALUE_UNSUPPORTED now route to the collector, which grows the source cap.)
    Honesty lives in the CITATION: when no source backs the value the analyst
    cites NOTHING, so the REAL scorer marks it weak and the REAL VALUE_UNSUPPORTED
    check has no cited haystack to validate against. Only once a citing source
    exists is its verbatim span the actual backing for the value.
    """
    blocks = _parse_evidence_blocks(evidence_text)
    # Honest citation: only sources whose own block carries the verbatim fact.
    citing = sorted(
        sid for sid in (source_ids or []) if _TIER_FACT in blocks.get(sid, "")
    )
    # The value is the analyst's reported sub-field (a verbatim span). In round 0
    # nothing cites it -> WEAK_EVIDENCE -> collector re-fetch. In a later round
    # only a source that actually carries the verbatim span is cited, so the REAL
    # VALUE_UNSUPPORTED check stays clean and the scorer can promote the claim.
    return {
        "statement": _TIER_FACT,
        "claim_type": "fact",
        "value": {"tiers": _TIER_FACT},
        "evidence_ref": citing,
    }


@pytest.mark.slow
def test_demo_loop_moves_field_from_fail_to_pass():
    with tempfile.TemporaryDirectory() as d:
        db_path = f"{d}/mj.db"
        cache_path = f"{d}/cache.db"
        db = Database(db_path)
        db.init_schema()
        settings = _settings(db_path, cache_path)

        run_id = db.create_run(category="AI tool", competitors=["Acme"], goal="pricing")

        executor = make_run_executor(
            lambda: db,
            settings=settings,
            collect_fn=make_demo_collect_fn(_corpus()),
            analyze_fn=_staged_analyze_fn,
            prewarm=False,
        )
        executor(run_id)

        # FIX 2 — prove the IMPROVEMENT on the pricing claim itself, not partial
        # promotion. Walk ALL versions of the pricing_model claim (same id) and
        # assert the evidence genuinely strengthened weak -> {moderate,strong}
        # through the loop, ending status="pass".
        all_claims = db.claims_for_run(run_id)
        pricing_versions = [c for c in all_claims if c["schema_field"] == "pricing_model"]
        assert pricing_versions, "no pricing_model claim was produced"
        # A single logical claim id, tracked across versions.
        pricing_id = pricing_versions[0]["id"]
        assert all(c["id"] == pricing_id for c in pricing_versions), (
            "expected one logical pricing_model claim tracked across versions"
        )
        ordered = sorted(pricing_versions, key=lambda c: c["version"])
        assert len(ordered) >= 2, (
            "pricing_model has only one version — the loop never revised it"
        )
        earliest, final = ordered[0], ordered[-1]
        assert earliest["evidence_strength"] == "weak", (
            f"earliest pricing version should be weak, got {earliest['evidence_strength']!r}"
        )
        assert final["evidence_strength"] in {"moderate", "strong"}, (
            "final pricing version did not strengthen past weak: "
            f"{final['evidence_strength']!r}"
        )
        assert final["status"] == "pass", (
            f"final pricing version did not reach pass: {final['status']!r}"
        )

        # FIX 3 — tie the rejection to round 0 + WEAK_EVIDENCE + the pricing claim.
        # qa_fail payloads carry keys: claim_id, reason, code, round (trace_events
        # emit_qa_verdict). The WEAK_EVIDENCE issue sets code="WEAK_EVIDENCE" and
        # claim_id=<the claim's id>.
        import json

        events = db.trace_events_for_run(run_id)
        weak_round0_fails = []
        for e in events:
            if e.get("event_type") != "qa_fail":
                continue
            payload = json.loads(e["payload_json"])
            if (
                payload.get("code") == "WEAK_EVIDENCE"
                and payload.get("round") == 0
                and payload.get("claim_id") == pricing_id
            ):
                weak_round0_fails.append(payload)
        assert weak_round0_fails, (
            "no round-0 WEAK_EVIDENCE qa_fail for the pricing claim — "
            "the real loop did not reject thin round-0 evidence"
        )
