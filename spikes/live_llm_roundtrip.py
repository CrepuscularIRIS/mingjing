"""Live round-trip verification spike for MiniMax M2.7 via call_llm.

Verifies:
1. Settings.load() resolves the /v1 base_url and correct model name.
2. call_llm(..., schema=True) makes a real network round-trip.
3. The llm_calls row in sqlite captures a non-empty prompt_json, output_text,
   and a positive total_tokens.

Usage (from /home/lingxufeng/Langgraph/mingjing):
    source .venv/bin/activate
    set -a; . /home/lingxufeng/Langgraph/.env; set +a
    unset MINGJING_LLM_BASE_URL 2>/dev/null || true
    python spikes/live_llm_roundtrip.py
"""

import json
import os
import sys
import tempfile
import traceback

# ---------------------------------------------------------------------------
# Ensure the src package is importable when run from the repo root.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mingjing.config import Settings
from mingjing.db import Database
from mingjing.llm import call_llm

EXPECTED_BASE_URL = "https://api.minimaxi.com/v1"
EXPECTED_MODEL = "MiniMax-M2.7"

PASS = "LIVE LLM ROUND-TRIP: PASS"
FAIL_PREFIX = "LIVE LLM ROUND-TRIP: FAIL"


def _assert(condition: bool, msg: str) -> None:
    if not condition:
        print(f"{FAIL_PREFIX} — {msg}", flush=True)
        sys.exit(1)


def main() -> None:
    # ------------------------------------------------------------------
    # Step 1: Verify Settings.load() resolves the correct /v1 endpoint.
    # ------------------------------------------------------------------
    api_key_len = len(os.environ.get("MINIMAX_API_KEY", ""))
    print(f"[config] MINIMAX_API_KEY present: {'[SET]' if api_key_len > 0 else '[MISSING]'} (len={api_key_len})")

    try:
        settings = Settings.load()
    except Exception as exc:
        print(f"{FAIL_PREFIX} — Settings.load() raised: {exc}", flush=True)
        sys.exit(1)

    print(f"[config] minimax_base_url = {settings.minimax_base_url!r}")
    print(f"[config] minimax_model    = {settings.minimax_model!r}")

    _assert(
        settings.minimax_base_url == EXPECTED_BASE_URL,
        f"base_url mismatch: got {settings.minimax_base_url!r}, want {EXPECTED_BASE_URL!r}. "
        f"Did MINGJING_LLM_BASE_URL get exported with the /anthropic value? Run: unset MINGJING_LLM_BASE_URL",
    )
    _assert(
        settings.minimax_model == EXPECTED_MODEL,
        f"model mismatch: got {settings.minimax_model!r}, want {EXPECTED_MODEL!r}",
    )
    _assert(
        len(settings.minimax_api_key) > 20,
        "MINIMAX_API_KEY is empty or too short — is .env loaded?",
    )
    print("[config] assertions PASSED\n")

    # ------------------------------------------------------------------
    # Step 2: Create a fresh temp sqlite DB, init schema, create a run.
    # ------------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    print(f"[db] temp DB: {db_path}")
    db = Database(db_path)
    db.init_schema()
    run_id = db.create_run(
        category="saas",
        competitors=["GenericSaaS"],
        goal="live-roundtrip-smoke-test",
    )
    print(f"[db] run_id: {run_id}\n")

    # ------------------------------------------------------------------
    # Step 3: Make ONE real call via call_llm with schema=True.
    # ------------------------------------------------------------------
    messages = [
        {
            "role": "user",
            "content": (
                'Return ONLY JSON of the form {"pricing":"<one short string>"} '
                "describing a generic SaaS Pro plan price. No prose."
            ),
        }
    ]

    print("[llm] sending live request to MiniMax …", flush=True)
    try:
        result = call_llm(
            db,
            run_id,
            agent="analyst",
            messages=messages,
            schema=True,
            settings=settings,
        )
    except Exception as exc:
        traceback.print_exc()
        print(f"\n{FAIL_PREFIX} — call_llm raised: {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 4: Confirm the returned value is a parsed dict.
    # ------------------------------------------------------------------
    result_repr = repr(result)
    if len(result_repr) > 200:
        result_repr = result_repr[:197] + "..."
    print(f"[llm] parsed result: {result_repr}")
    _assert(isinstance(result, dict), f"Expected dict from call_llm, got {type(result).__name__}")
    print("[llm] result is a dict — OK\n")

    # ------------------------------------------------------------------
    # Step 5: Read the llm_calls row and assert key fields are populated.
    # ------------------------------------------------------------------
    rows = db.llm_calls_for_run(run_id)
    _assert(len(rows) >= 1, f"Expected at least 1 llm_calls row, got {len(rows)}")

    # Use the LAST row (in case a repair retry added a second row).
    row = rows[-1]

    prompt_json = row.get("prompt_json") or ""
    output_text = row.get("output_text") or ""
    prompt_tokens = row.get("prompt_tokens")
    completion_tokens = row.get("completion_tokens")
    total_tokens = row.get("total_tokens")

    print(f"[db] llm_calls rows for run: {len(rows)}")
    print(f"[db] model           : {row.get('model')!r}")
    print(f"[db] prompt_tokens   : {prompt_tokens}")
    print(f"[db] completion_tokens: {completion_tokens}")
    print(f"[db] total_tokens    : {total_tokens}")
    print(f"[db] output_text len : {len(output_text)} chars")
    print(f"[db] prompt_json len : {len(prompt_json)} chars")

    # Validate prompt_json is parseable non-empty JSON.
    _assert(len(prompt_json) > 2, "prompt_json is empty")
    try:
        parsed_prompt = json.loads(prompt_json)
    except json.JSONDecodeError as exc:
        _assert(False, f"prompt_json is not valid JSON: {exc}")
    _assert(isinstance(parsed_prompt, list) and len(parsed_prompt) > 0,
            f"prompt_json should be a non-empty list, got: {prompt_json[:100]!r}")

    # Validate output_text is non-empty.
    _assert(len(output_text) > 0, "output_text is empty")

    # Validate total_tokens is a positive integer.
    if total_tokens is None:
        print(
            "\n[WARNING] total_tokens is NULL — MiniMax did not populate usage in the response. "
            "This is a real finding: token accounting is not available for this model/endpoint."
        )
        print(f"{FAIL_PREFIX} — total_tokens is NULL (no usage returned by MiniMax)")
        sys.exit(1)

    _assert(
        isinstance(total_tokens, int) and total_tokens > 0,
        f"total_tokens must be a positive integer, got {total_tokens!r}",
    )

    # ------------------------------------------------------------------
    # All checks passed.
    # ------------------------------------------------------------------
    print(f"\n{PASS}")
    print(f"  model      : {settings.minimax_model}")
    print(f"  base_url   : {settings.minimax_base_url}")
    print(f"  prompt_tokens     = {prompt_tokens}")
    print(f"  completion_tokens = {completion_tokens}")
    print(f"  total_tokens      = {total_tokens}")
    print(f"  parsed result     = {result_repr}")

    # Cleanup temp DB.
    try:
        os.unlink(db_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
