# Deployment — MingJing Evidence Runtime

## Environment variables

All settings are read by `config.py:Settings.load()` from the process environment
(load with `python-dotenv` or set directly). Missing variables fall back to the
defaults shown.

| Variable | Required | Default | Description |
|---|---|---|---|
| `MINIMAX_API_KEY` | yes (live runs) | `""` | MiniMax API key. Set in `.env`, never commit. |
| `MINGJING_LLM_BASE_URL` | no | `https://api.minimaxi.com/v1` | MiniMax international OpenAI-compatible endpoint. Do NOT use the `.env` `MINIMAX_BASE_URL` (that is the `/anthropic` variant used by other tooling). |
| `MINIMAX_MODEL` | no | `MiniMax-M2.7` | Model name passed to the OpenAI SDK. |
| `MINGJING_MODE` | no | `live_first` | `live_first` or `cache_first`. Set to `cache_first` for the D0 auto-downgrade (offline-safe demo). |
| `MINGJING_RATE_LIMITING_ENABLED` | **startup assert** | `true` | Must be `"true"` or startup raises `ValueError`. The vendored `AdaptiveRateLimitTracker` silently no-ops if this is false; refusing to start is safer. |
| `MINGJING_DB` | no | `data/mingjing.db` | Live run SQLite file path. |
| `MINGJING_CACHE_DB` | no | `data/cache/cache.db` | Read-only demo cache store path. |
| `MINGJING_SOURCE_CAP` | no | `3` | Max live sources fetched per field per round. |
| `MINGJING_FETCH_TIMEOUT` | no | `8` | Per-URL fetch timeout in seconds. |
| `MINGJING_REVISE_CAP` | no | `2` | Max QA revision rounds before honest partial. |
| `MINGJING_BUDGET_CALLS` | no | `40` | Max cumulative LLM + fetch calls per run. |

### Sample `.env`

```bash
# Copy .env.example and fill in:
MINIMAX_API_KEY=<your-key-here>
MINGJING_LLM_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL=MiniMax-M2.7
MINGJING_RATE_LIMITING_ENABLED=true
MINGJING_MODE=live_first
```

---

## Running live vs cache-first

### Live-first (default)

```bash
uv run uvicorn mingjing.api:app --reload --port 8000
# or:
make api
```

The Collector attempts real fetches. On timeout, HTTP 4xx/5xx, or any exception,
it falls back to the read-only cache (`MINGJING_CACHE_DB`) and tags the source
`CACHED`. The provenance badge in the frontend makes this fallback visible.

### Cache-first (offline demo / D0 auto-downgrade)

```bash
MINGJING_MODE=cache_first make api
```

The Collector reads the cache first. Only if the cache misses does it attempt a
live fetch. Use this if the venue network blocks outbound web, or if you want a
fully stable offline demo. The frontend badge shows `CACHED` for all sources.

### Pre-warm (recommended before demo)

```python
from mingjing.prewarm import prewarm_all
prewarm_all(
    competitors=["CompetitorA", "CompetitorB"],
    fields=["pricing_model", "user_sentiment", "feature_tree", "user_persona", "swot"],
    cache=cache_store,
    max_workers=4,
    url_for=your_url_resolver,   # inject the real URL map
)
```

Run pre-warm at demo start (before the judge picks a competitor) so the first
live run hits warm compute. Individual URL failures are captured in
`result["errors"]` and never abort the whole warm-up.

---

## Rate limiting

The runtime enforces `MINGJING_RATE_LIMITING_ENABLED=true` at startup. This
ensures the vendored `AdaptiveRateLimitTracker` is active (it silently does
nothing when disabled). Rate-limit sleeps are in the fetch/LLM path and
**count against the 6-minute demo wall-clock** — keep `MINGJING_SOURCE_CAP` and
`MINGJING_BUDGET_CALLS` within the timing budget confirmed during dry-runs.

---

## SSRF and robots posture

### SSRF guard (`collector/fetch.py:is_safe_url`)

Applied to every URL before any live fetch, **and re-applied at every redirect
hop** (redirects are followed manually for this reason). Blocks:

- Non-`http`/`https` schemes
- Non-standard ports (only 80, 443, None allowed)
- Loopback, private, link-local, reserved, multicast, unspecified IP ranges
- Cloud metadata endpoints: `169.254.169.254`, `100.100.100.200`,
  `fd00:ec2::254`, and hostname aliases `metadata.google.internal`,
  `metadata`, `instance-data`

**Accepted caveat:** a residual DNS-rebinding TOCTOU exists — the guard resolves
the hostname at check time, then `requests` resolves it again to connect. A
fast-rebinding attack could route the second resolution to a private IP. This is
accepted for the demo because fetch targets come from an allowlisted
competitor/search set, not arbitrary user input. IP-pinning is future work for
arbitrary-URL deployments.

### Robots gate (`collector/robots.py`)

`robots.is_allowed(url, fetch_robots)` is called before every fetch. Disallowed
URLs are recorded as `skipped_robots` in the source dict (`"fetched": False,
"reason": "skipped_robots"`) and **never fetched**. Robots responses are cached
per domain with a short TTL (not sticky-fail-open) to avoid fetching `robots.txt`
on every request.

### PII anonymization (survey/interview ingest)

`ingest.anonymize_respondent_meta()` is applied recursively to every respondent /
speaker metadata dict before it reaches the DB. It drops identity-named keys
(name, email, phone, mobile, contact, etc.) at every nesting level, and redacts
email and phone patterns from surviving string values. Known limitation: free-text
name tokens in answer/segment content are not removed (NER would be required).

---

## Frontend

```bash
cd frontend && npm install   # first time only
npm run dev                  # Vite dev server on http://localhost:5173
npm run build                # production build to dist/
```

Or via Make:

```bash
make web         # dev server
make web-build   # production build
```

CORS is configured permissively for any `localhost:<port>` origin (Vite dev
server runs on a different port than the API). No CDN: all JS/CSS is local.

---

## Health check

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```
