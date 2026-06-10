"""Claim assembly + persistence helpers (extracted from graph_nodes, Task 15b).

These pure-ish helpers turn collected source rows + an analyst payload into an
append-only claim row, classify a source's authoritativeness, and rebuild the QA
claimset from DB rows. They have NO dependency on ``graph.py`` (they take ``db``
and plain dicts), which is why they live here rather than in ``graph_nodes`` —
keeping both that module and this one comfortably under the file-size convention
and free of the graph<->graph_nodes import cycle.
"""

import json
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from . import scoring
from .admiralty import grade as admiralty_grade
from .collector import independence
from .qa.rules import prune_unsupported_optional_leaves


def paragraph_locator(url: str, raw_text: str | None, snippet: str | None) -> str:
    """Return ``url#p:N`` where N is the 0-based paragraph index containing snippet.

    Paragraphs are split on blank-line boundaries (two or more consecutive
    newlines).  If that yields only a single block the text is further split on
    individual newlines so that dense plain-text pages (no blank lines) still get
    useful paragraph indices.

    Both the paragraph text and the snippet are normalised before comparison:
    all whitespace runs are collapsed to a single ASCII space and the result is
    lower-cased. The first paragraph whose normalised form *contains* the
    normalised snippet is returned.

    Falls back to the bare ``url`` when:

    * ``snippet`` is ``None`` or empty.
    * ``raw_text`` is ``None`` or empty.
    * The snippet cannot be located in any paragraph.
    * ``url`` is empty (the empty string is returned as-is).

    Args:
        url: The source page URL.
        raw_text: Full text of the fetched source page.
        snippet: The snippet to locate within the page.

    Returns:
        ``"url#p:N"`` on a successful match, otherwise ``url`` unchanged.
    """
    # raw_text/snippet are externally supplied and may be non-strings; a non-str
    # raw_text would crash re.split below. Treat non-str (or empty) as "no match".
    if not isinstance(snippet, str) or not snippet or not isinstance(raw_text, str) or not raw_text:
        return url
    # When url is empty, the augmented form "#p:N" would be meaningless — return as-is.
    if not url:
        return url

    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    norm_snippet = _norm(snippet)
    if not norm_snippet:
        return url

    # Primary split: blank-line boundaries (2+ newlines).
    paragraphs = re.split(r"\n\s*\n", raw_text)

    # If only one block, fall back to single-newline split.
    if len(paragraphs) <= 1:
        paragraphs = raw_text.splitlines()

    for i, para in enumerate(paragraphs):
        if norm_snippet in _norm(para):
            return f"{url}#p:{i}"

    return url


def to_json(value: Any) -> str:
    """Serialize ``value`` to a JSON string for a DB column."""
    return json.dumps(value, default=str, ensure_ascii=False)


# Advisory, NON-AUTHORITATIVE source-type buckets (display labels only). A domain
# here is classified review/forum INSTEAD of the generic 'web' — but review/forum
# carry the same Admiralty letter as 'web' and are NOT authoritative, so scoring,
# dedupe, and admission are unchanged (see infer_source_type's note).
_REVIEW_DOMAINS = frozenset(
    {
        "g2.com", "capterra.com", "getapp.com", "trustradius.com",
        "softwareadvice.com", "saashub.com", "alternativeto.net",
        "crozdesk.com", "slant.co", "producthunt.com",
    }
)
_FORUM_DOMAINS = frozenset(
    {
        "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
        "ycombinator.com", "v2ex.com", "zhihu.com",
    }
)


def infer_source_type(url: str, competitor: str) -> str:
    """Deterministically classify a source by URL host.

    Official ONLY when the competitor's name token equals a full dot-LABEL of the
    host (e.g. ``acme.example.com`` for "Acme") OR is the leading label of the
    registrable domain (e.g. ``acme.co.uk`` for "Acme"). A bare substring match is
    deliberately rejected so look-alike hosts like ``attackacme.com``,
    ``not-salesforce.com`` or ``acme-review.net`` are NOT promoted to official —
    that promotion flips the authoritative gate in :func:`scoring.strength` and
    could fabricate a "strong" tier from an adversarial domain.
    """
    if not url:
        return "web"
    host = (urlparse(url).hostname or "").lower()
    token = competitor.lower().split()[0] if competitor else ""
    if not token or not host:
        return "web"
    # Full dot-label match anywhere in the host (subdomains included).
    if token in host.split("."):
        return "official"
    # Leading label of the registrable domain (eTLD+1) equals the token.
    registrable = independence.registrable_domain(url)
    if registrable and registrable.split(".")[0] == token:
        return "official"
    # Advisory, NON-AUTHORITATIVE classification (review aggregators / forums).
    # IMPORTANT: this runs AFTER the official checks so a competitor's own site is
    # never demoted. review/forum are NOT in scoring.AUTHORITATIVE_TYPES and carry
    # the SAME Admiralty letter (D) as 'web' (admiralty._FALLBACK), so the strength
    # tier, dedupe authority weight, and claim admission are byte-identical to the
    # previous 'web' label — only the displayed source-type string gets richer.
    if registrable in _REVIEW_DOMAINS:
        return "review"
    labels = host.split(".")
    if registrable in _FORUM_DOMAINS or any(
        lbl in {"forum", "forums", "community"} for lbl in labels
    ):
        return "forum"
    return "web"


def supersede_target(
    db: Any, run_id: str, competitor: str | None, field_name: str
) -> tuple[str | None, int]:
    """Find the claim id + next version for a (competitor, field).

    A revision supersedes by INSERTING a higher ``version`` under the SAME claim
    id (so :meth:`Database.latest_claims_for_run` collapses the history to the
    newest row). Returns ``(existing_id_or_None, next_version)``: the existing
    highest-version claim's id is reused on a revision; ``None`` (caller assigns a
    fresh id) on the first version.
    """
    rows = [
        c
        for c in db.claims_for_run(run_id)
        if c.get("competitor") == competitor and c.get("schema_field") == field_name
    ]
    if not rows:
        return None, 1
    latest = max(rows, key=lambda c: c["version"])
    return latest["id"], latest["version"] + 1


def snippet_for(payload: dict[str, Any], source_row: dict[str, Any]) -> str:
    """Pick a snippet for a cited source — the analyst's candidate, verified by QA.

    The analyst proposes a per-source snippet (ideally a verbatim quote). We return
    that candidate UNCHANGED and let the QA HALLUCINATED_SNIPPET gate independently
    verify it is a real substring of ``raw_text`` (whitespace-normalized, no
    lowercasing). This is the only honest invariant: a verbatim quote passes; a
    paraphrase or fabrication is rejected and the claim is re-collected/revised.

    We deliberately do NOT try to "ground" a non-verbatim candidate to a best-match
    source span. Token-overlap grounding cannot tell a genuine reworded paraphrase
    (which can share as little as the competitor name, or ~20% of CJK bigrams) from
    an outright fabrication that shares the same — so any substitution either masks
    fabrications behind real source text (Codex G21a BLOCKING findings) or rejects
    genuine paraphrases. Keeping the snippet verbatim-or-reject avoids both.

    Two analyst shapes are accepted, in priority order:
    1. the legacy ``snippets`` map (``{source_id: snippet}``);
    2. the per-source ``snippet`` in the ``evidence`` list
       (``[{source_id, snippet, relevance}]``) the analyst prompt actually emits.

    Value grounding (VALUE_UNSUPPORTED) is a separate, independent gate and stays
    strict in every case.
    """
    # The analyst snippet is model-supplied and may be a non-string (list, number,
    # null). snippet_for is typed `-> str` and its result flows to paragraph_locator
    # → _norm → re.sub, which raises TypeError on a non-str (crashing build_claim,
    # which runs OUTSIDE the analyze try/except). So only accept a non-empty string;
    # anything else falls through to the statement / raw-slice fallback.
    raw = source_row.get("raw_text")
    if not isinstance(raw, str):
        raw = ""

    candidate: str | None = None
    snippets = payload.get("snippets")
    if isinstance(snippets, dict):
        c = snippets.get(source_row["id"])
        if isinstance(c, str) and c:
            candidate = c
    if candidate is None:
        evidence = payload.get("evidence")
        if isinstance(evidence, list):
            for ev in evidence:
                if isinstance(ev, dict) and ev.get("source_id") == source_row["id"]:
                    c = ev.get("snippet")
                    if isinstance(c, str) and c:
                        candidate = c
                    break

    # Return the analyst candidate as-is: verbatim → QA admits it; non-verbatim
    # (paraphrase/fabrication) → QA HALLUCINATED_SNIPPET rejects it. Never rewrite it.
    if candidate is not None:
        return candidate

    # No usable analyst candidate: keep the original safe fallback —
    # statement-if-substring, else a leading raw slice (also covers empty/non-str
    # raw, where the substring test is False and we return "").
    statement = payload.get("statement", "")
    if isinstance(statement, str) and statement and statement in raw:
        return statement
    return raw[:200]


def claimset_parts(
    db: Any, latest_claims: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build the QA ``claims`` list and ``sources`` map from DB rows.

    Evidence and value JSON columns are decoded back into the nested shape the
    verifier expects. The sources map carries ``raw_text``, ``source_type``,
    ``url`` AND ``source_mode`` — the mode is load-bearing: QA-side tier
    computation (``qa.rules._evidence_tuples`` / contradiction detection) skips
    SIMULATED rows via ``scoring.contributes_to_tier``, and dropping the mode
    here would silently let simulated survey rows count again.
    """
    claims: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for row in latest_claims:
        evidence = json.loads(row.get("evidence_json") or "[]")
        value = json.loads(row.get("value_json") or "{}")
        for ev in evidence:
            if ev.get("source_id"):
                source_ids.add(ev["source_id"])
        claims.append(
            {
                "id": row["id"],
                "competitor": row.get("competitor"),
                "schema_field": row["schema_field"],
                "claim_type": row["claim_type"],
                "statement": row["statement"],
                "value": value,
                "evidence": evidence,
                # Decode the lineage so the QA inference-integrity check sees it;
                # without this it is dropped before QA and every inference looks
                # lineage-less.
                "based_on": json.loads(row.get("based_on_json") or "[]"),
            }
        )

    sources: dict[str, dict[str, Any]] = {}
    for sid in source_ids:
        src = db.get_source(sid)
        if src is None:
            continue
        sources[sid] = {
            "raw_text": src.get("raw_text") or "",
            "source_type": src.get("source_type") or "web",
            "url": src.get("url") or "",
            "source_mode": src.get("source_mode"),
        }
    return claims, sources


def relevance(source_id: str, supporting_ids: set[str]) -> str:
    """A source is ``supports`` only when the analyst cited it; else ``unrelated``."""
    return "supports" if source_id in supporting_ids else "unrelated"


def build_claim(
    db: Any,
    run_id: str,
    task: dict[str, Any],
    src_rows: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one append-only claim row from the analyst payload + sources.

    The analyst's ``evidence_ref`` is the set of sources it can actually back the
    claim with (``supports``); other collected sources are cited as context
    (``unrelated``). Strength is the transparent :func:`scoring.strength` over the
    relevance-tagged tuples. The claim supersedes any prior version for the same
    (competitor, field) by reusing its id with an incremented version.

    Lifecycle: a claim is born ``status="draft"`` here; the terminal write node
    (``graph_nodes.make_write_node``) promotes a QA-accepted claim to
    ``status="pass"`` by appending a superseding version (append-only, never
    UPDATE). The report API surfaces only ``status="pass"`` claims.
    """
    field_name = task.get("field", "")
    competitor = task.get("competitor", "")
    supporting_ids = set(payload.get("evidence_ref", []))

    # SIMULATED (fixture-seeded) rows are display/grounding-only: they never
    # enter the tier tuples — a simulated survey domain must not provide the
    # second independent domain or the authoritative type that mints strong.
    tuples = [
        (
            r.get("source_type", "web"),
            relevance(r["id"], supporting_ids),
            independence.registrable_domain(r.get("url") or ""),
        )
        for r in src_rows
        if scoring.contributes_to_tier(r)
    ]
    strength = scoring.strength(sources=tuples, contradiction=False)

    # Per-source stance enum (supports/refutes/neutral) tagged by the analyst.
    # Read from the analyst payload's optional ``stances`` map; default to
    # "neutral" when a source is absent from the map so an UNCITED/untagged
    # source can never become a synthetic "supports" that fabricates a
    # source-vs-source contradiction against one real "refutes".
    stances = payload.get("stances")
    stances = stances if isinstance(stances, dict) else {}

    # Distinct supporting/refuting *domains* for THIS claim feed the SECONDARY
    # Admiralty credibility axis (corroboration vs contradiction). De-duping by
    # registrable domain prevents a single multi-page source from inflating
    # corroboration. The PRIMARY evidence_strength above is untouched.
    supporting_domains: set[str] = set()
    refuting_domains: set[str] = set()
    for r in src_rows:
        # Simulated rows must not improve the displayed corroboration digit
        # (secondary Admiralty axis) any more than the primary tier.
        if not scoring.contributes_to_tier(r):
            continue
        stance = stances.get(r["id"], "neutral")
        domain = independence.registrable_domain(r.get("url") or "")
        if not domain:
            continue
        if stance == "supports":
            supporting_domains.add(domain)
        elif stance == "refutes":
            refuting_domains.add(domain)
    evidence = []
    for r in src_rows:
        snippet = snippet_for(payload, r)
        # Item-relative credibility: a source's corroborators/contradictors are
        # the OTHER distinct domains (exclude this source's own domain so it
        # never counts as its own corroborator).
        own_domain = independence.registrable_domain(r.get("url") or "")
        n_corroborators = len(supporting_domains - {own_domain})
        n_contradictors = len(refuting_domains - {own_domain})
        evidence.append(
            {
                "source_id": r["id"],
                "snippet": snippet,
                "relevance": relevance(r["id"], supporting_ids),
                "stance": stances.get(r["id"], "neutral"),
                "locator": paragraph_locator(r.get("url") or "", r.get("raw_text"), snippet),
                # SECONDARY metadata only — band-only Admiralty grade (e.g. "B2").
                # schema_domain=None -> active schema domain's source_weights (M5).
                "admiralty": admiralty_grade(
                    r.get("source_type", "web"),
                    independent_corroborators=n_corroborators,
                    contradictors=n_contradictors,
                    schema_domain=None,
                ),
            }
        )
    # Withhold ungrounded OPTIONAL value leaves before persisting: the QA gate
    # only hard-checks REQUIRED sub-fields, so an LLM-fabricated value under an
    # OPTIONAL key would otherwise reach status=pass + the published report. We
    # drop such leaves deterministically (withhold, not reject — honest paraphrases
    # aren't futilely lost). The grounding text is the raw text of THIS claim's
    # evidence sources — the SAME haystack the gate's _check_value_unsupported
    # builds (keyed off evidence source_ids), so the prune and the gate can never
    # diverge on what counts as grounded, even if evidence is later filtered.
    # Coerce non-string raw_text to "" so the join below (and any downstream str
    # op) can never raise on an LLM/ingest/DB anomaly.
    _raw_by_id = {
        r["id"]: (rt if isinstance(rt := r.get("raw_text"), str) else "") for r in src_rows
    }
    cited_source_text = " ".join(
        _raw_by_id.get(ev["source_id"], "") for ev in evidence
    )
    value = prune_unsupported_optional_leaves(
        payload.get("value", {}), field_name, cited_source_text
    )

    existing_id, version = supersede_target(db, run_id, competitor, field_name)
    return {
        "id": existing_id or str(uuid.uuid4()),
        "run_id": run_id,
        "competitor": competitor,
        "schema_field": field_name,
        # `or` (not `.get` default): an explicit JSON null from the LLM must fall back to "fact", not None (NOT NULL column).
        "claim_type": payload.get("claim_type") or "fact",
        "statement": payload.get("statement", ""),
        "value": value,
        "value_json": to_json(value),
        "evidence": evidence,
        "evidence_json": to_json(evidence),
        # Carry the analyst's lineage (claim ids this inference rests on) so it is
        # persisted instead of defaulting to '[]' and lost before QA.
        "based_on": payload.get("based_on") or [],
        "based_on_json": to_json(payload.get("based_on") or []),
        "evidence_strength": strength,
        "status": "draft",
        "version": version,
        "produced_by": "analyst",
    }
