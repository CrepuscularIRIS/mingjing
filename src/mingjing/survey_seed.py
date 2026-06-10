"""Build survey/interview SOURCE ROWS from a fixture and return graph-seed entries.

Survey/interview evidence MUST enter as source rows whose ``raw_text`` holds the
(PII-scrubbed) answer text — analyze + QA read ``db.get_source(sid).raw_text``,
never ``evidence_chunks``. The executor seeds the returned entries into the graph's
initial additive ``sources`` state so analyze surfaces them per (competitor, field)
exactly like a web source. Deterministic, LLM-free; ids are stable (run-scoped, once).
"""

import time
from typing import Any, Protocol

from .survey import scrub_open_text


class _SourceStore(Protocol):
    def append_source(self, source: dict[str, Any]) -> None: ...


def _append_field_sources(
    db: _SourceStore, run_id: str, competitor: str, *,
    kind: str, ident: str, fields: dict[str, str | None],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for field, text in fields.items():
        scrubbed = scrub_open_text(text)[0]
        # Run-scoped id: `sources.id` is a PRIMARY KEY and `append_source` is a
        # plain INSERT, so the id MUST be unique across runs — a stable cross-run
        # id collides on the second run (UNIQUE constraint) and, under the
        # best-effort seeder, silently drops that run's survey evidence. The run
        # id (a uuid4 hex) makes it unique; the locator (url) stays the stable,
        # human-readable `survey:SV-1/<field>` for display/citation.
        # One source row per (competitor, field) claim: the contradiction/
        # corroboration counter dedupes by registrable domain, and every
        # `survey:*`/`interview:*` locator collapses to the literal domain
        # "survey"/"interview" — so a single claim must cite at most ONE seeded
        # source, else two survey fields would under-count as one domain.
        source_id = f"{run_id}-{kind}-{ident}-{field}"  # run-scoped, citable id
        locator = f"{kind}:{ident}/{field}"             # survey:SV-1/pricing_model
        db.append_source(
            {
                "id": source_id,
                "run_id": run_id,
                "url": locator,
                "title": f"{kind} {ident} ({field})",
                "source_type": kind,                    # "survey" | "interview"
                # SIMULATED: fixture-seeded demo data. Display-only for
                # credibility — scoring/corroboration/contradiction skip these
                # rows (scoring.contributes_to_tier); grounding still reads
                # raw_text so the lane demonstrates ingestion end-to-end. A real
                # survey import would use "INGESTED" and keep authoritative lift.
                "source_mode": "SIMULATED",
                "fetched_at": time.time(),
                "content_hash": None,
                "raw_text": scrubbed,                   # the GROUNDABLE content
                "meta_json": '{"simulated": true}',
            }
        )
        entries.append({"source_id": source_id, "field": field, "competitor": competitor})
    return entries


def survey_seed(
    db: _SourceStore, run_id: str, competitor: str, fixture: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Append per-(competitor, field) survey/interview source rows; return seed entries.

    Returns ``[]`` when ``fixture`` is None (honest absence — no synthesized evidence).
    """
    if not fixture:
        return []
    entries: list[dict[str, Any]] = []
    survey = fixture.get("survey")
    if survey:
        sid = survey.get("survey_id")
        if not sid:
            raise ValueError(f"survey fixture for {competitor!r} missing 'survey_id'")
        entries += _append_field_sources(
            db, run_id, competitor,
            kind="survey", ident=sid, fields=survey.get("fields", {}),
        )
    interview = fixture.get("interview")
    if interview:
        iid = interview.get("interview_id")
        if not iid:
            raise ValueError(f"interview fixture for {competitor!r} missing 'interview_id'")
        entries += _append_field_sources(
            db, run_id, competitor,
            kind="interview", ident=iid, fields=interview.get("fields", {}),
        )
    return entries
