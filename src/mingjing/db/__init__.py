"""SQLite source-of-truth layer (assembled from per-table mixins).

The ``Database`` class is composed via the MIXIN pattern from a small base
(:class:`mingjing.db._base._BaseDatabase`, holding the connection, schema, and
migrations) plus one mixin per table group. Every module shares the ONE canonical
``_WRITE_LOCK`` defined in :mod:`mingjing.db._base`, so the single-writer
discipline holds across the whole class regardless of which mixin a method lives
in.

Public API is unchanged: ``from mingjing.db import Database`` works exactly as it
did when this was a single module.
"""

from ._base import _BaseDatabase
from ._claims import ClaimMixin
from ._runs import RunMixin
from ._sources import SourcesEvidenceMixin
from ._trace import TraceLlmSynthesisMixin


class Database(
    _BaseDatabase,
    RunMixin,
    ClaimMixin,
    SourcesEvidenceMixin,
    TraceLlmSynthesisMixin,
):
    """Thin wrapper around a single shared sqlite3 connection.

    Assembled from :class:`_BaseDatabase` and the per-table mixins; see the
    individual mixin modules for the method-level documentation.
    """


__all__ = ["Database"]
