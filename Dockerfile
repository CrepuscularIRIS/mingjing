# MingJing backend — FastAPI evidence-admissible runtime.
#
# Boots in cache_first mode (NO API key needed). For live web + LLM runs, pass
# MINIMAX_API_KEY and set MINGJING_MODE=live_first (see .env.example).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    MINGJING_MODE=cache_first \
    MINGJING_DB=/app/data/mingjing.db \
    MINGJING_CACHE_DB=/app/data/cache/cache.db

WORKDIR /app

# uv: fast, lockfile-reproducible installs.
RUN pip install --no-cache-dir uv

# Dependency layer (cached): resolve from the committed lockfile.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# App source + demo corpus + schemas.
COPY . .
RUN mkdir -p /app/data/cache

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "mingjing.api:app", "--host", "0.0.0.0", "--port", "8000"]
