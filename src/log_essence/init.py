"""Auto-configure log-essence as an MCP server for AI coding tools.

Removes the manual JSON editing currently required to set up log-essence
with Claude Desktop, Claude Code, and other AI tools.
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
from pathlib import Path

# Tool configuration registry
TOOL_CONFIGS: dict[str, dict] = {
    "claude-desktop": {
        "display_name": "Claude Desktop",
        "config_paths": {
            "Darwin": Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
            "Linux": Path.home() / ".config" / "Claude" / "claude_desktop_config.json",
        },
        "key": "mcpServers",
    },
    "claude-code": {
        "display_name": "Claude Code",
        "config_paths": {
            "Darwin": Path.home() / ".claude" / "settings.json",
            "Linux": Path.home() / ".claude" / "settings.json",
        },
        "key": "mcpServers",
    },
}

SERVER_ENTRY_NAME = "log-essence"


def _get_mcp_command() -> list[str]:
    """Get the MCP server command for log-essence."""
    return ["uvx", "log-essence", "serve"]


def _get_config_path(tool_name: str) -> Path | None:
    """Get the config file path for a tool on the current platform."""
    tool = TOOL_CONFIGS.get(tool_name)
    if not tool:
        return None
    system = platform.system()
    return tool["config_paths"].get(system)


def _detect_installed_tools() -> list[str]:
    """Detect which AI tools have config directories present."""
    found = []
    for tool_name in TOOL_CONFIGS:
        path = _get_config_path(tool_name)
        if path and path.parent.exists():
            found.append(tool_name)
    return found


def _read_config(path: Path) -> dict:
    """Read a JSON config file, returning empty dict if it doesn't exist."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _backup_config(path: Path) -> Path | None:
    """Create a backup of the config file before modifying."""
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    return backup


def _write_config(path: Path, data: dict) -> None:
    """Write JSON config, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _is_configured(config: dict, key: str) -> bool:
    """Check if log-essence is already configured in the config."""
    servers = config.get(key, {})
    return SERVER_ENTRY_NAME in servers


def _add_server_entry(config: dict, key: str) -> dict:
    """Add log-essence MCP server entry to config."""
    if key not in config:
        config[key] = {}
    config[key][SERVER_ENTRY_NAME] = {
        "command": _get_mcp_command()[0],
        "args": _get_mcp_command()[1:],
    }
    return config


def _remove_server_entry(config: dict, key: str) -> dict:
    """Remove log-essence MCP server entry from config."""
    servers = config.get(key, {})
    servers.pop(SERVER_ENTRY_NAME, None)
    return config


def configure_tool(
    tool_name: str,
    *,
    dry_run: bool = False,
    uninstall: bool = False,
) -> bool:
    """Configure or unconfigure log-essence for a specific AI tool.

    Args:
        tool_name: Name of the tool (e.g. 'claude-desktop').
        dry_run: If True, only print what would happen.
        uninstall: If True, remove configuration instead of adding.

    Returns:
        True if changes were made (or would be made in dry-run).
    """
    tool = TOOL_CONFIGS.get(tool_name)
    if not tool:
        print(f"Unknown tool: {tool_name}", file=sys.stderr)
        print(f"Supported tools: {', '.join(TOOL_CONFIGS.keys())}", file=sys.stderr)
        return False

    config_path = _get_config_path(tool_name)
    if not config_path:
        print(
            f"{tool['display_name']}: not supported on {platform.system()}",
            file=sys.stderr,
        )
        return False

    config = _read_config(config_path)
    key = tool["key"]

    if uninstall:
        if not _is_configured(config, key):
            print(f"{tool['display_name']}: log-essence not configured, nothing to remove")
            return False
        if dry_run:
            print(f"{tool['display_name']}: would remove log-essence from {config_path}")
            return True
        _backup_config(config_path)
        config = _remove_server_entry(config, key)
        _write_config(config_path, config)
        print(f"{tool['display_name']}: removed log-essence from {config_path}")
        return True

    # Install
    if _is_configured(config, key):
        print(f"{tool['display_name']}: already configured, skipping")
        return False

    if dry_run:
        print(f"{tool['display_name']}: would add log-essence to {config_path}")
        cmd = _get_mcp_command()
        print(f"  command: {cmd[0]}")
        print(f"  args: {cmd[1:]}")
        return True

    _backup_config(config_path)
    config = _add_server_entry(config, key)
    _write_config(config_path, config)
    print(f"{tool['display_name']}: configured log-essence in {config_path}")
    return True


def run_init_command(
    *,
    tool: str | None = None,
    dry_run: bool = False,
    uninstall: bool = False,
) -> int:
    """Execute the init subcommand.

    Args:
        tool: Specific tool to configure, or None for auto-detect.
        dry_run: Preview changes without writing.
        uninstall: Remove configuration.

    Returns:
        Exit code (0 for success).
    """
    if tool:
        tools = [tool]
    else:
        tools = _detect_installed_tools()
        if not tools:
            print("No supported AI tools detected.", file=sys.stderr)
            print(
                f"Supported tools: {', '.join(TOOL_CONFIGS.keys())}",
                file=sys.stderr,
            )
            print("Use --tool <name> to configure a specific tool.", file=sys.stderr)
            return 1

    any_configured = False
    for t in tools:
        if configure_tool(t, dry_run=dry_run, uninstall=uninstall):
            any_configured = True

    if not any_configured and not uninstall:
        print("All detected tools are already configured.")

    return 0
