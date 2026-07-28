"""The Rule protocol every rule module implements.

A rule is pure: it sees one operation, the whole file's operation list for
same-file lookback, and the config. It never reads files and never decides exit
codes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..config import Config
from ..ir import Finding, Operation


@runtime_checkable
class Rule(Protocol):
    code: str
    severity: str
    dialects: tuple[str, ...]
    summary: str
    explanation: str

    def check(
        self,
        op: Operation,
        file_ops: Sequence[Operation],
        index: int,
        config: Config,
    ) -> Finding | None: ...
