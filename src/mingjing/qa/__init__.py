"""QA subpackage: pure verifier rules and the pure router."""

from .route import route
from .rules import Issue, qa_check

__all__ = ["route", "qa_check", "Issue"]
