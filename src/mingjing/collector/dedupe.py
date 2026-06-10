"""Quality-biased deduplication and ranking for raw search previews (PURE).

After parallel search returns many preview dicts, ``dedupe_and_rank`` selects
the best top-K biased toward AUTHORITATIVE + INDEPENDENT sources, dropping spam
clones.  Deterministic, no I/O, no LLM.

Algorithm overview
------------------
1. Exact-URL dedup: collapse same normalised URL, accumulate ``agreement``
   (count of distinct engines that surfaced it).
2. Authority weight: map ``infer_source_type`` letter → numeric score.
3. Independence bonus: first URL per registrable domain earns +1.0; later
   URLs from the same domain earn 0 (rewards diversity).
4. Spam penalty: detect typo-squat hosts via edit-distance on the registrable-
   domain label; apply a large penalty so spam ranks below genuine sources.
5. Final score: ``quality = authority_weight + independence_bonus + agreement
   - spam_penalty``.
6. Per-domain cap: keep at most ``per_domain_cap`` URLs per registrable domain.
7. Stable sort by quality DESC; return top-K with ``quality`` and ``agreement``
   fields attached for observability.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..claim_builder import infer_source_type
from .independence import registrable_domain

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mirror of default.json ``source_weights`` (Admiralty letter grades).
DEFAULT_SOURCE_WEIGHTS: dict[str, str] = {
    "official": "B",
    "news": "C",
    "review": "D",
    "survey": "D",
    "forum": "D",
    "web": "D",
    "blog": "E",
}

# Admiralty letter → numeric authority weight.
# A and F are reserved extension grades not used by DEFAULT_SOURCE_WEIGHTS today.
_LETTER_TO_WEIGHT: dict[str, float] = {
    "A": 5.0,
    "B": 4.0,
    "C": 3.0,
    "D": 2.0,
    "E": 1.0,
    "F": 0.5,
}

_INDEPENDENCE_BONUS: float = 1.0
_SPAM_PENALTY: float = 5.0
# Max relevance bonus (scaled by the fraction of query tokens a candidate
# matches). Sized to dominate authority+independence so an on-topic D-grade page
# outranks an authoritative-but-irrelevant one (e.g. a Notion forum post beats a
# Federal-Reserve PDF for the query "Notion pricing").
_RELEVANCE_BONUS: float = 6.0
# Tokens too generic to signal topical relevance (drop from the query tokens).
_RELEVANCE_STOPWORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "of", "for", "and", "or", "vs", "to", "in", "on", "model", "plan"}
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    """Normalise a URL for exact-dedup comparison.

    Rules:
    * Lowercase scheme and host.
    * Strip trailing slash from path.
    * Drop fragment (``#…``).
    * Preserve query string (different query = different resource).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url.lower()
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")
    query = parsed.query
    norm = f"{scheme}://{host}{path}"
    if query:
        norm = f"{norm}?{query}"
    return norm


def _edit_distance(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two short strings.

    Uses the classic DP approach; acceptable for short domain labels.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    # Keep two rows only.
    prev = list(range(lb + 1))
    curr = [0] * (lb + 1)
    for i in range(1, la + 1):
        curr[0] = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, [0] * (lb + 1)
    return prev[lb]


def _domain_label(reg_domain: str) -> str:
    """Return the registrable-domain label (everything before the public suffix).

    Example: ``feishu.cn`` → ``feishu``;  ``example.co.uk`` → ``example``.
    The label is the *first* part of the registrable domain.
    """
    if not reg_domain:
        return ""
    return reg_domain.split(".")[0]


def _query_tokens(query: str) -> list[str]:
    """Significant lowercase tokens from a query (ASCII words ≥2 chars + CJK runs).

    Drops generic stopwords so a candidate must match a CONTENTFUL term (the
    entity / topic) to earn relevance, not just filler like "for"/"model".
    """
    raw = re.findall(r"[a-z0-9]{2,}|[一-鿿]+", (query or "").lower())
    return [t for t in raw if t not in _RELEVANCE_STOPWORDS]


def _relevance_bonus(preview: dict[str, Any], tokens: list[str]) -> float:
    """Relevance score for a preview: fraction of distinct query tokens that
    appear in its title + snippet + url, scaled by ``_RELEVANCE_BONUS``.

    Returns 0.0 when no query tokens are given (preserves legacy ranking).
    """
    if not tokens:
        return 0.0
    hay = " ".join(
        (preview.get(k, "") or "") for k in ("title", "snippet", "url")
    ).lower()
    uniq = set(tokens)
    matched = sum(1 for t in uniq if t in hay)
    return _RELEVANCE_BONUS * (matched / len(uniq))


def _authority_weight(
    url: str,
    competitor: str,
    source_weights: dict[str, str],
) -> float:
    """Return numeric authority weight for a URL.

    Unknown source_type → weight 1.0 (spec: B→4, C→3, D→2, E→1, unknown→1).
    """
    source_type = infer_source_type(url, competitor)
    letter = source_weights.get(source_type)
    if letter is None:
        return 1.0
    return _LETTER_TO_WEIGHT.get(letter, 1.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dedupe_and_rank(
    previews: list[dict[str, Any]],
    *,
    top_k: int,
    per_domain_cap: int,
    competitor: str,
    source_weights: dict[str, str] | None = None,
    query: str = "",
) -> list[dict[str, Any]]:
    """Deduplicate and quality-rank search previews.

    Args:
        previews: Raw preview dicts each containing ``url``, ``title``,
            ``snippet``, and ``engine`` keys.
        top_k: Maximum number of results to return.
        per_domain_cap: Maximum URLs to keep per registrable domain.
        competitor: Competitor name token (forwarded to ``infer_source_type``).
        source_weights: Optional override for the Admiralty letter map.
            Defaults to ``DEFAULT_SOURCE_WEIGHTS``.

    Returns:
        At most ``top_k`` preview dicts sorted by quality DESC (stable).
        Each returned dict carries two extra observability fields:
        * ``quality``: the computed float score.
        * ``agreement``: count of distinct engines that surfaced this URL.
    """
    sw = source_weights if source_weights is not None else DEFAULT_SOURCE_WEIGHTS
    rel_tokens = _query_tokens(query)

    # ------------------------------------------------------------------
    # Step 1: Exact-URL dedup — collapse same normalised URL.
    # We preserve the *first* occurrence's metadata; accumulate engines.
    # ------------------------------------------------------------------
    seen_norm: dict[str, dict[str, Any]] = {}   # norm_url → deduped dict
    engine_sets: dict[str, set[str]] = {}        # norm_url → distinct engines
    order: list[str] = []                        # preserves first-seen order

    for preview in previews:
        raw_url: str = preview.get("url", "")
        norm = _normalize_url(raw_url)
        if norm not in seen_norm:
            seen_norm[norm] = dict(preview)
            engine_sets[norm] = set()
            order.append(norm)
        engine = preview.get("engine", "")
        if engine:
            engine_sets[norm].add(engine)

    # ------------------------------------------------------------------
    # Step 2 & 3: Compute authority weight + independence bonus.
    # Process in first-seen order so the independence bonus is assigned
    # deterministically to the first URL per registrable domain.
    # ------------------------------------------------------------------
    seen_reg_domains: set[str] = set()  # registrable domains already encountered

    # (norm_url, quality_before_spam, agreement, authority_weight)
    scored: list[tuple[str, float, int, float]] = []

    for norm in order:
        preview = seen_norm[norm]
        url = preview.get("url", "")

        agreement = len(engine_sets[norm])
        auth = _authority_weight(url, competitor, sw)

        reg_dom = registrable_domain(url)
        if reg_dom not in seen_reg_domains:
            # Independence bonus: first-SEEN per domain; a later per-domain-cap
            # drop could orphan the bonus — acceptable for current workloads.
            independence = _INDEPENDENCE_BONUS
            seen_reg_domains.add(reg_dom)
        else:
            independence = 0.0

        relevance = _relevance_bonus(preview, rel_tokens)
        quality_pre_spam = auth + independence + agreement + relevance
        scored.append((norm, quality_pre_spam, agreement, auth))

    # ------------------------------------------------------------------
    # Step 4: Spam penalty — detect typo-squat hosts.
    # A candidate is penalised if its domain label is within edit-distance ≤ 2
    # of a SHORTER label whose URL has a strictly higher PURE authority_weight
    # (spec: "higher-authority url").  We compare authority_weight only — not
    # the composite quality — so a high-agreement typosquat cannot dodge the
    # penalty by accumulating cross-engine votes.
    # ------------------------------------------------------------------
    # Collect (label, authority_weight) for all entries.
    label_info: list[tuple[str, float]] = []  # (label, authority_weight)
    for norm, _qps, _agreement, auth in scored:
        url = seen_norm[norm].get("url", "")
        reg_dom = registrable_domain(url)
        label = _domain_label(reg_dom)
        label_info.append((label, auth))

    final_scored: list[tuple[str, float, int]] = []
    for _idx, (norm, quality_pre_spam, agreement, candidate_auth) in enumerate(scored):
        url = seen_norm[norm].get("url", "")
        reg_dom = registrable_domain(url)
        candidate_label = _domain_label(reg_dom)
        spam_penalty = 0.0

        if candidate_label:
            for other_label, other_auth in label_info:
                if other_label == candidate_label:
                    continue
                # Typo-squats are typically LONGER (padded/inserted chars).
                if len(candidate_label) <= len(other_label):
                    continue
                if _edit_distance(candidate_label, other_label) <= 2:
                    # Fire the penalty when the shorter-label URL has strictly
                    # higher PURE authority_weight (independent of agreement).
                    if other_auth > candidate_auth:
                        spam_penalty = _SPAM_PENALTY
                        break

        final_quality = quality_pre_spam - spam_penalty
        final_scored.append((norm, final_quality, agreement))

    # ------------------------------------------------------------------
    # Step 6: Per-domain cap — keep at most per_domain_cap per domain,
    # highest quality first.
    # Sort first by quality DESC to determine which survive the cap.
    # ------------------------------------------------------------------
    # Stable sort by quality DESC (preserves first-seen order on ties).
    indexed = list(enumerate(final_scored))
    indexed.sort(key=lambda x: (-x[1][1], x[0]))  # sort by (-quality, original_index)

    domain_counts: dict[str, int] = {}
    kept_indices: list[int] = []
    for orig_idx, (norm, _quality, _agreement) in indexed:
        url = seen_norm[norm].get("url", "")
        reg_dom = registrable_domain(url)
        count = domain_counts.get(reg_dom, 0)
        if count < per_domain_cap:
            domain_counts[reg_dom] = count + 1
            kept_indices.append(orig_idx)

    # ------------------------------------------------------------------
    # Step 7: Re-sort kept entries by quality DESC (stable → ties keep
    # first-seen / first-appearance order from original input).
    # ------------------------------------------------------------------
    kept_indices.sort(key=lambda i: (-final_scored[i][1], i))

    # Build result list (top_k).
    results: list[dict[str, Any]] = []
    for i in kept_indices[:top_k]:
        norm, quality, agreement = final_scored[i]
        out = dict(seen_norm[norm])
        out["quality"] = quality
        out["agreement"] = agreement
        results.append(out)

    return results
