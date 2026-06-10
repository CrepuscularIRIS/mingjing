"""Environment-driven settings for MingJing.

Enforces two demo-critical invariants at load time:
- rate limiting may never be disabled via env (``false`` is refused at startup —
  a fail-loud compliance guard, see ``Settings.load``),
- mode defaults to ``live_first`` (``cache_first`` is the D0 auto-downgrade).
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DepthTier:
    """Knobs for a single collection depth tier."""

    sub_queries: int
    engines: tuple[str, ...]
    top_k: int


# quick vs detailed differ by BREADTH (sub_queries, engines, top_k candidate pool),
# NOT by fetched-source count per round — per-round fetch depth is governed by the
# graph's source_cap = 1 + revision_round weak→strong loop.
DEPTH_TIERS: dict[str, DepthTier] = {
    # Engine order is cosmetic in the deep-collect path: parallel_search runs
    # EVERY (query × engine) pair concurrently and merges, so unavailable engines
    # (missing key/url) just return [] and drop out. `bocha` is listed first as the
    # China-reachable primary; `searxng` is the keyless local aggregator.
    # top_k is the CANDIDATE/snippet pool (cheap): more candidates → more
    # snippet-as-evidence breadth. The number of expensive full-page FETCHES is
    # governed separately by the graph's round-aware source_cap (1 + round), so a
    # large top_k adds coverage without blowing the fetch budget.
    "quick": DepthTier(
        sub_queries=5,
        engines=("bocha", "tavily", "searxng", "duckduckgo"),
        top_k=8,
    ),
    "detailed": DepthTier(
        sub_queries=8,
        engines=("bocha", "tavily", "brave", "searxng", "duckduckgo"),
        top_k=12,
    ),
}


def tier_for(depth: str) -> DepthTier:
    """Return the DepthTier for *depth*, falling back to 'quick' on unknown keys."""
    tier = DEPTH_TIERS.get(depth)
    if tier is None:
        logger.warning("Unknown depth tier %r; falling back to 'quick'", depth)
        tier = DEPTH_TIERS["quick"]
    return tier


@dataclass(frozen=True)
class Settings:
    minimax_base_url: str
    minimax_api_key: str
    minimax_model: str
    mode: str  # "live_first" | "cache_first"  (cache_first = D0 auto-downgrade)
    rate_limiting_enabled: bool
    db_path: str
    cache_db_path: str
    per_field_source_cap: int
    min_source_chars: int
    fetch_timeout_s: float
    revise_round_cap: int
    budget_calls_max: int
    llm_max_tokens: int
    llm_timeout_s: float  # per-call LLM timeout; a stuck provider raises APITimeoutError instead of hanging
    depth: str  # "quick" | "detailed" — selects DepthTier knobs
    deep_collect_workers: int  # parallel worker count for deep-collect
    fetch_budget_per_run: int  # max page fetches per run
    firecrawl_api_key: str  # Firecrawl service API key (empty = disabled)
    firecrawl_base_url: str  # Firecrawl API base URL
    # Report output language for analyst `statement` prose + synthesis sentences.
    # "zh" = Simplified Chinese (the product default, set by load()); "en" keeps
    # the original English prompts. Evidence `value` sub-fields and `snippet`s stay
    # source-verbatim regardless of language, so the QA gate's substring grounding
    # is language-agnostic. The dataclass default is "en" so test-constructed
    # Settings stay English; load() applies the "zh" product default.
    report_language: str = "en"

    @staticmethod
    def load() -> "Settings":
        rl = os.environ.get("MINGJING_RATE_LIMITING_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not rl:
            # Fail-loud compliance invariant: collector throttling/robots posture
            # may never be silently disabled via env. The knob exists only so a
            # `false` is REFUSED at startup instead of producing an unthrottled
            # run that still claims compliance. (The legacy AdaptiveRateLimitTracker
            # this guarded is upstream-LDR lineage, not vendored in this repo.)
            raise ValueError(
                "rate_limiting.enabled must be true (refusing to run unthrottled)"
            )
        return Settings(
            minimax_base_url=os.environ.get("MINGJING_LLM_BASE_URL", "https://api.minimaxi.com/v1"),
            minimax_api_key=os.environ.get("MINIMAX_API_KEY", ""),
            minimax_model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
            mode=os.environ.get("MINGJING_MODE", "live_first"),
            rate_limiting_enabled=rl,
            db_path=os.environ.get("MINGJING_DB", "data/mingjing.db"),
            cache_db_path=os.environ.get("MINGJING_CACHE_DB", "data/cache/cache.db"),
            per_field_source_cap=int(os.environ.get("MINGJING_SOURCE_CAP", "3")),
            # JS-rendered SPA pages (feishu.cn, larksuite.com) fetch HTTP 200 but
            # extract to a ~8-char loading shell; below this floor a fetch is an
            # unusable shell, dropped at collect so the analyst never cites it.
            min_source_chars=int(os.environ.get("MINGJING_MIN_SOURCE_CHARS", "100")),
            fetch_timeout_s=float(os.environ.get("MINGJING_FETCH_TIMEOUT", "8")),
            revise_round_cap=int(os.environ.get("MINGJING_REVISE_CAP", "2")),
            budget_calls_max=int(os.environ.get("MINGJING_BUDGET_CALLS", "40")),
            llm_max_tokens=int(os.environ.get("MINGJING_LLM_MAX_TOKENS", "8000")),
            llm_timeout_s=float(os.environ.get("MINGJING_LLM_TIMEOUT", "90")),
            depth=os.environ.get("MINGJING_DEPTH", "quick"),
            deep_collect_workers=int(os.environ.get("MINGJING_DEEP_WORKERS", "8")),
            fetch_budget_per_run=int(os.environ.get("MINGJING_FETCH_BUDGET", "60")),
            firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
            firecrawl_base_url=os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1"),
            report_language=os.environ.get("MINGJING_REPORT_LANGUAGE", "zh"),
        )
