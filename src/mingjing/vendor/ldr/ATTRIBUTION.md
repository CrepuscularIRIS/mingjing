# Vendoring / LLM-integration decision record (D0 spikes, 2026-05-30)

## LDR import-closure spike (Task 1 step 3)
**Decision: DO NOT vendor heavy `local-deep-research` modules.** Use a thin
`requests` + `BeautifulSoup` `_live_fetch` and a small built-in `is_safe_url`
SSRF guard (see `collector/fetch.py`). LDR's `ContentFetcher` drags a large
transitive closure (sqlalchemy/flask/crawl4ai); vendoring it is not worth the
risk for an 11-day demo slice. The eng review confirmed the provider/fetcher
abstractions were not load-bearing. 88 backend tests pass on the thin path.

No LDR source is vendored here; this file documents the deliberate choice.

## MiniMax LLM protocol spike (Task 1 step 1)
Key in `.env` authenticates against MiniMax **international** (`api.minimaxi.com`),
model **`MiniMax-M2.7`**. All three surfaces return 200 with the same key:
OpenAI-compatible `/v1/chat/completions`, Anthropic `/anthropic/v1/messages`,
native `/v1/text/chatcompletion_v2`.

**Decisions for the MingJing backend:**
1. Use the **OpenAI SDK** against `base_url="https://api.minimaxi.com/v1"`.
   Do NOT inherit the `.env` `MINIMAX_BASE_URL` (it is the `/anthropic` variant,
   used by other tooling). Config uses a MingJing-owned base-url default.
2. **Native function-calling works** (`tools=` -> `tool_calls`, clean JSON args,
   `finish_reason="tool_calls"`). Agent structured output uses tool-calls;
   `parse_json_with_repair` is the fallback path.
3. `MiniMax-M2.7` is a **reasoning model**: it emits `<think>...</think>` inline
   in `content`, and `response_format={"type":"json_object"}` does NOT suppress
   it. `parse_json_with_repair` MUST strip `<think>...</think>` before extracting
   the first balanced JSON span (otherwise it captures JSON quoted inside the
   reasoning). Tool-calls avoid this entirely.

## Outbound-web spike (Task 1 step 2)
`https://duckduckgo.com` reachable (HTTP 200) from the build environment.
Live-first mode is viable; cache_first remains the D0 auto-downgrade.
