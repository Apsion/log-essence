"""Tests for the analytics module."""

import json
from pathlib import Path

from log_essence.analytics import (
    format_stats_dashboard,
    format_stats_footer,
    get_stats,
    record_analysis,
    reset_stats,
    run_stats_command,
)


def test_record_and_get_stats(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    record_analysis(
        source="/var/log/test.log",
        lines_in=1000,
        tokens_in=5000,
        tokens_out=500,
        redactions=3,
        duration_ms=120.5,
        log_format="docker",
        db_path=db,
    )
    stats = get_stats(db_path=db)
    assert stats["total_analyses"] == 1
    assert stats["total_lines"] == 1000
    assert stats["total_tokens_in"] == 5000
    assert stats["total_tokens_out"] == 500
    assert stats["total_tokens_saved"] == 4500
    assert stats["total_redactions"] == 3
    assert stats["avg_compression_pct"] == 90.0
    assert stats["formats"]["docker"] == 1


def test_multiple_records(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    for i in range(3):
        record_analysis(
            source=f"/var/log/test{i}.log",
            lines_in=100,
            tokens_in=1000,
            tokens_out=100,
            db_path=db,
        )
    stats = get_stats(db_path=db)
    assert stats["total_analyses"] == 3
    assert stats["total_lines"] == 300
    assert stats["total_tokens_in"] == 3000
    assert stats["total_tokens_out"] == 300


def test_reset_stats(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    record_analysis(source="test", lines_in=10, tokens_in=100, tokens_out=10, db_path=db)
    assert get_stats(db_path=db)["total_analyses"] == 1
    assert reset_stats(db_path=db) is True
    assert get_stats(db_path=db)["total_analyses"] == 0


def test_get_stats_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    stats = get_stats(db_path=db)
    assert stats["total_analyses"] == 0
    assert stats["avg_compression_pct"] == 0.0


def test_get_stats_since_filter(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    record_analysis(source="test", lines_in=10, tokens_in=100, tokens_out=10, db_path=db)
    # All records are recent, so 1h filter should include them
    stats = get_stats(since="1h", db_path=db)
    assert stats["total_analyses"] == 1


def test_analytics_disabled(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "stats.db"
    monkeypatch.setenv("LOG_ESSENCE_NO_ANALYTICS", "1")
    record_analysis(source="test", lines_in=10, tokens_in=100, tokens_out=10, db_path=db)
    stats = get_stats(db_path=db)
    assert stats["total_analyses"] == 0


def test_format_stats_footer() -> None:
    footer = format_stats_footer(
        lines_in=15432,
        tokens_out=847,
        tokens_in=15000,
        redactions=23,
        duration_ms=145,
    )
    assert "15,432 lines" in footer
    assert "847 tokens" in footer
    assert "94.4% reduction" in footer
    assert "23 secrets redacted" in footer
    assert "145ms" in footer


def test_format_stats_footer_no_redactions() -> None:
    footer = format_stats_footer(
        lines_in=100,
        tokens_out=50,
        tokens_in=200,
        redactions=0,
        duration_ms=50,
    )
    assert "secrets redacted" not in footer
    assert "75.0% reduction" in footer


def test_format_stats_dashboard(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    record_analysis(
        source="test",
        lines_in=1000,
        tokens_in=5000,
        tokens_out=500,
        redactions=5,
        duration_ms=100,
        log_format="syslog",
        db_path=db,
    )
    stats = get_stats(db_path=db)
    dashboard = format_stats_dashboard(stats)
    assert "Total analyses" in dashboard
    assert "1,000" in dashboard
    assert "syslog" in dashboard


def test_format_stats_dashboard_empty() -> None:
    from log_essence.analytics import _empty_stats

    dashboard = format_stats_dashboard(_empty_stats())
    assert "No analyses recorded" in dashboard


def test_run_stats_command_json(tmp_path: Path, capsys) -> None:
    db = tmp_path / "stats.db"
    record_analysis(source="test", lines_in=10, tokens_in=100, tokens_out=10, db_path=db)
    result = run_stats_command(as_json=True, db_path=db)
    assert result == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_analyses"] == 1


def test_run_stats_command_reset(tmp_path: Path) -> None:
    db = tmp_path / "stats.db"
    record_analysis(source="test", lines_in=10, tokens_in=100, tokens_out=10, db_path=db)
    result = run_stats_command(reset=True, db_path=db)
    assert result == 0
    assert get_stats(db_path=db)["total_analyses"] == 0
