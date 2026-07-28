"""Rule registry: rule code to Rule, populated at import time and never mutated."""

from __future__ import annotations

from . import mg001, mg002, mg003, mg004, mg005, mg006, mg007
from .base import Rule

REGISTRY: tuple[Rule, ...] = (
    mg001.RULE,
    mg002.RULE,
    mg003.RULE,
    mg004.RULE,
    mg005.RULE,
    mg006.RULE,
    mg007.RULE,
)


def rules_for(dialect: str) -> tuple[Rule, ...]:
    """The registered rules that apply to a dialect, in stable code order."""
    return tuple(rule for rule in REGISTRY if dialect in rule.dialects)


def get_rule(code: str) -> Rule | None:
    for rule in REGISTRY:
        if rule.code == code:
            return rule
    return None
