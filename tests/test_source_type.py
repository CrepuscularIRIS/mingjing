"""Source-type classification must not be fooled by look-alike domains (C2).

``infer_source_type`` decides ``official`` vs ``web``; ``official`` flips the
authoritative gate in :func:`scoring.strength`. A bare substring match would let
an adversarial host (``attackacme.com``) masquerade as the competitor and
fabricate a "strong" tier, so classification is by full dot-LABEL / registrable
leading-label only.
"""

from mingjing.claim_builder import infer_source_type


def test_subdomain_label_is_official() -> None:
    # The competitor token is a full dot-label of the host.
    assert infer_source_type("https://acme.example.com/pricing", "Acme Corp") == "official"


def test_apex_registrable_leading_label_is_official() -> None:
    # Registrable domain's leading label equals the token.
    assert infer_source_type("https://www.acme.com/about", "Acme") == "official"
    assert infer_source_type("https://acme.com/about", "Acme") == "official"


def test_multi_label_suffix_registrable_is_official() -> None:
    # eTLD+1 with a known multi-label suffix: leading label still matches.
    assert infer_source_type("https://acme.co.uk/pricing", "Acme") == "official"


def test_substring_false_positives_are_not_official() -> None:
    # None of these hosts contain the token as a standalone label.
    assert infer_source_type("https://attackacme.com/pricing", "Acme") == "web"
    assert infer_source_type("https://not-salesforce.com/x", "Salesforce") == "web"
    assert infer_source_type("https://acme-review.net/x", "Acme") == "web"


def test_plain_third_party_is_not_official() -> None:
    assert infer_source_type("https://reviews.example.net/acme", "Acme") == "web"


def test_empty_url_or_competitor_defaults_web() -> None:
    assert infer_source_type("", "Acme") == "web"
    assert infer_source_type("https://acme.example.com", "") == "web"


# ---------------------------------------------------------------------------
# Advisory review/forum classification (维度5) — NON-authoritative labels.
# ---------------------------------------------------------------------------


def test_review_aggregators_classified_review() -> None:
    assert infer_source_type("https://www.g2.com/products/notion/reviews", "Notion") == "review"
    assert infer_source_type("https://www.capterra.com/p/123/Notion/", "Notion") == "review"
    assert infer_source_type("https://www.trustradius.com/products/notion", "Notion") == "review"


def test_forums_classified_forum() -> None:
    assert infer_source_type("https://www.reddit.com/r/Notion/comments/x", "Notion") == "forum"
    assert infer_source_type("https://zhihu.com/question/123", "Notion") == "forum"
    # 'forum' subdomain label on an arbitrary host is treated as a forum.
    assert infer_source_type("https://forum.example.com/t/notion", "Notion") == "forum"


def test_official_wins_over_review_forum() -> None:
    # The official check runs first: a competitor whose own site somehow shares a
    # label must NOT be demoted to review/forum.
    assert infer_source_type("https://reddit.com/about", "Reddit") == "official"


def test_unlisted_third_party_still_web() -> None:
    # Regression: example.net is NOT a listed review/forum domain → still 'web'.
    assert infer_source_type("https://reviews.example.net/acme", "Acme") == "web"
    assert infer_source_type("https://someblog.io/notion-review", "Notion") == "web"
