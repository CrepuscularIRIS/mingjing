"""Drive a Discovery-Mode demo run into the shared DB and print its run_id.

Demonstrates "give a CATEGORY, the system DISCOVERS the competitors": the run is
created with an EMPTY competitor list + a category, and the bounded discovery
pre-step (mingjing.discovery) selects the top competitors from a CACHED set of
real search-result previews. Selection is computed by the real ranking algorithm
over real product pages — nothing hand-picked — so it is reproducible offline and
safe for the 答辩 (live CN search is too noisy for a demo; see the plan doc).

Two modes:

    # default — CLOSED LOOP: discovers Notion + Linear (which have a real corpus)
    # so the SAME run goes category → discover → analyze → QA → verified report.
    uv run python scripts/run_discovery_demo.py            # (needs an LLM key)

    # discovery-only story: discovers the CN AI-Agent set (no corpus -> the run
    # shows the discovery panel + trace, analysis is honestly empty/partial).
    uv run python scripts/run_discovery_demo.py discovery-only

Run `make api` + `make web` (same MINGJING_DB), then open the printed run via
近期运行 or ?run=<id>.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.demo.corpus import load_corpus, make_demo_collect_fn
from mingjing.discovery import discover_competitors
from mingjing.runner import make_run_executor

DISCOVERY_DIR = Path("demo/discovery")


def _fixture_search_fn(previews: list[dict[str, Any]]):
    """A fixture-backed search_fn: serve the cached previews once, then nothing.

    Extraction dedupes by registrable domain, so issuing the curated set on the
    first query is sufficient and keeps the pass bounded/deterministic.
    """
    served = {"done": False}

    def search_fn(_query: str) -> list[dict[str, Any]]:
        if served["done"]:
            return []
        served["done"] = True
        return previews

    return search_fn


def _make_discover_fn(previews: list[dict[str, Any]]):
    def discover_fn(category: str, **kwargs: Any) -> Any:
        return discover_competitors(category, search_fn=_fixture_search_fn(previews), **kwargs)

    return discover_fn


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "closed-loop"
    settings = Settings.load()
    db = Database(settings.db_path)
    db.init_schema()

    if mode == "discovery-only":
        fixture = json.loads((DISCOVERY_DIR / "ai-agent-cn.json").read_text(encoding="utf-8"))
        run_id = db.create_run(
            category=fixture["category"],
            competitors=[],
            goal="中国范围内通用 AI Agent 竞品分析（定价 / 用户画像 / 功能 / SWOT）",
            market_scope=fixture.get("market_scope", "china"),
            max_competitors=4,
        )
        print(f"run_id={run_id}", flush=True)

        def empty_collect(query: str, *, cache: Any, source_cap: int, mode: str = "live_first") -> list[dict[str, Any]]:
            return []  # no corpus for the discovered products -> honest empty analysis

        executor = make_run_executor(
            lambda: db,
            settings=settings,
            discover_fn=_make_discover_fn(fixture["previews"]),
            collect_fn=empty_collect,
            prewarm=False,
        )
    else:
        # CLOSED LOOP: discover Notion + Linear, then analyze them with the real
        # curated corpus + the real analyst LLM (same path as scripts/run_demo.py).
        fixture = json.loads((DISCOVERY_DIR / "collab-tools.json").read_text(encoding="utf-8"))
        merged_corpus: dict[str, Any] = {}
        for name in ("notion", "linear"):
            merged_corpus.update(load_corpus(f"demo/corpus/{name}.json"))
        run_id = db.create_run(
            category=fixture["category"],
            competitors=[],
            goal="团队协作 / 项目管理工具竞品分析（定价 / 用户画像 / 功能 / SWOT）",
            market_scope=fixture.get("market_scope", "global"),
            max_competitors=2,
        )
        print(f"run_id={run_id}", flush=True)
        executor = make_run_executor(
            lambda: db,
            settings=settings,
            discover_fn=_make_discover_fn(fixture["previews"]),
            collect_fn=make_demo_collect_fn(merged_corpus),
            # analyze_fn=None -> real analyst LLM (agents.analyst.analyze_field)
            prewarm=False,
        )

    executor(run_id)
    row = db.get_run(run_id)
    print(f"done run_id={run_id} discovered={row['competitors']} status={row['status']}", flush=True)


if __name__ == "__main__":
    main()
