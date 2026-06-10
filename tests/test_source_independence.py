"""Task 9 unit tests: source independence counting (PURE, offline).

``count_independent`` dedupes by registrable domain: two URLs on the same
registrable domain count as one independent source; different domains count
separately. No network access.
"""

from mingjing.collector.independence import count_independent, registrable_domain


def test_same_domain_counts_once():
    sources = [
        "https://www.example.com/pricing",
        "https://blog.example.com/post",
        "http://example.com/about",
    ]
    assert count_independent(sources) == 1


def test_distinct_domains_count_separately():
    sources = [
        "https://example.com/a",
        "https://other.org/b",
    ]
    assert count_independent(sources) == 2


def test_mixed():
    sources = [
        "https://www.example.com/a",
        "https://example.com/b",
        "https://news.ycombinator.com/item",
        "https://other.org/x",
    ]
    assert count_independent(sources) == 3


def test_accepts_dict_sources():
    sources = [
        {"url": "https://example.com/a"},
        {"url": "https://example.com/b"},
        {"url": "https://other.org/c"},
    ]
    assert count_independent(sources) == 2


def test_empty():
    assert count_independent([]) == 0


def test_registrable_domain_strips_subdomains():
    assert registrable_domain("https://blog.example.com/x") == "example.com"
    assert registrable_domain("https://example.co.uk/y") == "example.co.uk"
