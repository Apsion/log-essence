"""Cumulative analytics persistence and reporting for log-essence.

Tracks analysis metrics in a local SQLite database so users can see
the value log-essence delivers over time.

Storage locations:
- macOS: ~/Library/Application Support/log-essence/stats.db
- Linux: ~/.local/share/log-essence/stats.db

Opt-out: set LOG_ESSENCE_NO_ANALYTICS=1 or analytics: false in config.
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _get_data_dir() -> Path:
    """Get platform-appropriate data directory for analytics storage."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "log-essence"
    # Linux / other
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "log-essence"
    return Path.home() / ".local" / "share" / "log-essence"


def _is_analytics_disabled() -> bool:
    """Check if analytics are disabled via environment variable."""
    return os.environ.get("LOG_ESSENCE_NO_ANALYTICS", "").strip() in ("1", "true", "yes")


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    lines_in INTEGER NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    redactions INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL,
    log_format TEXT NOT NULL DEFAULT 'unknown'
)
"""


def _get_db_path() -> Path:
    """Get the path to the analytics database."""
    return _get_data_dir() / "stats.db"


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to the analytics database, creating it if needed."""
    if db_path is None:
        db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def record_analysis(
    *,
    source: str,
    lines_in: int,
    tokens_in: int,
    tokens_out: int,
    redactions: int = 0,
    duration_ms: float = 0.0,
    log_format: str = "unknown",
    db_path: Path | None = None,
) -> None:
    """Record a single analysis run to the stats database.

    No-op if analytics are disabled.
    """
    if _is_analytics_disabled():
        return

    try:
        conn = _get_connection(db_path)
        conn.execute(
            "INSERT INTO stats (timestamp, source, lines_in, tokens_in, tokens_out, "
            "redactions, duration_ms, log_format) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                source,
                lines_in,
                tokens_in,
                tokens_out,
                redactions,
                duration_ms,
                log_format,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass  # Never let analytics failures break the main workflow


def _parse_since(since: str) -> datetime | None:
    """Parse a relative time string like '7d', '1h', '30m' into a datetime cutoff."""
    import re

    match = re.match(r"^(\d+)([smhdw])$", since.lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    delta_map = {
        "s": timedelta(seconds=value),
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
        "w": timedelta(weeks=value),
    }
    return datetime.now(UTC) - delta_map[unit]


def get_stats(
    since: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """Query cumulative analytics.

    Args:
        since: Optional relative time window (e.g. '7d', '1h').
        db_path: Override database path (for testing).

    Returns:
        Dict with total_analyses, total_lines, total_tokens_in, total_tokens_out,
        total_redactions, total_duration_ms, avg_compression_pct, formats breakdown.
    """
    try:
        conn = _get_connection(db_path)
    except sqlite3.Error:
        return _empty_stats()

    where = ""
    params: list = []
    if since:
        cutoff = _parse_since(since)
        if cutoff:
            where = "WHERE timestamp >= ?"
            params = [cutoff.isoformat()]

    row = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(lines_in),0), COALESCE(SUM(tokens_in),0), "
        f"COALESCE(SUM(tokens_out),0), COALESCE(SUM(redactions),0), "
        f"COALESCE(SUM(duration_ms),0) FROM stats {where}",
        params,
    ).fetchone()

    total_analyses = row[0]
    total_lines = row[1]
    total_tokens_in = row[2]
    total_tokens_out = row[3]
    total_redactions = row[4]
    total_duration_ms = row[5]

    avg_compression = 0.0
    if total_tokens_in > 0:
        avg_compression = (1 - total_tokens_out / total_tokens_in) * 100

    # Format breakdown
    query = (
        f"SELECT log_format, COUNT(*) FROM stats {where} GROUP BY log_format ORDER BY COUNT(*) DESC"
    )
    formats_rows = conn.execute(query, params).fetchall()
    formats = {r[0]: r[1] for r in formats_rows}

    conn.close()

    return {
        "total_analyses": total_analyses,
        "total_lines": total_lines,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_tokens_saved": total_tokens_in - total_tokens_out,
        "total_redactions": total_redactions,
        "total_duration_ms": total_duration_ms,
        "avg_compression_pct": round(avg_compression, 1),
        "formats": formats,
    }


def _empty_stats() -> dict:
    return {
        "total_analyses": 0,
        "total_lines": 0,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "total_tokens_saved": 0,
        "total_redactions": 0,
        "total_duration_ms": 0,
        "avg_compression_pct": 0.0,
        "formats": {},
    }


def reset_stats(db_path: Path | None = None) -> bool:
    """Delete all analytics data.

    Returns:
        True if reset succeeded.
    """
    try:
        conn = _get_connection(db_path)
        conn.execute("DELETE FROM stats")
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def format_stats_dashboard(stats: dict) -> str:
    """Format stats dict into a human-readable dashboard string."""
    if stats["total_analyses"] == 0:
        return "No analyses recorded yet. Run log-essence on some logs to start tracking!"

    lines = [
        "log-essence Analytics",
        "=" * 40,
        f"Total analyses:    {stats['total_analyses']:,}",
        f"Lines processed:   {stats['total_lines']:,}",
        f"Tokens in:         {stats['total_tokens_in']:,}",
        f"Tokens out:        {stats['total_tokens_out']:,}",
        f"Tokens saved:      {stats['total_tokens_saved']:,}",
        f"Avg compression:   {stats['avg_compression_pct']}%",
        f"Secrets redacted:  {stats['total_redactions']:,}",
        f"Total time:        {stats['total_duration_ms'] / 1000:.1f}s",
    ]

    if stats["formats"]:
        lines.append("")
        lines.append("Log formats analyzed:")
        for fmt, count in stats["formats"].items():
            lines.append(f"  {fmt}: {count}")

    return "\n".join(lines)


def format_stats_footer(
    *,
    lines_in: int,
    tokens_out: int,
    tokens_in: int,
    redactions: int,
    duration_ms: float,
) -> str:
    """Format a one-line stats footer for stderr output after analysis.

    Example: log-essence: 15,432 lines -> 847 tokens (94.5% reduction, 23 secrets redacted, 145ms)
    """
    reduction = (1 - tokens_out / tokens_in) * 100 if tokens_in > 0 else 0.0

    parts = [f"{reduction:.1f}% reduction"]
    if redactions > 0:
        parts.append(f"{redactions:,} secrets redacted")
    parts.append(f"{duration_ms:.0f}ms")

    return f"log-essence: {lines_in:,} lines → {tokens_out:,} tokens ({', '.join(parts)})"


def run_stats_command(
    *,
    as_json: bool = False,
    since: str | None = None,
    reset: bool = False,
    db_path: Path | None = None,
) -> int:
    """Execute the stats subcommand.

    Returns:
        Exit code (0 for success).
    """
    if reset:
        if reset_stats(db_path):
            print("Analytics data cleared.", file=sys.stderr)
        else:
            print("Failed to clear analytics data.", file=sys.stderr)
            return 1
        return 0

    stats = get_stats(since=since, db_path=db_path)

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        print(format_stats_dashboard(stats))

    return 0
