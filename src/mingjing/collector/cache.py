"""Minimal sqlite-backed READ cache for fetched pages.

This is the real fallback source behind :func:`mingjing.collector.fetch.fetch_with_fallback`
and the store the demo pre-warm (Task 16) populates. It is intentionally tiny: a
single ``cached_pages`` table keyed by URL, opened in WAL mode like the main DB.

A :class:`Cache` exposes the ``get(url) -> FetchResult | None`` interface that
``fetch_with_fallback`` consumes, plus a ``put`` upsert. A page served from this
cache is always tagged ``source_mode="CACHED"`` so the provenance badge is honest
about where the text came from.
"""

import sqlite3
import threading

from .fetch import FetchResult

# Single global write lock — mirrors the main DB's single-writer discipline so a
# pre-warm writer and concurrent readers never corrupt the file.
_WRITE_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_pages (
    url TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    content_hash TEXT,
    fetched_at REAL,
    source_mode TEXT
);
"""


class Cache:
    """A sqlite read cache of fetched pages, keyed by URL."""

    def __init__(self, path: str) -> None:
        """Open (or create) the cache file at ``path`` and ensure the schema.

        Args:
            path: Filesystem path to the sqlite cache file (separate from the
                main run DB).
        """
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        with _WRITE_LOCK:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def put(self, result: "FetchResult") -> None:
        """Upsert a fetched page by URL.

        The stored ``source_mode`` is recorded as supplied; reads always re-tag
        the served result as ``CACHED`` (see :meth:`get`).

        Args:
            result: The :class:`FetchResult` to cache.
        """
        with _WRITE_LOCK:
            self._conn.execute(
                "INSERT INTO cached_pages (url, text, content_hash, fetched_at, source_mode)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(url) DO UPDATE SET"
                " text=excluded.text, content_hash=excluded.content_hash,"
                " fetched_at=excluded.fetched_at, source_mode=excluded.source_mode",
                (
                    result.url,
                    result.text,
                    result.content_hash,
                    result.fetched_at,
                    result.source_mode,
                ),
            )
            self._conn.commit()

    def get(self, url: str) -> "FetchResult | None":
        """Return the cached page for ``url`` tagged ``CACHED``, or ``None`` on miss.

        Args:
            url: The page URL to look up.

        Returns:
            A :class:`FetchResult` with ``source_mode="CACHED"`` when present,
            otherwise ``None``.
        """
        # Read under the same single lock that guards put()/__init__ — the shared
        # connection has one cursor state, so concurrent read+write must serialize
        # for read-consistency under the module's single-lock discipline.
        with _WRITE_LOCK:
            cur = self._conn.execute(
                "SELECT url, text, content_hash, fetched_at FROM cached_pages WHERE url = ?",
                (url,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return FetchResult(
            text=row["text"],
            url=row["url"],
            source_mode="CACHED",
            fetched_at=row["fetched_at"],
            content_hash=row["content_hash"] or "",
        )

    def close(self) -> None:
        """Close the underlying sqlite connection."""
        self._conn.close()

    def __enter__(self) -> "Cache":
        """Enter a ``with Cache(path) as c:`` block, returning the cache."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the connection on block exit so WAL ``-wal``/``-shm`` sidecars
        don't leak past the caller's scope."""
        self.close()
