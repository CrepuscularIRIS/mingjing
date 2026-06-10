# MingJing evidence-runtime — top-level Makefile
#
# All Python targets use `uv run` so the correct project virtualenv is always
# activated.  No global activation or PATH manipulation needed.
#
# Quick reference (make help):
#   setup         — install Python deps (uv sync) + frontend npm deps
#   test          — run the full offline test suite (no key needed)
#   test-slow     — run only the @pytest.mark.slow tests (end-to-end graph loops)
#   api           — start the FastAPI dev server on port 8000
#   web           — start the frontend dev server (Vite, port 5173)
#   web-build     — production build of the frontend (tsc + vite build)
#   demo          — convenience alias for demo-timing
#   demo-timing   — run the offline/live wall-clock timing harness

.PHONY: setup test test-slow api web web-build demo demo-timing demo-reliable record-demo help

# Install Python deps and frontend npm deps (run once after cloning).
setup:
	uv sync
	cd frontend && npm install

# Print this help.
help:
	@grep -E '^[a-zA-Z_-]+:' Makefile | grep -v '^\.PHONY' | sed 's/:.*$$//' | \
	  while read t; do \
	    desc=$$(grep -A1 "^# " Makefile | grep -B1 "^$$t:" | head -1 | sed 's/^# //'); \
	    printf "  %-14s %s\n" "$$t" "$$desc"; \
	  done

# Run the full offline test suite.
test:
	uv run pytest -q

# Run only the slow (end-to-end loop) tests with verbose output.
test-slow:
	uv run pytest -m slow -v

# Start the FastAPI dev server.
# Loads ./.env (if present) so Settings.load() sees MINGJING_* / MINIMAX_* vars,
# matching the README quickstart (copy .env.example -> .env).
api:
	set -a; [ -f .env ] && . ./.env; set +a; uv run uvicorn mingjing.api:app --reload --port 8000

# Start the frontend dev server (Vite, port 5173).
web:
	cd frontend && npm run dev

# Build the frontend for production (tsc + vite build).
web-build:
	cd frontend && npm run build

# Convenience alias — runs the timing harness.
demo: demo-timing

# Run the wall-clock timing harness (offline by default; set
# MINGJING_TIMING_LIVE=1 for the live path — requires MINIMAX_API_KEY).
demo-timing:
	uv run python scripts/demo_timing.py

# Drive one deterministic demo run (curated corpus + real LLM, cache_first) into
# the shared DB, then view via `make api` + `make web`. Requires MINIMAX_API_KEY.
demo-reliable:
	set -a; [ -f .env ] && . ./.env; set +a; MINGJING_MODE=cache_first uv run python scripts/run_demo.py $(COMPETITOR)

# Record the 6-minute money-shot demo (video + per-beat PNGs) into
# frontend/e2e/recordings/. Prereq: the app is already up (make api + make web)
# with demo data seeded (make demo-reliable). MJ_BASE overrides the URL.
record-demo:
	cd frontend && node e2e/record-money-shot.mjs
