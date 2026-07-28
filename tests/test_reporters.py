from __future__ import annotations

from collections.abc import Callable

from click.testing import Result
from conftest import SQL_UNSAFE

from migrate_guard.config import Config
from migrate_guard.ir import Finding, SourceSpan
from migrate_guard.reporters import text

POSTGRES = Config(dialect="postgres")


def finding(
    code: str = "MG002",
    severity: str = "error",
    line: int = 7,
    allowed: bool = False,
    reason: str | None = None,
) -> Finding:
    return Finding(
        code=code,
        severity=severity,
        span=SourceSpan("db/migrations/0042_add_email_index.sql", line),
        table="users",
        message="CREATE INDEX without CONCURRENTLY blocks all writes to users.",
        safe_alternative="CREATE INDEX CONCURRENTLY users_email_idx ON users (email);",
        statement="CREATE INDEX users_email_idx ON users (email)",
        allowed=allowed,
        allow_reason=reason,
    )


def test_report_matches_the_golden_file(
    run_cli: Callable[..., Result], golden: Callable[[str], str]
) -> None:
    result = run_cli("check", SQL_UNSAFE, "--dialect", "postgres")

    assert result.stdout == golden("sql_unsafe_text.txt")


def test_findings_render_with_statement_and_fix() -> None:
    report = text.render([finding()], 1, 1, POSTGRES)

    assert report.splitlines()[0] == "db/migrations/0042_add_email_index.sql"
    assert report.splitlines()[1].startswith("  7  MG002  error    CREATE INDEX")
    assert "                     statement: CREATE INDEX users_email_idx" in report
    assert "                     fix: CREATE INDEX CONCURRENTLY" in report
    assert "1 finding: 1 error (1 gating), 0 warnings, 0 allowed" in report
    assert report.endswith("verdict: FAIL (fail_on = error)\n")


def test_allowed_findings_show_the_reason_instead_of_a_fix() -> None:
    report = text.render([finding(allowed=True, reason="retired 2026-06")], 1, 1, POSTGRES)

    assert '                     allowed: "retired 2026-06"' in report
    assert "fix:" not in report
    assert "1 finding: 0 errors (0 gating), 0 warnings, 1 allowed" in report
    assert "verdict: PASS (fail_on = error)" in report


def test_clean_run_reports_counts_and_passes() -> None:
    report = text.render([], 2, 5, POSTGRES)

    assert (
        report
        == "no problems found\nchecked 2 files, 5 statements\nverdict: PASS (fail_on = error)\n"
    )


def test_empty_file_set_is_reported_and_passes() -> None:
    report = text.render([], 0, 0, POSTGRES)

    assert report == "no migration files to check\nverdict: PASS (fail_on = error)\n"


def test_warnings_gate_only_under_fail_on_warning() -> None:
    warning = finding(code="MG000", severity="warning")

    assert "verdict: PASS" in text.render([warning], 1, 1, POSTGRES)
    assert "verdict: FAIL (fail_on = warning)" in text.render(
        [warning], 1, 1, Config(dialect="postgres", fail_on="warning")
    )


def test_color_is_opt_in_and_never_the_only_signal() -> None:
    plain = text.render([finding()], 1, 1, POSTGRES, color=False)
    painted = text.render([finding()], 1, 1, POSTGRES, color=True)

    assert "\033[" not in plain
    assert "\033[31mFAIL\033[0m" in painted
    assert "error" in plain and "FAIL" in plain


def test_summarize_separates_allowed_from_gating() -> None:
    counts = text.summarize(
        [finding(), finding(code="MG000", severity="warning"), finding(allowed=True, reason="ok")],
        "error",
    )

    assert counts == {"total": 3, "error": 1, "warning": 1, "allowed": 1, "gating": 1}
