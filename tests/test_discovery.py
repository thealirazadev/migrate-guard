from __future__ import annotations

from pathlib import Path

import pytest

from migrate_guard.config import MigrateGuardError
from migrate_guard.discovery import discover, read_source


def test_directories_are_walked_recursively_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "0002.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "0001.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("nope\n", encoding="utf-8")

    found = discover([str(tmp_path)])

    assert [Path(item.path).name for item in found] == ["0001.sql", "0002.sql"]
    assert {item.format for item in found} == {"sql"}


def test_paths_are_reported_as_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "0001.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert discover(["."])[0].path == "0001.sql"


def test_duplicate_paths_are_deduplicated(tmp_path: Path) -> None:
    target = tmp_path / "0001.sql"
    target.write_text("SELECT 1;\n", encoding="utf-8")

    assert len(discover([str(target), str(target)])) == 1


def test_symlink_out_of_the_scan_root_is_skipped(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.sql").write_text("DROP TABLE x;\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "0001.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (root / "link.sql").symlink_to(outside / "secret.sql")

    assert [Path(item.path).name for item in discover([str(root)])] == ["0001.sql"]


def test_missing_path_is_an_error() -> None:
    with pytest.raises(MigrateGuardError, match="does not exist"):
        discover(["does/not/exist"])


def test_unsupported_explicit_file_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("nope\n", encoding="utf-8")

    with pytest.raises(MigrateGuardError, match="unsupported file type"):
        discover([str(target)])


def test_no_paths_is_an_error() -> None:
    with pytest.raises(MigrateGuardError) as excinfo:
        discover([])
    assert excinfo.value.remedy is not None


def test_unreadable_file_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / "0001.sql"
    target.write_text("SELECT 1;\n", encoding="utf-8")
    target.chmod(0o000)
    try:
        with pytest.raises(MigrateGuardError, match="cannot read"):
            read_source(str(target))
    finally:
        target.chmod(0o644)


def test_undecodable_file_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / "0001.sql"
    target.write_bytes(b"\xff\xfe\x00binary")

    with pytest.raises(MigrateGuardError, match="not valid UTF-8"):
        read_source(str(target))
