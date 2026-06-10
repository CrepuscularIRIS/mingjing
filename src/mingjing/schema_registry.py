"""Schema registry — loads domain field-schemas from JSON files.

Design: domains are declared in ``src/mingjing/domains/*.json``.  The active
domain is selected via the ``MINGJING_SCHEMA_DOMAIN`` env-var (default:
``"default"``).  ``schemas.py`` calls :func:`resolve_active_schema` at import
time so ``FIELD_SCHEMAS`` stays a plain ``dict`` — all importers are
unaffected.

This module must NOT import from ``schemas.py`` (avoids circular imports).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DOMAINS_DIR: Path = Path(__file__).parent / "domains"

DEFAULT_DOMAIN: str = "default"

# Top-level keys in a domain JSON that are domain-wide config, NOT field specs.
# They are skipped by the per-field validation loop and excluded from the
# returned field-schema dict so existing importers see only real fields.
_RESERVED_KEYS: frozenset[str] = frozenset({"source_weights", "key_fields"})


def list_domains() -> list[str]:
    """Return available domain names (json stems), sorted with ``default`` first.

    Returns:
        A sorted list of domain names where ``"default"`` is always first.
    """
    stems = sorted(p.stem for p in _DOMAINS_DIR.glob("*.json"))
    if DEFAULT_DOMAIN in stems:
        stems.remove(DEFAULT_DOMAIN)
        stems.insert(0, DEFAULT_DOMAIN)
    return stems


def _load_domain_raw(name: str) -> dict[str, Any]:
    """Read and JSON-parse a domain file, returning its raw top-level dict.

    No field validation and no reserved-key filtering is performed here — this
    is the single point that touches the filesystem so both :func:`load_domain`
    and :func:`domain_source_weights` share one read path.

    Args:
        name: Domain stem name (e.g. ``"default"``, ``"ai_agent"``, ``"hr"``).

    Returns:
        The raw top-level ``dict`` parsed from the domain JSON file.

    Raises:
        ValueError: When the domain file doesn't exist or is malformed.
    """
    path = _DOMAINS_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(repr(s) for s in list_domains())
        raise ValueError(
            f"Unknown schema domain: {name!r} (available: {available})"
        )

    try:
        with path.open(encoding="utf-8") as fh:
            raw: dict[str, Any] = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in domain file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(
            f"Domain file {path} must contain a JSON object at the top level"
        )

    return raw


def load_domain(name: str) -> dict[str, dict[str, Any]]:
    """Load and validate a domain's field-schema dict from its JSON file.

    Reserved top-level keys (see :data:`_RESERVED_KEYS`) carry domain-wide
    config rather than field specs; they are skipped during validation and
    excluded from the returned dict.

    Args:
        name: Domain stem name (e.g. ``"default"``, ``"ai_agent"``, ``"hr"``).

    Returns:
        A ``dict[str, dict[str, Any]]`` where each value has ``required`` and
        ``sub_fields`` keys (both ``list[str]``).

    Raises:
        ValueError: When the domain file doesn't exist or is malformed.
    """
    raw = _load_domain_raw(name)

    for field, spec in raw.items():
        if field in _RESERVED_KEYS:
            continue
        if not isinstance(spec, dict):
            raise ValueError(
                f"Domain {name!r}: field {field!r} must be a JSON object"
            )
        for key in ("required", "sub_fields"):
            val = spec.get(key)
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                raise ValueError(
                    f"Domain {name!r}: field {field!r}.{key} must be a list of strings"
                )
        # Every required sub-field must be declared in sub_fields — catches a
        # config typo that would otherwise make the QA gates check a sub-field
        # the schema never advertises.
        missing = set(spec["required"]) - set(spec["sub_fields"])
        if missing:
            raise ValueError(
                f"Domain {name!r}: field {field!r} requires "
                f"{sorted(missing)} not present in sub_fields"
            )

    return {f: s for f, s in raw.items() if f not in _RESERVED_KEYS}


def domain_source_weights(name: str | None = None) -> dict[str, str]:
    """Return the active (or named) domain's source-type → reliability-letter map.

    Args:
        name: Domain stem name; when ``None`` the active domain (per env) is used.

    Returns:
        The ``source_weights`` mapping, or an empty dict when absent / malformed.
    """
    raw = _load_domain_raw(name or resolved_active_domain())
    weights = raw.get("source_weights", {})
    return weights if isinstance(weights, dict) else {}


def resolve_active_schema() -> dict[str, dict[str, Any]]:
    """Return the field-schema dict for the active domain.

    Reads ``MINGJING_SCHEMA_DOMAIN`` from the environment (default:
    ``"default"``).  If the env-var names an unknown domain, falls back to
    ``default`` and emits a warning — so a misconfigured env never crashes the
    app at import time.

    Returns:
        The field-schema dict for the resolved domain.
    """
    domain = os.environ.get("MINGJING_SCHEMA_DOMAIN", DEFAULT_DOMAIN)
    try:
        return load_domain(domain)
    except ValueError:
        logger.warning(
            "MINGJING_SCHEMA_DOMAIN=%r is not a known domain; "
            "falling back to %r",
            domain,
            DEFAULT_DOMAIN,
        )
        return load_domain(DEFAULT_DOMAIN)


def resolved_active_domain() -> str:
    """Return the domain name that :func:`resolve_active_schema` actually uses.

    Mirrors the env→fallback logic so callers (e.g. ``GET /schemas``) report the
    truly-active domain rather than a bogus env value that silently fell back.

    Returns:
        The resolved domain name (the env value if it names a real domain, else
        ``DEFAULT_DOMAIN``).
    """
    domain = os.environ.get("MINGJING_SCHEMA_DOMAIN", DEFAULT_DOMAIN)
    return domain if domain in list_domains() else DEFAULT_DOMAIN
