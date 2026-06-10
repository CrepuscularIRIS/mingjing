"""Drive ONE multi-competitor demo run into the shared DB and print its run_id.

Same honesty contract as ``run_demo.py`` (curated real corpus + REAL analyst LLM,
``cache_first``), but merges several competitor corpora into a single run so the
report's competitor-by-field comparison matrix actually renders (it hides itself
for a single competitor). Each competitor only contributes the fields for which
we hold real cached evidence — sparse competitors stay honestly sparse (their
uncovered fields show as coverage gaps, never fabricated).

Usage:
    MINGJING_MODE=cache_first uv run python scripts/run_demo_multi.py Notion Linear
"""

import sys
from typing import Any

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.demo.corpus import load_corpus, make_demo_collect_fn
from mingjing.runner import make_run_executor


def main() -> None:
    competitors = sys.argv[1:] or ["Notion", "Linear"]

    # Merge per-competitor corpora. Keys are build_query(competitor, field), which
    # already embeds the competitor name, so distinct competitors never collide.
    merged: dict[str, dict[str, Any]] = {}
    for competitor in competitors:
        corpus = load_corpus(f"demo/corpus/{competitor.lower()}.json")
        merged.update(corpus)

    settings = Settings.load()  # MiniMax/Doubao from env; mode from MINGJING_MODE
    db = Database(settings.db_path)
    db.init_schema()

    run_id = db.create_run(
        category="AI 产品竞品分析",
        competitors=list(competitors),
        goal="对比 " + " vs ".join(competitors) + " 的定价、用户画像、功能与 SWOT",
    )
    print(f"run_id={run_id} competitors={competitors}", flush=True)

    executor = make_run_executor(
        lambda: db,
        settings=settings,
        collect_fn=make_demo_collect_fn(merged),
        # analyze_fn=None -> real analyst LLM (agents.analyst.analyze_field)
        prewarm=False,
    )
    executor(run_id)
    print(f"done run_id={run_id}", flush=True)


if __name__ == "__main__":
    main()
