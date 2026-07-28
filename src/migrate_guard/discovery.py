"""Resolving scan paths to migration files and reading their text.

Reported paths stay in the user-supplied form: CI logs should not leak the
runner's filesystem layout.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import MigrateGuardError

FORMAT_BY_EXTENSION = {".sql": "sql"}


@dataclass(frozen=True, slots=True)
class MigrationFile:
    path: str
    format: str


def discover(paths: Sequence[str]) -> list[MigrationFile]:
    """Resolve files and directories to a sorted, deduplicated migration file list."""
    if not paths:
        raise MigrateGuardError(
            "no paths to check",
            "pass PATHS on the command line or set paths in .migrateguard.toml",
        )

    found: dict[str, MigrationFile] = {}
    for entry in paths:
        candidate = Path(entry)
        if candidate.is_dir():
            for child in _walk(candidate):
                _add(found, child)
        elif candidate.is_file():
            extension = candidate.suffix.lower()
            if extension not in FORMAT_BY_EXTENSION:
                raise MigrateGuardError(
                    f"unsupported file type {entry}; "
                    f"accepted extensions: {', '.join(sorted(FORMAT_BY_EXTENSION))}"
                )
            _add(found, candidate)
        else:
            raise MigrateGuardError(f"path {entry} does not exist")

    return [found[key] for key in sorted(found)]


def read_source(path: str) -> str:
    """Read a migration file; an unreadable file is an environment error, not a finding."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MigrateGuardError(f"{path} is not valid UTF-8 text") from exc
    except OSError as exc:
        raise MigrateGuardError(f"cannot read {path}: {exc.strerror}") from exc


def _walk(root: Path) -> list[Path]:
    """Collect known migration files under root without following symlinks out of it."""
    boundary = _resolve(root)
    collected: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories[:] = [
            name
            for name in sorted(subdirectories)
            if _resolve(Path(directory) / name).is_relative_to(boundary)
        ]
        for filename in sorted(filenames):
            child = Path(directory) / filename
            if child.suffix.lower() not in FORMAT_BY_EXTENSION:
                continue
            if child.is_symlink() and not _resolve(child).is_relative_to(boundary):
                continue
            collected.append(child)
    return collected


def _add(found: dict[str, MigrationFile], path: Path) -> None:
    key = str(path)
    found.setdefault(key, MigrationFile(path=key, format=FORMAT_BY_EXTENSION[path.suffix.lower()]))


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()
