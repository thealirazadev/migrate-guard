"""Rule registry: rule code to Rule, populated at import time and never mutated."""

from __future__ import annotations

from dataclasses import dataclass

from . import mg000, mg001, mg002, mg003, mg004, mg005, mg006, mg007, mg008, mg009
from .base import Rule

REGISTRY: tuple[Rule, ...] = (
    mg001.RULE,
    mg002.RULE,
    mg003.RULE,
    mg004.RULE,
    mg005.RULE,
    mg006.RULE,
    mg007.RULE,
    mg008.RULE,
    mg009.RULE,
)


def rules_for(dialect: str) -> tuple[Rule, ...]:
    """The registered rules that apply to a dialect, in stable code order."""
    return tuple(rule for rule in REGISTRY if dialect in rule.dialects)


@dataclass(frozen=True, slots=True)
class RuleInfo:
    """One row of the documented catalog. MG000 is a diagnostic, not a Rule, so the
    `rules` and `explain` commands read this view instead of the registry."""

    code: str
    severity: str
    dialects: tuple[str, ...]
    summary: str
    explanation: str


def catalog() -> tuple[RuleInfo, ...]:
    """Every documented code including MG000, ordered by code."""
    entries = [
        RuleInfo(
            code=mg000.CODE,
            severity=mg000.SEVERITY,
            dialects=mg000.DIALECTS,
            summary=mg000.SUMMARY,
            explanation=mg000.EXPLANATION,
        )
    ]
    entries.extend(
        RuleInfo(
            code=rule.code,
            severity=rule.severity,
            dialects=rule.dialects,
            summary=rule.summary,
            explanation=rule.explanation,
        )
        for rule in REGISTRY
    )
    return tuple(sorted(entries, key=lambda entry: entry.code))


def find(code: str) -> RuleInfo | None:
    for entry in catalog():
        if entry.code == code:
            return entry
    return None
