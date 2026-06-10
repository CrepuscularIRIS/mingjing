"""Tests for schema_registry.py — config-driven domain switching (Task B)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mingjing.schema_registry import (
    list_domains,
    load_domain,
    resolve_active_schema,
)
from mingjing.schemas import FIELD_SCHEMAS

# ---------------------------------------------------------------------------
# Expected default domain (byte-equivalent to the original literal)
# ---------------------------------------------------------------------------

_EXPECTED_DEFAULT: dict = {
    "pricing_model": {
        "required": ["tiers"],
        "sub_fields": ["tiers", "free_tier", "currency", "billing_period"],
    },
    "user_sentiment": {
        "required": ["overall"],
        "sub_fields": ["overall", "positives", "negatives", "sample_size"],
    },
    "feature_tree": {
        "required": ["categories"],
        "sub_fields": ["categories", "features", "depth"],
    },
    "user_persona": {
        "required": ["segments"],
        "sub_fields": ["segments", "needs", "pain_points"],
    },
    "swot": {
        "required": ["strengths", "weaknesses", "opportunities", "threats"],
        "sub_fields": ["strengths", "weaknesses", "opportunities", "threats"],
    },
}


# ---------------------------------------------------------------------------
# load_domain
# ---------------------------------------------------------------------------


def test_load_domain_default_byte_equal():
    """load_domain('default') must be identical to the original 5-field literal."""
    assert load_domain("default") == _EXPECTED_DEFAULT


def test_load_domain_unknown_raises():
    with pytest.raises(ValueError, match="Unknown schema domain"):
        load_domain("nope")


def test_load_domain_ai_agent_has_8_fields():
    schema = load_domain("ai_agent")
    assert len(schema) == 8


def test_load_domain_ai_agent_required_subset_of_sub_fields():
    """Every required item must appear in sub_fields (catches typos)."""
    schema = load_domain("ai_agent")
    for field, spec in schema.items():
        required = set(spec["required"])
        sub_fields = set(spec["sub_fields"])
        assert required.issubset(sub_fields), (
            f"ai_agent/{field}: required items {required - sub_fields!r} "
            "not in sub_fields"
        )


def test_load_domain_hr_has_5_fields():
    schema = load_domain("hr")
    assert len(schema) == 5


def test_load_domain_hr_required_subset_of_sub_fields():
    schema = load_domain("hr")
    for field, spec in schema.items():
        required = set(spec["required"])
        sub_fields = set(spec["sub_fields"])
        assert required.issubset(sub_fields), (
            f"hr/{field}: required items {required - sub_fields!r} "
            "not in sub_fields"
        )


# ---------------------------------------------------------------------------
# list_domains
# ---------------------------------------------------------------------------


def test_list_domains_contains_expected():
    domains = list_domains()
    assert "default" in domains
    assert "ai_agent" in domains
    assert "hr" in domains


def test_list_domains_default_is_first():
    assert list_domains()[0] == "default"


# ---------------------------------------------------------------------------
# resolve_active_schema
# ---------------------------------------------------------------------------


def test_resolve_active_schema_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("MINGJING_SCHEMA_DOMAIN", raising=False)
    schema = resolve_active_schema()
    assert schema == _EXPECTED_DEFAULT


def test_resolve_active_schema_hr_via_env(monkeypatch):
    monkeypatch.setenv("MINGJING_SCHEMA_DOMAIN", "hr")
    schema = resolve_active_schema()
    assert len(schema) == 5
    assert "integration_matrix" in schema


def test_resolve_active_schema_bogus_env_falls_back_to_default(monkeypatch):
    """A bad env value must NOT raise — falls back to default."""
    monkeypatch.setenv("MINGJING_SCHEMA_DOMAIN", "totally_unknown_domain_xyz")
    schema = resolve_active_schema()
    assert schema == _EXPECTED_DEFAULT


# ---------------------------------------------------------------------------
# Regression: FIELD_SCHEMAS import back-compat (env must be unset for this)
# ---------------------------------------------------------------------------


def test_field_schemas_import_equals_default(monkeypatch):
    """FIELD_SCHEMAS (with env unset) must equal the original 5-field dict."""
    # FIELD_SCHEMAS is evaluated at import time, so we compare directly.
    # The test suite must not set MINGJING_SCHEMA_DOMAIN globally.
    monkeypatch.delenv("MINGJING_SCHEMA_DOMAIN", raising=False)
    # Re-import to ensure we pick up the env state — but since it's already
    # imported, just assert the module-level value equals expected.
    # (If the env was unset during collection, this holds.)
    assert set(FIELD_SCHEMAS) == {
        "pricing_model",
        "user_sentiment",
        "feature_tree",
        "user_persona",
        "swot",
    }
    assert FIELD_SCHEMAS == _EXPECTED_DEFAULT


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """FastAPI test client with an injected in-memory DB and no executor."""
    import os as _os
    import tempfile

    from mingjing.api import create_app
    from mingjing.db import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = Database(db_path)
        db.init_schema()
        app = create_app(db=db, run_executor=None)
        with TestClient(app) as c:
            yield c
    finally:
        try:
            _os.unlink(db_path)
        except OSError:
            pass


def test_get_schemas_lists_domains(client):
    resp = client.get("/schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert "domains" in data
    assert "active" in data
    assert "default" in data["domains"]
    assert "ai_agent" in data["domains"]
    assert "hr" in data["domains"]


def test_get_schemas_domain_ai_agent(client):
    resp = client.get("/schemas/ai_agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "ai_agent"
    assert len(data["fields"]) == 8


def test_get_schemas_domain_unknown_returns_404(client):
    resp = client.get("/schemas/nope")
    assert resp.status_code == 404


def test_get_schema_domain_includes_source_weights(client):
    resp = client.get("/schemas/default")
    assert resp.status_code == 200
    sw = resp.json()["source_weights"]
    assert set(sw) == {"weights", "fallback", "unknown_letter"}
    assert sw["fallback"]["official"] == "B"  # built-in default
    assert sw["unknown_letter"] == "F"


def test_get_schema_domain_source_weights_additive_fields_unchanged(client):
    # The legend block is purely additive: existing fields shape is unaffected.
    data = client.get("/schemas/ai_agent").json()
    assert len(data["fields"]) == 8
    assert data["source_weights"]["weights"] == {}  # ai_agent defines none


def test_source_weights_view_is_advisory_copy(client):
    # The fallback is a copy — mutating the response cannot affect module state.
    from mingjing.admiralty import fallback_source_weights

    a = fallback_source_weights()
    a["official"] = "ZZZ"
    assert fallback_source_weights()["official"] == "B"


# ---------------------------------------------------------------------------
# Reserved-key skip + source_weights accessor (Task 1: M5)
# ---------------------------------------------------------------------------

from mingjing.schema_registry import domain_source_weights  # noqa: E402


def test_domain_with_source_weights_loads(tmp_path, monkeypatch):
    import json

    d = tmp_path / "domains"
    d.mkdir()
    (d / "demo.json").write_text(
        json.dumps(
            {
                "pricing_model": {
                    "required": ["tiers"],
                    "sub_fields": ["tiers", "free_tier"],
                },
                "source_weights": {"official": "B", "review": "D"},
                "key_fields": ["pricing_model"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("mingjing.schema_registry._DOMAINS_DIR", d)
    schema = load_domain("demo")
    assert "pricing_model" in schema
    assert "source_weights" not in schema  # reserved key NOT treated as a field
    assert domain_source_weights("demo") == {"official": "B", "review": "D"}
