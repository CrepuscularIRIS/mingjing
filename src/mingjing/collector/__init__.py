"""Collector subpackage: search, robots gate, fetch-with-fallback, independence."""

from .fetch import FetchResult, fetch_with_fallback, is_safe_url
from .independence import count_independent, registrable_domain
from .robots import is_allowed
from .search import search

__all__ = [
    "FetchResult",
    "fetch_with_fallback",
    "is_safe_url",
    "is_allowed",
    "count_independent",
    "registrable_domain",
    "search",
]
