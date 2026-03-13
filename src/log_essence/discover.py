"""Discover analyzable log sources in the current environment.

Scans for:
- Log files in the current directory and common locations
- Running Docker containers
- Docker Compose projects
- systemd units (if journalctl is available)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _count_lines(path: Path) -> int:
    """Count lines in a file, returning 0 on error."""
    try:
        return sum(1 for _ in path.open(errors="replace"))
    except OSError:
        return 0


def _find_log_files() -> list[dict]:
    """Find log files in the current directory and common locations."""
    sources: list[dict] = []
    seen: set[Path] = set()

    search_dirs = [
        Path.cwd(),
        Path.cwd() / "logs",
        Path.cwd() / "log",
    ]

    # Add system log dirs only if they exist and are readable
    for system_dir in [Path("/var/log"), Path.home() / "Library" / "Logs"]:
        if system_dir.is_dir():
            search_dirs.append(system_dir)

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for ext in ("*.log", "*.log.*", "*.txt"):
            try:
                for f in search_dir.glob(ext):
                    resolved = f.resolve()
                    if resolved in seen or not f.is_file():
                        continue
                    seen.add(resolved)
                    lines = _count_lines(f)
                    if lines > 0:
                        sources.append(
                            {
                                "type": "file",
                                "name": str(f),
                                "lines": lines,
                                "command": f"log-essence {f}",
                            }
                        )
            except PermissionError:
                continue

    return sources


def _find_docker_containers() -> list[dict]:
    """Find running Docker containers with log output."""
    if not shutil.which("docker"):
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    sources: list[dict] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, image = parts[1], parts[2]
        sources.append(
            {
                "type": "docker",
                "name": f"{name} ({image})",
                "lines": "?",
                "command": f"docker logs {name} 2>&1 | log-essence -",
            }
        )

    return sources


def _find_compose_projects() -> list[dict]:
    """Find Docker Compose projects in the current directory."""
    sources: list[dict] = []
    compose_files = [
        Path.cwd() / "docker-compose.yml",
        Path.cwd() / "docker-compose.yaml",
        Path.cwd() / "compose.yml",
        Path.cwd() / "compose.yaml",
    ]

    for cf in compose_files:
        if cf.is_file():
            sources.append(
                {
                    "type": "compose",
                    "name": str(cf.name),
                    "lines": "?",
                    "command": "docker compose logs 2>&1 | log-essence -",
                }
            )
            break  # Only report the first one found

    return sources


def _find_journalctl_units() -> list[dict]:
    """Find systemd units with recent log activity."""
    if not shutil.which("journalctl"):
        return []

    try:
        result = subprocess.run(
            ["journalctl", "--list-boots", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    # Suggest the most common useful sources
    return [
        {
            "type": "journald",
            "name": "system journal",
            "lines": "?",
            "command": "journalctl --since '1h ago' --no-pager | log-essence -",
        },
    ]


def discover_sources() -> list[dict]:
    """Discover all analyzable log sources.

    Returns:
        List of source dicts with keys: type, name, lines, command.
    """
    sources: list[dict] = []
    sources.extend(_find_log_files())
    sources.extend(_find_docker_containers())
    sources.extend(_find_compose_projects())
    sources.extend(_find_journalctl_units())
    return sources


def format_discovery_table(sources: list[dict]) -> str:
    """Format discovered sources as a table."""
    if not sources:
        return "No log sources found in the current environment."

    # Calculate column widths
    type_w = max(len(s["type"]) for s in sources)
    name_w = max(len(str(s["name"])) for s in sources)
    lines_w = max(len(str(s["lines"])) for s in sources)

    type_w = max(type_w, 4)
    name_w = min(max(name_w, 4), 50)
    lines_w = max(lines_w, 5)

    header = f"{'Type':<{type_w}}  {'Source':<{name_w}}  {'Lines':>{lines_w}}  Command"
    sep = f"{'-' * type_w}  {'-' * name_w}  {'-' * lines_w}  {'-' * 30}"

    rows = [header, sep]
    for s in sources:
        name = str(s["name"])
        if len(name) > name_w:
            name = "..." + name[-(name_w - 3) :]
        lines_str = str(s["lines"])
        rows.append(
            f"{s['type']:<{type_w}}  {name:<{name_w}}  {lines_str:>{lines_w}}  {s['command']}"
        )

    return "\n".join(rows)


def run_discover_command() -> int:
    """Execute the discover subcommand.

    Returns:
        Exit code (0 for success).
    """
    print("Scanning for log sources...", file=sys.stderr)
    sources = discover_sources()
    print(format_discovery_table(sources))
    print(f"\nFound {len(sources)} source(s).", file=sys.stderr)
    return 0
