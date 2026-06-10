"""The four MingJing agents: Collector, Analyst, QA, Writer.

Collector/Analyst/QA are thin orchestration over the already-tested primitives
(search/robots/fetch, llm, qa.rules/scoring). Writer is a PURE deterministic
projection of QA-passed claims (the only unit-tested agent path).
"""

from .qa import review as qa_review
from .writer import Report, render_report

__all__ = [
    "Report",
    "render_report",
    "qa_review",
]
