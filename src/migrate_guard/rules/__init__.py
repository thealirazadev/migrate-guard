"""Rule registry: rule code to Rule, populated at import time and never mutated."""

from __future__ import annotations

from .base import Rule

REGISTRY: tuple[Rule, ...] = ()


def rules_for(dialect: str) -> tuple[Rule, ...]:
    """The registered rules that apply to a dialect, in stable code order."""
    return tuple(rule for rule in REGISTRY if dialect in rule.dialects)


def get_rule(code: str) -> Rule | None:
    for rule in REGISTRY:
        if rule.code == code:
            return rule
    return None
