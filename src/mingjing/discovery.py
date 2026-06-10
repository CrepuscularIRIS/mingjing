"""Bounded competitor discovery — the Discovery-Mode pre-step.

When a run is created with a **category** but **no competitors**, the runner asks
this module: *given this category (and optional market scope / seeds), which
products should we analyze?* It runs a single bounded search pass — a handful of
deterministic queries, a small top-k each — extracts candidate product names from
the result previews, ranks them by how many independent domains mention them
(with an official-page boost), and returns the top ``max_competitors``.

This is deliberately **NOT** a recursive DeepResearch:
  * ``build_discovery_queries`` caps the query count (default 4, clamp 1..6),
  * the pure extraction/ranking functions never touch the network,
  * ``discover_competitors`` calls the injected ``search_fn`` once per query and
    never follows links or recurses.

Everything downstream (collection, the QA gate, evidence/provenance, scoring) is
untouched — discovery only decides *which* competitors enter the existing loop.

The module's core (``build_discovery_queries``, ``extract_candidates``,
``rank_candidates``) is PURE and dependency-free so it is fully unit-testable;
``discover_competitors`` takes the search callable as a parameter so tests inject
a deterministic fake and production passes a thin wrapper over
:func:`mingjing.collector.search.search`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .collector.independence import registrable_domain

_log = logging.getLogger(__name__)

# Search previews arrive as ``{"url", "title", "snippet"}`` dicts (the contract
# of :func:`mingjing.collector.search.search`).
Preview = dict[str, Any]
SearchFn = Callable[[str], list[Preview]]

# Domains that are aggregators / press / social / SEO — they MENTION products but
# are not themselves the product, so they never become a candidate. Their previews
# still contribute to a product's mention count.
_NOISE_DOMAINS: frozenset[str] = frozenset(
    {
        # review aggregators / directories
        "g2.com", "capterra.com", "getapp.com", "trustradius.com",
        "softwareadvice.com", "producthunt.com", "saashub.com", "slant.co",
        "alternativeto.net", "crozdesk.com", "sourceforge.net",
        # social / Q&A / UGC
        "reddit.com", "quora.com", "medium.com", "youtube.com", "twitter.com",
        "x.com", "linkedin.com", "facebook.com", "instagram.com", "tiktok.com",
        "github.com", "stackoverflow.com", "substack.com", "notion.site",
        # encyclopedias / search engines
        "wikipedia.org", "google.com", "bing.com", "duckduckgo.com",
        # press / analyst
        "techcrunch.com", "theverge.com", "forbes.com", "gartner.com",
        "businessinsider.com", "wired.com", "cnbc.com", "venturebeat.com",
        # CN aggregators / press / UGC
        "zhihu.com", "csdn.net", "jianshu.com", "36kr.com", "sspai.com",
        "baidu.com", "cnblogs.com", "juejin.cn", "woshipm.com", "ithome.com",
        "163.com", "qq.com", "sina.com.cn", "sohu.com", "toutiao.com",
    }
)

# Generic words that must never be treated as a brand when they head a title.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "best", "top", "the", "a", "an", "vs", "and", "or", "for", "of", "to",
        "review", "reviews", "comparison", "compare", "alternatives",
        "alternative", "tools", "tool", "software", "platform", "platforms",
        "app", "apps", "product", "products", "list", "guide", "guides",
        "free", "online", "ai", "best-of", "ranked", "rankings", "ranking",
        "解决方案", "竞品", "对比", "推荐", "排行", "排行榜", "盘点", "有哪些",
        "哪些", "推荐的", "最好的", "免费", "工具", "平台", "产品", "软件",
    }
)

# Title separators — we keep the head segment as the likely product name.
_TITLE_SPLIT = re.compile(r"\s*[|\-–—·:：丨•]\s*|\s+[-–—]\s+")
_SLUG_RE = re.compile(r"[^a-z0-9一-鿿]+")

_SCOPE_WORDS: dict[str, str] = {"china": "中国", "cn": "中国", "global": "全球"}


@dataclass
class Candidate:
    """A discovered competitor candidate with its supporting evidence signals."""

    name: str
    domains: set[str] = field(default_factory=set)
    source_count: int = 0
    has_official: bool = False


@dataclass(frozen=True)
class DiscoveryResult:
    """The outcome of one bounded discovery pass."""

    selected: list[str]
    candidates: list[dict[str, Any]]
    queries: list[str]

    def as_payload(self) -> dict[str, Any]:
        """Trace-/UI-friendly dict (used for the ``competitors_discovered`` event)."""
        return {
            "selected": list(self.selected),
            "candidates": list(self.candidates),
            "queries": list(self.queries),
        }


def _slug(text: str) -> str:
    """Lowercase, strip non-alphanumeric (keep CJK) — a stable comparison key."""
    return _SLUG_RE.sub("", text.lower()).strip()


def _scope_label(market_scope: str | None) -> str:
    """Map a scope token to a human query fragment (``china`` -> 中国); passthrough else."""
    if not market_scope:
        return ""
    return _SCOPE_WORDS.get(market_scope.strip().lower(), market_scope.strip())


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def build_discovery_queries(
    category: str,
    *,
    market_scope: str | None = None,
    goal: str | None = None,
    max_queries: int = 4,
) -> list[str]:
    """Build a small, deterministic set of discovery search queries.

    PURE. Produces scope-aware query variants for *category*, deduped and clamped
    to ``max_queries`` (clamp 1..6). ``goal`` is appended to one variant when
    present so a focused run nudges discovery toward the right segment.

    Args:
        category: The product category (e.g. "通用 AI Agent", "CRM").
        market_scope: Optional scope token; ``china``/``cn`` -> 中国,
            ``global`` -> 全球, otherwise the raw string is used verbatim.
        goal: Optional research goal; appended to one query variant when set.
        max_queries: Upper bound on returned queries (clamped to 1..6).

    Returns:
        An ordered, deduplicated list of query strings (length <= max_queries).
    """
    cat = category.strip()
    if not cat:
        return []
    scope = _scope_label(market_scope)
    prefix = f"{scope} " if scope else ""
    variants = [
        f"{prefix}{cat} 竞品有哪些",
        f"top {cat} products {scope}".strip(),
        f"best {cat} tools 2026 {scope}".strip(),
        f"{cat} alternatives comparison",
    ]
    if goal and goal.strip():
        variants.append(f"{prefix}{cat} {goal.strip()}")
    # Dedup preserving order, then clamp.
    seen: set[str] = set()
    out: list[str] = []
    for q in variants:
        norm = re.sub(r"\s+", " ", q).strip()
        key = norm.lower()
        if norm and key not in seen:
            seen.add(key)
            out.append(norm)
    return out[: _clamp(max_queries, 1, 6)]


def _title_head(title: str) -> str:
    """Return the leading segment of a title (before the first separator)."""
    if not title:
        return ""
    head = _TITLE_SPLIT.split(title.strip(), maxsplit=1)[0]
    return head.strip()


def _brand_from_domain(domain: str) -> str:
    """Derive a brand name from a registrable domain (``linear.app`` -> ``Linear``)."""
    if not domain:
        return ""
    root = domain.split(".")[0]
    if not root:
        return ""
    # ASCII roots read better title-cased; leave CJK/other untouched.
    return root.capitalize() if root.isascii() else root


def _is_stop(name: str, *, category: str) -> bool:
    """True when *name* is a generic/category word that must not be a candidate."""
    low = name.lower().strip()
    if not low or low in _STOP_WORDS:
        return True
    cat_tokens = {t for t in re.split(r"\s+", category.lower()) if t}
    return low in cat_tokens


def extract_candidates(previews: list[Preview], *, category: str) -> list[Candidate]:
    """Extract ranked-ready candidate products from search-result previews.

    PURE. Two candidate signals are merged and scored:

    * **Domain brand** — each non-noise registrable domain yields a candidate
      (its root label as the brand); this also flags an official page.
    * **Title head** — the leading segment of each title (before a separator),
      when it is short and not a generic/category word.

    Each candidate's ``source_count`` is the number of distinct registrable
    domains whose preview *mentions* the candidate (case-insensitive substring in
    title/snippet/url, or the domain itself for a domain-brand). ``has_official``
    is set when some preview's domain root slug matches the candidate slug.

    Args:
        previews: ``{"url", "title", "snippet"}`` dicts (empty/garbled tolerated).
        category: The category, used to filter category words out of candidates.

    Returns:
        A list of :class:`Candidate` (unranked; pass to :func:`rank_candidates`).
    """
    # Index previews once: (registrable_domain, slugged-haystack, ascii-token-set).
    # The token set lets ASCII brand mentions match on word boundaries (so a short
    # slug like "go" is NOT credited from inside "mango"); the slugged haystack
    # serves multi-word ASCII brands and CJK (which have no word boundaries).
    indexed: list[tuple[str, str, set[str]]] = []
    for p in previews:
        if not isinstance(p, dict):
            continue
        dom = registrable_domain(p.get("url", ""))
        if not dom or "." not in dom:  # a real domain has a dot ("http" is garbage)
            continue
        hay = " ".join(str(p.get(k, "")) for k in ("title", "snippet", "url")).lower()
        indexed.append((dom, _slug(hay), set(re.findall(r"[a-z0-9]+", hay))))

    # Seed candidate names from domain brands + title heads.
    names_by_slug: dict[str, str] = {}

    def _consider(name: str) -> None:
        # Collapse whitespace so a multi-line title head can't carry newlines
        # into the persisted name / prompt (defense-in-depth with text_safety).
        name = re.sub(r"\s+", " ", name or "").strip()
        if not name or len(name) > 40 or _is_stop(name, category=category):
            return
        slug = _slug(name)
        if not slug or len(slug) < 2:
            return
        # Keep the first (usually cleaner) display form for a given slug.
        names_by_slug.setdefault(slug, name)

    for p in previews:
        if not isinstance(p, dict):
            continue
        dom = registrable_domain(p.get("url", ""))
        # Only a NON-aggregator page is a candidate source: its domain brand and
        # its title head are the product itself. Aggregator/press pages (g2,
        # zhihu, …) list products — their domain brand and listicle title must
        # NOT become candidates (they still credit a product via the mention
        # scan below).
        if not dom or "." not in dom or dom in _NOISE_DOMAINS:
            continue
        _consider(_brand_from_domain(dom))
        head = _title_head(str(p.get("title", "")))
        # Only short title heads look like product names.
        if head and len(re.split(r"\s+", head)) <= 4:
            _consider(head)

    # Fold a CJK-prefixed brand variant into its ASCII sibling so the same product
    # is not double-counted: "扣子 Coze" (slug 扣子coze) -> "Coze" (slug coze).
    ascii_slugs = {s for s in names_by_slug if s.isascii()}
    for slug in list(names_by_slug):
        if slug.isascii():
            continue
        ascii_part = re.sub(r"[^a-z0-9]", "", slug)  # strip CJK, keep latin/digits
        if len(ascii_part) >= 2 and ascii_part in ascii_slugs:
            del names_by_slug[slug]

    candidates: list[Candidate] = []
    for slug, display in names_by_slug.items():
        domains: set[str] = set()
        has_official = False
        is_ascii = slug.isascii()
        for dom, hay_slug, tokens in indexed:
            dom_slug = _slug(dom.split(".")[0])
            if dom_slug == slug:
                has_official = True
                domains.add(dom)
            elif is_ascii:
                # Exact token match avoids short-slug substring false positives
                # ("go" in "mango"); long slugs also allow a multi-word substring.
                if slug in tokens or (len(slug) >= 6 and slug in hay_slug):
                    domains.add(dom)
            elif slug in hay_slug:
                domains.add(dom)
        if not domains:
            continue
        candidates.append(
            Candidate(
                name=display,
                domains=domains,
                source_count=len(domains),
                has_official=has_official,
            )
        )
    return candidates


def rank_candidates(
    candidates: list[Candidate],
    *,
    max_competitors: int,
    seed_competitors: tuple[str, ...] = (),
) -> list[str]:
    """Rank candidates and return the top display names (seeds always first).

    PURE. Seeds are emitted first (cleaned + deduped, case-insensitive), then
    discovered candidates sorted by ``(has_official, source_count, -len(name))``
    descending with the name as a final tiebreaker for determinism. The combined
    list is deduped and clamped to ``max_competitors`` (clamp 1..6).

    Args:
        candidates: Output of :func:`extract_candidates`.
        max_competitors: Maximum competitors to return (clamped to 1..6).
        seed_competitors: User-provided names always included, in order.

    Returns:
        An ordered list of competitor display names (length <= max_competitors).
    """
    cap = _clamp(max_competitors, 1, 6)
    out: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        clean = name.strip()
        key = _slug(clean)
        if clean and key and key not in seen:
            seen.add(key)
            out.append(clean)

    for s in seed_competitors:
        _add(s)

    ordered = sorted(
        candidates,
        key=lambda c: (c.has_official, c.source_count, -len(c.name), c.name),
        reverse=True,
    )
    for c in ordered:
        if len(out) >= cap:
            break
        _add(c.name)
    return out[:cap]


def discover_competitors(
    category: str,
    *,
    search_fn: SearchFn,
    market_scope: str | None = None,
    goal: str | None = None,
    seed_competitors: tuple[str, ...] = (),
    max_competitors: int = 4,
    max_queries: int = 4,
) -> DiscoveryResult:
    """Run one bounded discovery pass and return ranked competitors.

    Orchestrates the pure core: build queries -> call ``search_fn`` once per
    query (bounded) -> extract candidates -> rank. Never raises: any search error
    is logged and the pass degrades to the seeds (or empty) with an empty
    candidate set, so the caller's run can proceed honestly.

    Args:
        category: The product category to discover competitors for.
        search_fn: ``(query) -> [previews]`` callable (inject a fake in tests; in
            production a thin wrapper over :func:`mingjing.collector.search.search`).
        market_scope: Optional scope token (see :func:`build_discovery_queries`).
        goal: Optional research goal threaded into one query variant.
        seed_competitors: Names always included in the result, in order.
        max_competitors: Maximum competitors to select (clamped 1..6).
        max_queries: Maximum discovery queries to issue (clamped 1..6).

    Returns:
        A :class:`DiscoveryResult` with ``selected`` competitors, ranked
        ``candidates`` (name/source_count/has_official dicts), and the
        ``queries`` actually issued.
    """
    queries = build_discovery_queries(
        category, market_scope=market_scope, goal=goal, max_queries=max_queries
    )
    previews: list[Preview] = []
    for q in queries:
        try:
            results = search_fn(q) or []
        except Exception:  # noqa: BLE001 — discovery is best-effort, never fatal
            _log.warning("discovery: search failed for query=%r; skipping", q, exc_info=True)
            continue
        previews.extend(r for r in results if isinstance(r, dict))

    candidates = extract_candidates(previews, category=category)
    selected = rank_candidates(
        candidates, max_competitors=max_competitors, seed_competitors=seed_competitors
    )
    ranked_payload = [
        {
            "name": c.name,
            "source_count": c.source_count,
            "has_official": c.has_official,
        }
        for c in sorted(
            candidates,
            key=lambda c: (c.has_official, c.source_count, -len(c.name), c.name),
            reverse=True,
        )
    ]
    return DiscoveryResult(selected=selected, candidates=ranked_payload, queries=queries)
