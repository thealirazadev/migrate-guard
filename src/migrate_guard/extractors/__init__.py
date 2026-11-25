"""Format-specific extractors. Each turns file text into the shared IR.

No extractor ever imports, evaluates, or executes the content it scans.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Finding, Operation


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Everything one file contributes to a run. Inline allows are parsed by `allows.py`."""

    operations: tuple[Operation, ...] = ()
    diagnostics: tuple[Finding, ...] = ()
    statement_count: int = 0
