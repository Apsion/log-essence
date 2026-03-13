"""Tests for the discover module."""

from pathlib import Path

from log_essence.discover import (
    _count_lines,
    _find_log_files,
    discover_sources,
    format_discovery_table,
)


def test_count_lines(tmp_path: Path) -> None:
    f = tmp_path / "test.log"
    f.write_text("line1\nline2\nline3\n")
    assert _count_lines(f) == 3


def test_count_lines_nonexistent(tmp_path: Path) -> None:
    assert _count_lines(tmp_path / "nonexistent") == 0


def test_find_log_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.log").write_text("line1\nline2\n")
    (tmp_path / "error.log").write_text("error1\n")

    sources = _find_log_files()
    log_names = [s["name"] for s in sources]
    assert any("app.log" in name for name in log_names)
    assert any("error.log" in name for name in log_names)
    assert all(s["type"] == "file" for s in sources)


def test_find_log_files_empty_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    sources = _find_log_files()
    # Should not crash, may find system logs or nothing
    assert isinstance(sources, list)


def test_format_discovery_table_empty() -> None:
    result = format_discovery_table([])
    assert "No log sources found" in result


def test_format_discovery_table_with_sources() -> None:
    sources = [
        {
            "type": "file",
            "name": "/var/log/app.log",
            "lines": 1000,
            "command": "log-essence /var/log/app.log",
        },
        {
            "type": "docker",
            "name": "web (nginx:latest)",
            "lines": "?",
            "command": "docker logs web | log-essence -",
        },
    ]
    result = format_discovery_table(sources)
    assert "file" in result
    assert "docker" in result
    assert "app.log" in result
    assert "web" in result


def test_discover_sources_returns_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    sources = discover_sources()
    assert isinstance(sources, list)
    for s in sources:
        assert "type" in s
        assert "name" in s
        assert "command" in s
