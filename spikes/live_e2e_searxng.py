"""Live end-to-end run with REAL search discovery via SearXNG (no cache workaround).

Unlike spikes/live_post_runs.py (which seeded the cache because DuckDuckGo was
throttled), this driver proves the FULL live loop:
    search (SearXNG) -> robots -> live fetch -> analyst (MiniMax) -> QA -> write

It uses the production run executor with the REAL collect_fn/analyst (no fakes,
no seeded cache). It then reports, per field, whether the claim reached
status="pass" — which doubles as the live re-verification that the
VALUE_UNSUPPORTED gate (now scoped to required sub-fields) does NOT over-reject
honest values on real competitor pages.

Usage:
  source .venv/bin/activate
  set -a; . /home/lingxufeng/Langgraph/.env; set +a
  unset MINGJING_LLM_BASE_URL
  export MINGJING_SEARXNG_URL=http://localhost:8888
  export MINGJING_DB=$(mktemp -u --suffix=.db)
  export MINGJING_CACHE_DB=$(mktemp -u --suffix=.db)
  python spikes/live_e2e_searxng.py [Competitor]
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("live_e2e_searxng")

os.environ.pop("MINGJING_LLM_BASE_URL", None)
for var, suffix in (("MINGJING_DB", ".db"), ("MINGJING_CACHE_DB", ".db")):
    if not os.environ.get(var):
        fd, p = tempfile.mkstemp(suffix=suffix)
        os.close(fd); os.unlink(p)
        os.environ[var] = p

COMPETITOR = sys.argv[1] if len(sys.argv) > 1 else "Notion"

from mingjing.config import Settings

settings = Settings.load()
assert settings.minimax_base_url == "https://api.minimaxi.com/v1", settings.minimax_base_url
assert settings.minimax_api_key, "MINIMAX_API_KEY not set"
sx_url = os.environ.get("MINGJING_SEARXNG_URL", "")
assert sx_url, "MINGJING_SEARXNG_URL not set — point it at the local SearXNG instance"
logger.info("config OK: base_url=%s model=%s key=[SET len=%d] searxng=%s mode=%s",
            settings.minimax_base_url, settings.minimax_model,
            len(settings.minimax_api_key), sx_url, settings.mode)

# --- Step 1: prove SearXNG discovery works through MingJing's own search() ---
from mingjing.collector.search import search as _search_fn

hits = _search_fn(f"{COMPETITOR} pricing", max_results=5)
logger.info("SearXNG discovery: %d hits", len(hits))
for h in hits[:5]:
    logger.info("  hit: %s | %s", h.get("url", ""), (h.get("title", "") or "")[:60])
assert hits, "SearXNG returned 0 hits — discovery would be bypassed"

# --- Step 2: drive the production executor with REAL collect/analyst ---
from fastapi.testclient import TestClient

from mingjing.api import create_app
from mingjing.db import Database
from mingjing.runner import make_run_executor

_db_box: list[Database] = []


def _get_db() -> Database:
    if not _db_box:
        db = Database(settings.db_path)
        db.init_schema()
        _db_box.append(db)
    return _db_box[0]


executor = make_run_executor(get_db=_get_db, settings=settings, prewarm=False)
app = create_app(run_executor=executor, wire_default_executor=False)
client = TestClient(app, raise_server_exceptions=False)

assert client.get("/health").status_code == 200
resp = client.post("/runs", json={
    "category": "saas", "competitors": [COMPETITOR],
    "goal": "competitive pricing & positioning analysis",
})
assert resp.status_code == 201, f"{resp.status_code} {resp.text}"
run_id = resp.json()["run_id"]
logger.info("run created: %s", run_id)

# --- Step 3: poll to terminal ---
db = _get_db()
start = time.time()
status = None
while time.time() - start < 360:
    row = db.get_run(run_id)
    status = row.get("status") if row else None
    if status in {"complete", "partial", "error"}:
        break
    time.sleep(5)
elapsed = time.time() - start
logger.info("terminal status=%s after %.1fs", status, elapsed)

# --- Step 4: per-field claim outcomes (E2E + value-gate re-verify) ---
latest = db.latest_claims_for_run(run_id)
logger.info("=== claims (%d) ===", len(latest))
passed_fields, draft_fields = [], []
for c in latest:
    fld, st, stg = c.get("schema_field"), c.get("status"), c.get("evidence_strength")
    val = json.loads(c.get("value_json") or "{}")
    logger.info("  %-14s status=%-6s strength=%-8s value=%s",
                fld, st, stg, json.dumps(val, ensure_ascii=False)[:160])
    (passed_fields if st == "pass" else draft_fields).append(fld)

# Source provenance (LIVE proves real fetch from discovered URLs)
modes: dict[str, int] = {}
src_urls = []
for c in latest:
    for ev in json.loads(c.get("evidence_json") or "[]"):
        sid = ev.get("source_id") if isinstance(ev, dict) else ev
        src = db.get_source(sid) if sid else None
        if src:
            modes[src.get("source_mode") or "?"] = modes.get(src.get("source_mode") or "?", 0) + 1
            if src.get("url"):
                src_urls.append((src.get("source_mode"), src.get("url")))

# LLM token totals
calls = client.get(f"/runs/{run_id}/llm_calls").json().get("calls", [])
tokens = sum(c.get("total_tokens") or 0 for c in calls)

print("\n" + "=" * 72)
print(f"LIVE E2E (SearXNG discovery) — competitor={COMPETITOR}")
print(f"  terminal status : {status}  ({elapsed:.0f}s)")
print(f"  search hits      : {len(hits)} (SearXNG)")
print(f"  claims passed    : {sorted(set(passed_fields))}")
print(f"  claims draft     : {sorted(set(draft_fields))}")
print(f"  source modes     : {modes}")
print(f"  LLM calls/tokens : {len(calls)} / {tokens}")
for m, u in src_urls[:8]:
    print(f"    [{m}] {u}")
print("=" * 72)

# E2E passes if the loop ran to a terminal state with >=1 passed claim and >=1
# LIVE source (real discovery+fetch). pricing_model passing is the headline.
ok = (
    status in {"complete", "partial"}
    and any(f == "pricing_model" for f in passed_fields)
    and modes.get("LIVE", 0) >= 1
)
print("RESULT:", "PASS" if ok else "REVIEW", "— pricing_model passed:",
      "pricing_model" in passed_fields, "| LIVE sources:", modes.get("LIVE", 0))
sys.exit(0 if ok else 2)
