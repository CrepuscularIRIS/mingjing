"""Drive one deterministic demo run into the shared DB and print its run_id.

Uses the curated corpus (deterministic evidence) with the REAL analyst LLM, in
cache_first mode. Run `make api` + `make web` (same MINGJING_DB) to view it.

Usage:
    MINGJING_MODE=cache_first uv run python scripts/run_demo.py <competitor>
"""

import sys

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.demo.corpus import load_corpus, make_demo_collect_fn
from mingjing.runner import make_run_executor


def main() -> None:
    competitor = sys.argv[1] if len(sys.argv) > 1 else "Notion"
    manifest = f"demo/corpus/{competitor.lower()}.json"
    corpus = load_corpus(manifest)

    settings = Settings.load()  # MiniMax/Doubao from env; mode from MINGJING_MODE
    db = Database(settings.db_path)
    db.init_schema()

    run_id = db.create_run(
        category="AI 产品竞品分析",
        competitors=[competitor],
        goal=f"分析 {competitor} 的定价、用户画像、功能与 SWOT",
    )
    print(f"run_id={run_id}", flush=True)

    executor = make_run_executor(
        lambda: db,
        settings=settings,
        collect_fn=make_demo_collect_fn(corpus),
        # analyze_fn=None -> real analyst LLM (agents.analyst.analyze_field)
        prewarm=False,
    )
    executor(run_id)
    print(f"done run_id={run_id}", flush=True)


if __name__ == "__main__":
    main()
