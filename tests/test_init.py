"""Tests for the init module."""

import json
from pathlib import Path

from log_essence.init import (
    SERVER_ENTRY_NAME,
    _add_server_entry,
    _get_mcp_command,
    _is_configured,
    _read_config,
    _remove_server_entry,
    configure_tool,
)


def test_get_mcp_command() -> None:
    cmd = _get_mcp_command()
    assert cmd[0] == "uvx"
    assert "log-essence" in cmd
    assert "serve" in cmd


def test_is_configured_false() -> None:
    config = {"mcpServers": {}}
    assert _is_configured(config, "mcpServers") is False


def test_is_configured_true() -> None:
    config = {"mcpServers": {SERVER_ENTRY_NAME: {"command": "uvx"}}}
    assert _is_configured(config, "mcpServers") is True


def test_add_server_entry() -> None:
    config: dict = {}
    result = _add_server_entry(config, "mcpServers")
    assert SERVER_ENTRY_NAME in result["mcpServers"]
    entry = result["mcpServers"][SERVER_ENTRY_NAME]
    assert entry["command"] == "uvx"
    assert "log-essence" in entry["args"]


def test_remove_server_entry() -> None:
    config = {"mcpServers": {SERVER_ENTRY_NAME: {"command": "test"}}}
    result = _remove_server_entry(config, "mcpServers")
    assert SERVER_ENTRY_NAME not in result["mcpServers"]


def test_read_config_nonexistent(tmp_path: Path) -> None:
    result = _read_config(tmp_path / "nonexistent.json")
    assert result == {}


def test_read_config_valid(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"mcpServers": {"other": {}}}))
    result = _read_config(config_file)
    assert "mcpServers" in result


def test_configure_tool_unknown(capsys) -> None:
    result = configure_tool("unknown-tool")
    assert result is False
    captured = capsys.readouterr()
    assert "Unknown tool" in captured.err


def test_configure_tool_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    # Patch the config path for claude-desktop to a tmp dir
    from log_essence import init

    config_path = tmp_path / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    original_get = init._get_config_path

    def mock_get(tool_name):
        if tool_name == "claude-desktop":
            return config_path
        return original_get(tool_name)

    monkeypatch.setattr(init, "_get_config_path", mock_get)

    result = configure_tool("claude-desktop", dry_run=True)
    assert result is True
    captured = capsys.readouterr()
    assert "would add" in captured.out


def test_configure_tool_install(tmp_path: Path, monkeypatch) -> None:
    from log_essence import init

    config_path = tmp_path / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    original_get = init._get_config_path

    def mock_get(tool_name):
        if tool_name == "claude-desktop":
            return config_path
        return original_get(tool_name)

    monkeypatch.setattr(init, "_get_config_path", mock_get)

    result = configure_tool("claude-desktop")
    assert result is True
    assert config_path.exists()

    data = json.loads(config_path.read_text())
    assert SERVER_ENTRY_NAME in data["mcpServers"]


def test_configure_tool_idempotent(tmp_path: Path, monkeypatch, capsys) -> None:
    from log_essence import init

    config_path = tmp_path / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_ENTRY_NAME: {"command": "uvx", "args": ["log-essence", "serve"]}
                }
            }
        )
    )

    original_get = init._get_config_path

    def mock_get(tool_name):
        if tool_name == "claude-desktop":
            return config_path
        return original_get(tool_name)

    monkeypatch.setattr(init, "_get_config_path", mock_get)

    result = configure_tool("claude-desktop")
    assert result is False  # Already configured
    captured = capsys.readouterr()
    assert "already configured" in captured.out


def test_configure_tool_uninstall(tmp_path: Path, monkeypatch) -> None:
    from log_essence import init

    config_path = tmp_path / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"mcpServers": {SERVER_ENTRY_NAME: {"command": "uvx"}}}))

    original_get = init._get_config_path

    def mock_get(tool_name):
        if tool_name == "claude-desktop":
            return config_path
        return original_get(tool_name)

    monkeypatch.setattr(init, "_get_config_path", mock_get)

    result = configure_tool("claude-desktop", uninstall=True)
    assert result is True

    data = json.loads(config_path.read_text())
    assert SERVER_ENTRY_NAME not in data["mcpServers"]


def test_configure_tool_creates_backup(tmp_path: Path, monkeypatch) -> None:
    from log_essence import init

    config_path = tmp_path / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"existing": True}))

    original_get = init._get_config_path

    def mock_get(tool_name):
        if tool_name == "claude-desktop":
            return config_path
        return original_get(tool_name)

    monkeypatch.setattr(init, "_get_config_path", mock_get)

    configure_tool("claude-desktop")
    backup = config_path.with_suffix(".json.bak")
    assert backup.exists()
    backup_data = json.loads(backup.read_text())
    assert backup_data == {"existing": True}
