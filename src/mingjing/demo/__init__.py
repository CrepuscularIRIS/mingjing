"""Deterministic demo support: a query-keyed corpus and a curated collect_fn.

These exist ONLY to make the scored demo reproducible and non-empty. They inject
through the existing ``runner.make_run_executor`` seam and change no agent, QA,
graph, or scoring logic. The real feedback loop (QA reject -> revise -> re-collect
-> improve) is exercised unchanged; the corpus only controls which evidence is
available in which round.
"""

from .corpus import corpus_key, load_corpus, make_demo_collect_fn

__all__ = ["corpus_key", "load_corpus", "make_demo_collect_fn"]
