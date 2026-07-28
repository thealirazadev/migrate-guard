"""Format-specific extractors. Each turns file text into the shared IR.

No extractor ever imports, evaluates, or executes the content it scans.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Allow, Finding, Operation


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Everything one file contributes to a run."""

    operations: tuple[Operation, ...] = ()
    allows: tuple[Allow, ...] = ()
    diagnostics: tuple[Finding, ...] = ()
    statement_count: int = 0
