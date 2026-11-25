from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import Result

from migrate_guard import allows
from migrate_guard.config import Config, ConfigAllow, MigrateGuardError
from migrate_guard.ir import Allow, Finding, SourceSpan

PATH = "db/migrations/0001_test.sql"


def finding(code: str, line: int, path: str = PATH, severity: str = "error") -> Finding:
    return Finding(
        code=code,
        severity=severity,
        span=SourceSpan(file=path, line=line),
        message="m",
        safe_alternative="s",
        statement="x",
    )


def inline(codes: tuple[str, ...], line: int, reason: str = "approved OPS-1") -> Allow:
    return Allow(codes=codes, reason=reason, span=SourceSpan(file=PATH, line=line), source="inline")


# Parsing


@pytest.mark.parametrize(
    ("fmt", "line"),
    [
        ("sql", '-- migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"'),
        ("sql", '   --migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"  '),
        ("laravel", '// migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"'),
        ("laravel", '# migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"'),
        ("django", '    # migrate-guard: allow MG004 reason="audit_legacy retired, OPS-1123"'),
    ],
)
def test_parse_accepts_each_comment_style(fmt: str, line: str) -> None:
    [allow] = allows.parse_inline(PATH, f"\n{line}\nDROP TABLE audit_legacy;\n", fmt)
    assert allow.codes == ("MG004",)
    assert allow.reason == "audit_legacy retired, OPS-1123"
    assert allow.span == SourceSpan(file=PATH, line=2)
    assert allow.source == "inline"


def test_parse_reads_several_codes() -> None:
    text = '# migrate-guard: allow MG004, MG008 reason="removed together, OPS-991"\n'
    [allow] = allows.parse_inline("app/migrations/0002_x.py", text, "django")
    assert allow.codes == ("MG004", "MG008")


def test_parse_ignores_other_comments_and_foreign_markers() -> None:
    text = (
        "-- an ordinary comment that mentions migrate-guard\n"
        "SELECT 1; -- trailing note\n"
        '// migrate-guard: allow MG004 reason="not a SQL comment"\n'
    )
    assert allows.parse_inline(PATH, text, "sql") == ()


def test_parse_strips_padding_around_the_reason() -> None:
    text = '-- migrate-guard: allow MG004 reason="  audit_legacy retired  "\n'
    [allow] = allows.parse_inline(PATH, text, "sql")
    assert allow.reason == "audit_legacy retired"


def test_parse_finds_nothing_for_an_unknown_format() -> None:
    text = '-- migrate-guard: allow MG004 reason="x"\n# migrate-guard: allow MG004 reason="x"\n'
    assert allows.parse_inline(PATH, text, "yaml") == ()


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("-- migrate-guard: allow MG004", "allow comment at db/migrations/0001_test.sql:1 has no"),
        ('-- migrate-guard: allow MG004 reason=""', "has no reason"),
        ('-- migrate-guard: allow MG004 reason="   "', "has no reason"),
        ('-- migrate-guard: allow MG999 reason="x"', 'unknown rule code "MG999"'),
        ('-- migrate-guard: allow mg004 reason="x"', 'unknown rule code "mg004"'),
        ("-- migrate-guard: allow MG004 reason=x", "cannot parse the reason"),
        ('-- migrate-guard: alow MG004 reason="x"', "cannot parse the migrate-guard comment"),
        ("-- migrate-guard: allow", "cannot parse the migrate-guard comment"),
    ],
)
def test_parse_rejects_malformed_allows(line: str, message: str) -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        allows.parse_inline(PATH, f"{line}\nDROP TABLE t;\n", "sql")
    assert message in excinfo.value.message
    assert f"{PATH}:1" in excinfo.value.message


# Applying


def test_inline_allow_waives_the_next_flagged_operation_only() -> None:
    findings = [finding("MG004", 3), finding("MG004", 7)]
    warnings: list[str] = []
    result = allows.apply(findings, PATH, [inline(("MG004",), 2)], Config("postgres"), warnings)

    assert [f.allowed for f in result] == [True, False]
    assert result[0].allow_reason == "approved OPS-1"
    assert warnings == []


def test_inline_allow_only_waives_listed_codes_at_the_target_line() -> None:
    findings = [finding("MG001", 4), finding("MG004", 4), finding("MG004", 9)]
    result = allows.apply(findings, PATH, [inline(("MG004",), 3)], Config("postgres"), [])

    assert [(f.code, f.span.line, f.allowed) for f in result] == [
        ("MG001", 4, False),
        ("MG004", 4, True),
        ("MG004", 9, False),
    ]


def test_inline_allow_never_reaches_backwards() -> None:
    warnings: list[str] = []
    result = allows.apply(
        [finding("MG004", 2)], PATH, [inline(("MG004",), 5)], Config("postgres"), warnings
    )

    assert not result[0].allowed
    assert warnings == [f"allow comment at {PATH}:5 matches no finding"]


def test_two_allows_cover_two_operations() -> None:
    findings = [finding("MG004", 2), finding("MG004", 4)]
    result = allows.apply(
        findings,
        PATH,
        [inline(("MG004",), 1, "first"), inline(("MG004",), 3, "second")],
        Config("postgres"),
        [],
    )

    assert [f.allow_reason for f in result] == ["first", "second"]


def test_ignored_codes_are_dropped() -> None:
    findings = [finding("MG009", 1, severity="warning"), finding("MG002", 2)]
    result = allows.apply(findings, PATH, [], Config("mysql", ignore=("MG009",)), [])

    assert [f.code for f in result] == ["MG002"]


def test_config_allow_waives_listed_codes_in_its_file() -> None:
    config = Config(
        "postgres",
        allow=(ConfigAllow(file=PATH, rules=("MG004",), reason="legacy cleanup, OPS-7"),),
    )
    findings = [finding("MG004", 2), finding("MG004", 8), finding("MG002", 5)]
    warnings: list[str] = []
    result = allows.apply(findings, f"./{PATH}", [], config, warnings)

    assert [(f.code, f.allowed) for f in result] == [
        ("MG004", True),
        ("MG004", True),
        ("MG002", False),
    ]
    assert result[0].allow_reason == "legacy cleanup, OPS-7"
    assert warnings == []


def test_config_allow_for_another_file_does_nothing() -> None:
    config = Config(
        "postgres",
        allow=(ConfigAllow(file="db/migrations/other.sql", rules=("MG004",), reason="r"),),
    )
    warnings: list[str] = []
    result = allows.apply([finding("MG004", 2)], PATH, [], config, warnings)

    assert not result[0].allowed
    assert warnings == []


def test_unused_config_allow_for_a_checked_file_warns() -> None:
    config = Config("postgres", allow=(ConfigAllow(file=PATH, rules=("MG005",), reason="r"),))
    warnings: list[str] = []
    allows.apply([finding("MG004", 2)], PATH, [], config, warnings)

    assert warnings == [f"config allow for {PATH} (MG005) matches no finding"]


def test_inline_allow_wins_over_config_allow() -> None:
    config = Config("postgres", allow=(ConfigAllow(file=PATH, rules=("MG004",), reason="cfg"),))
    result = allows.apply([finding("MG004", 2)], PATH, [inline(("MG004",), 1, "site")], config, [])

    assert result[0].allow_reason == "site"


# End to end through the CLI


def test_an_inline_allow_turns_a_failing_drop_into_a_pass(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    migration = tmp_path / "0100_drop.sql"
    migration.write_text(
        '-- migrate-guard: allow MG004 reason="audit_legacy retired 2026-06, OPS-1123"\n'
        "DROP TABLE audit_legacy;\n",
        encoding="utf-8",
    )
    result = run_cli("check", str(migration), "--dialect", "postgres")

    assert result.exit_code == 0
    assert "MG004" in result.stdout
    assert 'allowed: "audit_legacy retired 2026-06, OPS-1123"' in result.stdout
    assert "1 allowed" in result.stdout
    assert "verdict: PASS" in result.stdout
    assert result.stderr == ""


def test_a_malformed_inline_allow_exits_2_with_empty_stdout(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    migration = tmp_path / "0100_drop.sql"
    migration.write_text(
        "-- migrate-guard: allow MG004\nDROP TABLE audit_legacy;\n", encoding="utf-8"
    )
    result = run_cli("check", str(migration), "--dialect", "postgres")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == (
        f"error: allow comment at {migration}:1 has no reason\n"
        'add reason="..." with a short justification to the allow comment\n'
    )


def test_a_stale_inline_allow_warns_on_stderr(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    migration = tmp_path / "0100_safe.sql"
    migration.write_text(
        '-- migrate-guard: allow MG004 reason="left over"\nCREATE TABLE t (id int);\n',
        encoding="utf-8",
    )
    result = run_cli("check", str(migration), "--dialect", "postgres")

    assert result.exit_code == 0
    assert result.stderr == f"warning: allow comment at {migration}:1 matches no finding\n"
    assert "no problems found" in result.stdout


def test_config_allow_and_ignore_are_applied(
    run_cli: Callable[..., Result], tmp_path: Path
) -> None:
    migration = tmp_path / "0100_drop.sql"
    migration.write_text(
        "CREATE INDEX users_email_idx ON users (email);\nDROP TABLE audit_legacy;\n",
        encoding="utf-8",
    )
    config = tmp_path / ".migrateguard.toml"
    config.write_text(
        "[migrate-guard]\n"
        'dialect = "postgres"\n'
        'ignore = ["MG002"]\n'
        "[[migrate-guard.allow]]\n"
        f'file = "{migration}"\n'
        'rules = ["MG004"]\n'
        'reason = "retired, OPS-1123"\n',
        encoding="utf-8",
    )
    result = run_cli("check", str(migration), "--config", str(config))

    assert result.exit_code == 0
    assert "MG002" not in result.stdout
    assert 'allowed: "retired, OPS-1123"' in result.stdout
    assert "1 finding: 0 errors (0 gating), 0 warnings, 1 allowed" in result.stdout
