"""Loading and strict validation of .migrateguard.toml.

Anything wrong in the configuration aborts the run with exit 2 rather than being
guessed at: a lint gate whose settings silently drift is worse than no gate.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILENAME = ".migrateguard.toml"
ROOT_TABLE = "migrate-guard"

DIALECTS = ("postgres", "mysql")
FAIL_ON_VALUES = ("error", "warning")
TOP_LEVEL_KEYS = ("dialect", "postgres_version", "paths", "ignore", "fail_on", "allow")
ALLOW_KEYS = ("file", "rules", "reason")
NEVER_IGNORABLE = ("MG000", "MG004")

CODE_PATTERN = re.compile(r"^MG\d{3}$")


class MigrateGuardError(Exception):
    """An environment or configuration problem: exit 2 with a one-line message."""

    def __init__(self, message: str, remedy: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.remedy = remedy


@dataclass(frozen=True, slots=True)
class ConfigAllow:
    file: str
    rules: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class Config:
    dialect: str
    postgres_version: int = 16
    paths: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    fail_on: str = "error"
    allow: tuple[ConfigAllow, ...] = field(default_factory=tuple)


def load_config(
    config_path: str | None,
    dialect_override: str | None = None,
    postgres_version_override: int | None = None,
) -> Config:
    """Read and validate the config file, then merge the CLI overrides into it.

    An explicit --config path must exist; the default path is optional so a run
    can be driven entirely by CLI flags and PATHS.
    """
    explicit = config_path is not None
    path = Path(config_path) if explicit else Path(DEFAULT_CONFIG_FILENAME)

    raw: dict[str, Any] = {}
    text = ""
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MigrateGuardError(f"cannot read config file {path}: {exc.strerror}") from exc
        except UnicodeDecodeError as exc:
            raise MigrateGuardError(f"config file {path} is not valid UTF-8") from exc
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise MigrateGuardError(f"invalid TOML in {path}: {exc}") from exc
        raw = _root_table(document, path, text)
    elif explicit:
        raise MigrateGuardError(f"config file {path} does not exist")

    values = _validate(raw, path, text)

    if dialect_override is not None:
        if dialect_override not in DIALECTS:
            raise MigrateGuardError(
                f'invalid --dialect "{dialect_override}"; '
                f"accepted values: {', '.join(DIALECTS)}"
            )
        values["dialect"] = dialect_override

    if postgres_version_override is not None:
        if postgres_version_override <= 0:
            raise MigrateGuardError(
                f"invalid --postgres-version {postgres_version_override}; "
                "it must be a positive integer"
            )
        values["postgres_version"] = postgres_version_override

    if values.get("dialect") is None:
        raise MigrateGuardError(
            "no dialect configured",
            f'add dialect = "postgres" to {path} or pass --dialect',
        )

    return Config(**values)


def _root_table(document: dict[str, Any], path: Path, text: str) -> dict[str, Any]:
    for key in document:
        if key != ROOT_TABLE:
            raise MigrateGuardError(
                f'unknown table "{key}" in {path}{_where(text, key)}; '
                f"the only accepted table is [{ROOT_TABLE}]"
            )
    section = document.get(ROOT_TABLE, {})
    if not isinstance(section, dict):
        raise MigrateGuardError(f"[{ROOT_TABLE}] in {path} must be a table")
    return section


def _validate(raw: dict[str, Any], path: Path, text: str) -> dict[str, Any]:
    for key in raw:
        if key not in TOP_LEVEL_KEYS:
            raise MigrateGuardError(
                f'unknown key "{key}" in {path}{_where(text, key)}; '
                f"accepted keys: {', '.join(TOP_LEVEL_KEYS)}"
            )

    values: dict[str, Any] = {"dialect": None}

    if "dialect" in raw:
        dialect = raw["dialect"]
        if dialect not in DIALECTS:
            raise MigrateGuardError(
                f'invalid dialect "{dialect}" in {path}; ' f"accepted values: {', '.join(DIALECTS)}"
            )
        values["dialect"] = dialect

    if "postgres_version" in raw:
        version = raw["postgres_version"]
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            raise MigrateGuardError(
                f"postgres_version in {path} must be a positive integer, got {version!r}"
            )
        values["postgres_version"] = version

    if "paths" in raw:
        values["paths"] = tuple(_string_list(raw["paths"], "paths", path))

    if "ignore" in raw:
        codes = _string_list(raw["ignore"], "ignore", path)
        for code in codes:
            if not CODE_PATTERN.match(code):
                raise MigrateGuardError(f'invalid rule code "{code}" in ignore in {path}')
            if code in NEVER_IGNORABLE:
                raise MigrateGuardError(
                    f"{code} cannot be ignored globally; "
                    "use an inline allow with a reason at the offending site"
                )
        values["ignore"] = tuple(codes)

    if "fail_on" in raw:
        fail_on = raw["fail_on"]
        if fail_on not in FAIL_ON_VALUES:
            raise MigrateGuardError(
                f'invalid fail_on "{fail_on}" in {path}; '
                f"accepted values: {', '.join(FAIL_ON_VALUES)}"
            )
        values["fail_on"] = fail_on

    if "allow" in raw:
        values["allow"] = _allow_entries(raw["allow"], path)

    return values


def _allow_entries(entries: Any, path: Path) -> tuple[ConfigAllow, ...]:
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise MigrateGuardError(f"allow in {path} must be an array of tables")

    parsed: list[ConfigAllow] = []
    for index, entry in enumerate(entries):
        location = f"allow entry {index + 1} in {path}"
        for key in entry:
            if key not in ALLOW_KEYS:
                raise MigrateGuardError(
                    f'unknown key "{key}" in {location}; accepted keys: {", ".join(ALLOW_KEYS)}'
                )
        file_value = entry.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            raise MigrateGuardError(f"{location} needs a non-empty file")
        rules = _string_list(entry.get("rules", []), "rules", path)
        if not rules:
            raise MigrateGuardError(f"{location} needs a non-empty rules list")
        for code in rules:
            if not CODE_PATTERN.match(code):
                raise MigrateGuardError(f'invalid rule code "{code}" in {location}')
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise MigrateGuardError(
                f"{location} has no reason",
                'add reason="..." with a short justification',
            )
        parsed.append(ConfigAllow(file=file_value, rules=tuple(rules), reason=reason.strip()))
    return tuple(parsed)


def _string_list(value: Any, key: str, path: Path) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MigrateGuardError(f"{key} in {path} must be a list of strings")
    return list(value)


def _where(text: str, key: str) -> str:
    """Best-effort line number for a key, since tomllib does not report positions."""
    pattern = re.compile(rf"^\s*(?:\[\[?[\w.-]*\.)?{re.escape(key)}\s*(?:=|\]\]?)")
    for number, line in enumerate(text.splitlines(), start=1):
        if pattern.match(line):
            return f" (line {number})"
    return ""
