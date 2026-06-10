# Web Search

MingJing collects evidence from the open web through a **multi-engine** search
layer. The goal is coverage + graceful degradation: an engine that is missing a
key, rate-limited, or unreachable simply contributes nothing — the run continues
on whatever engines do respond.

> **China-network note.** Foreign engines (Tavily, Brave, DuckDuckGo, and a
> default SearXNG that aggregates Google/Bing) are throttled or blocked from a
> mainland-China network. If your demo runs from China, configure **博查 Bocha**
> and/or a **self-hosted SearXNG pointed at CN backends (Bing, Baidu)**. See
> `deploy/searxng/settings.yml`.

## Two code paths

There are two distinct paths, and they combine engines differently:

| Path | When | Engine combination |
|---|---|---|
| **Deep-collect** (`agents/collector.collect` with `engines=…`) | the live runner (real `POST /runs`) | **all** engines in the active depth tier run **concurrently**, results are **merged** then deduped/ranked. Order is cosmetic; missing-key engines return `[]`. |
| **Legacy chain** (`collector.search.search`) | the single-query helper / fallbacks | engines tried **in order**, **first non-empty wins** (`MINGJING_SEARCH_PROVIDER`). |

The depth tiers live in `config.py`:

| Tier | Engines |
|---|---|
| `quick` (default) | `bocha`, `tavily`, `searxng`, `duckduckgo` |
| `detailed` | `bocha`, `tavily`, `brave`, `searxng`, `duckduckgo` |

## Engines & keys

| Engine | Env var | Reachable from CN? | Notes |
|---|---|---|---|
| **博查 Bocha** | `BOCHA_API_KEY` | ✅ yes | Recommended CN primary. Key: <https://open.bochaai.com/> |
| **Tavily** | `TAVILY_API_KEY` | ⚠️ throttled/blocked | Agent-grade, free 1000/mo. Best on overseas/VPN. |
| **Brave** | `BRAVE_API_KEY` | ⚠️ throttled/blocked | Free 2000/mo. `detailed` tier only. |
| **SearXNG** | `MINGJING_SEARXNG_URL` | ✅ if CN-configured | Keyless local aggregator — see below. |
| **DuckDuckGo** | — | ❌ usually empty | Keyless last resort; the upstream lib is deprecated and frequently returns 0 results. Do not rely on it alone. |

Set at least one engine reachable from your demo network. With no engine
configured, live search returns **zero** sources and the pipeline falls back to
the cached corpus only.

## SearXNG — two ways to deploy

SearXNG is keyless. The collector calls `/search?format=json`, which requires
**`search.formats: [html, json]`** and **`server.limiter: false`** (otherwise the
JSON API returns HTTP 403). Both are set in `deploy/searxng/settings.yml`.

### Layer 1 — self-contained (recommended, scoped to MingJing)

Host port **8888** is used (8080 is commonly taken):

```bash
cd mingjing/deploy/searxng
docker compose up -d
# verify JSON API (expect a non-empty results array):
curl -s 'http://localhost:8888/search?q=notion+pricing&format=json' | head -c 400
```

Then in `.env`:

```bash
MINGJING_SEARXNG_URL=http://localhost:8888
```

### Layer 2 — reuse your existing Local Deep Research (LDR) SearXNG

LDR (`~/cli/local-deep-research/docker-compose.yml`) already ships a `searxng`
service, but it's only published on the **internal docker network**
(`http://searxng:8080`), so the host can't reach it. To reuse it, add a
`docker-compose.override.yml` in the LDR dir that exposes a host port and mounts
a JSON-enabled settings file:

```yaml
services:
  searxng:
    ports:
      - "8888:8080"
    volumes:
      - /home/lingxufeng/Langgraph/mingjing/deploy/searxng/settings.yml:/etc/searxng/settings.yml:ro
```

then `docker compose up -d searxng` and set `MINGJING_SEARXNG_URL=http://localhost:8888`.

Either layer satisfies the same `MINGJING_SEARXNG_URL` contract — pick one.

## Verifying search works

```bash
set -a; . ./.env; set +a
uv run python -c "from mingjing.collector.search import search; \
print(len(search('Notion pricing plans', max_results=5)))"
```

A healthy setup prints a non-zero count. `0` means no engine is reachable/keyed.
