"""Admiralty Code (STANAG 2511) two-axis grade — SECONDARY metadata only.

This module produces a pure, band-only Admiralty grade (e.g. ``"B2"``) attached
to evidence items as *secondary* metadata. The PRIMARY ``evidence_strength``
(strong/moderate/weak) is unchanged and never derived from these functions.

Bands only, never decimals: the reliability axis is a letter (A–F) and the
credibility axis is a digit (1–6); the grade is their concatenation.
"""

from .schema_registry import domain_source_weights

# Built-in reliability fallback by source type when the active domain's
# ``source_weights`` map omits the type. Note ``"A"`` is never assigned
# initially — an unknown source type degrades to ``"F"``.
_FALLBACK = {
    "official": "B",
    "news": "C",
    "review": "D",
    "survey": "D",
    "forum": "D",
    "web": "D",
    "blog": "E",
}


def fallback_source_weights() -> dict[str, str]:
    """Return a COPY of the built-in source-type → reliability-letter fallback.

    Public accessor for the private ``_FALLBACK`` so read-only views (e.g. the
    ``/schemas/{domain}`` source-weights legend) can show the effective default
    letters without reaching into a private name. Returns a fresh dict so callers
    cannot mutate the module state; behavior of :func:`reliability_letter` /
    :func:`grade` is unchanged.
    """
    return dict(_FALLBACK)


def reliability_letter(source_type: str, schema_domain: str | None = None) -> str:
    """Return the reliability letter (A–F) for a source type.

    Reads the active (or named) SCHEMA domain's ``source_weights`` map first,
    then the built-in ``_FALLBACK``; an unknown type degrades to ``"F"``.

    Args:
        source_type: The source type token (e.g. ``"official"``).
        schema_domain: Optional SCHEMA-domain stem (e.g. ``"default"``/``"hr"``)
            whose ``source_weights`` to use; ``None`` uses the active schema
            domain. This is NOT a source's registrable web domain.

    Returns:
        A single reliability letter.
    """
    # Defensive: an unknown schema-domain name degrades to the built-in fallback
    # rather than crash, since this is non-fatal SECONDARY metadata.
    try:
        weights = domain_source_weights(schema_domain) or {}
    except ValueError:
        weights = {}
    return weights.get(source_type, _FALLBACK.get(source_type, "F"))


def credibility_number(*, independent_corroborators: int, contradictors: int) -> int:
    """Return the credibility digit (1–5) from corroboration/contradiction counts.

    Contradiction dominates: two or more contradictors yields ``5``, one yields
    ``4``. Otherwise corroboration improves credibility: two or more independent
    corroborators yields ``1``, one yields ``2``, and none yields the neutral
    ``3``.

    Args:
        independent_corroborators: Count of distinct supporting domains.
        contradictors: Count of distinct refuting domains.

    Returns:
        A credibility digit.
    """
    if contradictors >= 2:
        return 5
    if contradictors == 1:
        return 4
    if independent_corroborators >= 2:
        return 1
    if independent_corroborators == 1:
        return 2
    return 3


def grade(
    source_type: str,
    *,
    independent_corroborators: int,
    contradictors: int,
    schema_domain: str | None = None,
) -> str:
    """Return the two-axis Admiralty grade string (e.g. ``"B2"``).

    Args:
        source_type: The source type token.
        independent_corroborators: Count of OTHER distinct supporting domains
            (excluding this source's own domain).
        contradictors: Count of distinct refuting domains.
        schema_domain: Optional SCHEMA-domain stem for the reliability lookup;
            ``None`` uses the active schema domain.

    Returns:
        ``letter + digit`` (band only, never a decimal).
    """
    letter = reliability_letter(source_type, schema_domain)
    number = credibility_number(
        independent_corroborators=independent_corroborators,
        contradictors=contradictors,
    )
    return f"{letter}{number}"
