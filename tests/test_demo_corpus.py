import json
from pathlib import Path

from mingjing.demo.corpus import corpus_key, load_corpus, make_demo_collect_fn
from mingjing.graph_nodes import build_query
from mingjing.graph_nodes import build_query as _bq


def _write_manifest(tmp_path) -> Path:
    manifest = {
        "competitor": "Acme",
        "fields": {
            "pricing_model": [
                {"url": "https://thin.example/a", "title": "A", "source_type": "web", "text": "free plan"},
                {"url": "https://acme.example/pricing", "title": "P", "source_type": "official",
                 "text": "Acme Pro tier costs 10 USD per month"},
            ]
        },
    }
    p = tmp_path / "acme.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


def test_corpus_key_uses_build_query():
    assert corpus_key("Acme", "pricing_model") == build_query("Acme", "pricing_model")


def test_load_corpus_keys_entries_by_query(tmp_path):
    corpus = load_corpus(_write_manifest(tmp_path))
    key = build_query("Acme", "pricing_model")
    assert key in corpus
    assert corpus[key]["competitor"] == "Acme"
    assert corpus[key]["field"] == "pricing_model"
    assert len(corpus[key]["sources"]) == 2
    assert corpus[key]["sources"][0]["url"] == "https://thin.example/a"


def test_load_corpus_rejects_non_object_toplevel(tmp_path):
    import pytest
    p = tmp_path / "bad.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus(p)


def test_load_corpus_rejects_non_list_field(tmp_path):
    import json as _json

    import pytest
    p = tmp_path / "bad2.json"
    p.write_text(_json.dumps({"competitor": "Acme", "fields": {"pricing_model": {"not": "a list"}}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus(p)


def _corpus():
    key = _bq("Acme", "pricing_model")
    return {
        key: {
            "competitor": "Acme",
            "field": "pricing_model",
            "sources": [
                {"url": "https://thin.example/a", "title": "A", "source_type": "web", "text": "free plan"},
                {"url": "https://acme.example/pricing", "title": "P", "source_type": "official",
                 "text": "Acme Pro tier costs 10 USD per month"},
            ],
        }
    }


def test_collect_fn_round0_returns_one_thin_source():
    fn = make_demo_collect_fn(_corpus())
    out = fn(_bq("Acme", "pricing_model"), cache=None, source_cap=1, mode="cache_first")
    assert len(out) == 1
    assert out[0]["fetched"] is True
    assert out[0]["url"] == "https://thin.example/a"
    assert out[0]["text"] == "free plan"
    assert out[0]["source_mode"] == "CACHED"


def test_collect_fn_round1_adds_strong_source():
    fn = make_demo_collect_fn(_corpus())
    out = fn(_bq("Acme", "pricing_model"), cache=None, source_cap=2, mode="cache_first")
    assert [s["url"] for s in out] == ["https://thin.example/a", "https://acme.example/pricing"]


def test_collect_fn_unknown_query_returns_empty():
    fn = make_demo_collect_fn(_corpus())
    assert fn("totally unknown query", cache=None, source_cap=2, mode="cache_first") == []
