"""Pytest config: ensure the repo root is importable so ``scripts.*`` resolves.

The audit tool ``scripts/audit_verbatim.py`` lives at the repo root (outside the
``src/`` package) and is imported by ``tests/test_audit_verbatim.py``. Prepending
the repo root to ``sys.path`` makes ``import scripts.audit_verbatim`` work
regardless of how pytest is invoked, without touching ``pyproject.toml``.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
