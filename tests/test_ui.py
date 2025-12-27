"""Tests for the Streamlit UI module."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestAnalysisStats:
    """Tests for AnalysisStats model."""

    def test_savings_percent_calculation(self) -> None:
        """Test savings_percent property calculates correctly."""
        from log_essence.ui.models import AnalysisStats

        stats = AnalysisStats(
            processing_time_ms=100.0,
            redaction_count=5,
            original_tokens=1000,
            output_tokens=200,
        )
        # (1 - 200/1000) * 100 = 80%
        assert stats.savings_percent == 80.0

    def test_savings_percent_zero_original(self) -> None:
        """Test savings_percent handles zero original tokens."""
        from log_essence.ui.models import AnalysisStats

        stats = AnalysisStats(
            processing_time_ms=0.0,
            redaction_count=0,
            original_tokens=0,
            output_tokens=0,
        )
        assert stats.savings_percent == 0.0

    def test_savings_percent_no_savings(self) -> None:
        """Test savings_percent when output equals input."""
        from log_essence.ui.models import AnalysisStats

        stats = AnalysisStats(
            processing_time_ms=50.0,
            redaction_count=0,
            original_tokens=500,
            output_tokens=500,
        )
        assert stats.savings_percent == 0.0


class TestUIConfig:
    """Tests for UIConfig model."""

    def test_defaults(self) -> None:
        """Test UIConfig has sensible defaults."""
        from log_essence.ui.models import UIConfig

        config = UIConfig()
        assert config.token_budget == 8000
        assert config.num_clusters == 10
        assert config.redaction_mode == "moderate"
        assert config.severity_filter is None

    def test_token_budget_must_be_positive(self) -> None:
        """Test token_budget validation - must be >= 100."""
        from log_essence.ui.models import UIConfig

        with pytest.raises(ValidationError):
            UIConfig(token_budget=-100)

        with pytest.raises(ValidationError):
            UIConfig(token_budget=50)

    def test_token_budget_max_limit(self) -> None:
        """Test token_budget validation - must be <= 100000."""
        from log_essence.ui.models import UIConfig

        with pytest.raises(ValidationError):
            UIConfig(token_budget=200000)

    def test_num_clusters_must_be_positive(self) -> None:
        """Test num_clusters validation - must be >= 1."""
        from log_essence.ui.models import UIConfig

        with pytest.raises(ValidationError):
            UIConfig(num_clusters=0)

        with pytest.raises(ValidationError):
            UIConfig(num_clusters=-5)

    def test_num_clusters_max_limit(self) -> None:
        """Test num_clusters validation - must be <= 100."""
        from log_essence.ui.models import UIConfig

        with pytest.raises(ValidationError):
            UIConfig(num_clusters=150)

    def test_valid_redaction_modes(self) -> None:
        """Test UIConfig accepts all valid redaction modes."""
        from log_essence.ui.models import UIConfig

        for mode in ["disabled", "minimal", "moderate", "strict"]:
            config = UIConfig(redaction_mode=mode)
            assert config.redaction_mode == mode

    def test_invalid_redaction_mode(self) -> None:
        """Test UIConfig rejects invalid redaction mode."""
        from log_essence.ui.models import UIConfig

        with pytest.raises(ValidationError):
            UIConfig(redaction_mode="invalid")

    def test_empty_severity_filter_becomes_none(self) -> None:
        """Test empty severity filter list converts to None."""
        from log_essence.ui.models import UIConfig

        config = UIConfig(severity_filter=[])
        assert config.severity_filter is None

    def test_valid_severity_filter(self) -> None:
        """Test valid severity filter values."""
        from log_essence.ui.models import UIConfig

        config = UIConfig(severity_filter=["ERROR", "WARNING"])
        assert config.severity_filter == ["ERROR", "WARNING"]


class TestAnalyzeLogsFromText:
    """Tests for analyze_logs_from_text wrapper function."""

    def test_basic_analysis(self) -> None:
        """Test analyze_logs_from_text returns markdown analysis."""
        from log_essence.ui.app import analyze_logs_from_text
        from log_essence.ui.models import UIConfig

        logs = """2025-01-01T10:00:00Z INFO Server started
2025-01-01T10:00:01Z ERROR Connection failed
2025-01-01T10:00:02Z INFO Retry successful"""

        config = UIConfig(token_budget=2000, num_clusters=3)
        result = analyze_logs_from_text(logs, config)

        assert "# Log Analysis Summary" in result.markdown
        assert "Total lines:" in result.markdown
        assert result.stats.original_tokens > 0
        assert result.stats.output_tokens > 0

    def test_empty_input_returns_error(self) -> None:
        """Test graceful handling of empty input."""
        from log_essence.ui.app import analyze_logs_from_text
        from log_essence.ui.models import UIConfig

        config = UIConfig()
        result = analyze_logs_from_text("", config)

        assert "error" in result.markdown.lower() or "no log" in result.markdown.lower()

    def test_whitespace_only_returns_error(self) -> None:
        """Test graceful handling of whitespace-only input."""
        from log_essence.ui.app import analyze_logs_from_text
        from log_essence.ui.models import UIConfig

        config = UIConfig()
        result = analyze_logs_from_text("   \n\n  \t  ", config)

        assert "error" in result.markdown.lower() or "no log" in result.markdown.lower()

    def test_redaction_disabled(self) -> None:
        """Test redaction can be disabled."""
        from log_essence.ui.app import analyze_logs_from_text
        from log_essence.ui.models import UIConfig

        logs = "2025-01-01T10:00:00Z INFO User test@example.com logged in"
        config = UIConfig(redaction_mode="disabled")
        result = analyze_logs_from_text(logs, config)

        # With redaction disabled, email should appear as-is
        assert "test@example.com" in result.markdown
        assert result.stats.redaction_count == 0

    def test_redaction_enabled(self) -> None:
        """Test redaction works when enabled."""
        from log_essence.ui.app import analyze_logs_from_text
        from log_essence.ui.models import UIConfig

        logs = "2025-01-01T10:00:00Z INFO User test@example.com logged in"
        config = UIConfig(redaction_mode="moderate")
        result = analyze_logs_from_text(logs, config)

        # With redaction enabled, email should be redacted
        assert "test@example.com" not in result.markdown
        assert "[EMAIL:" in result.markdown
        assert result.stats.redaction_count > 0


class TestLaunchUI:
    """Tests for launch_ui function."""

    def test_launch_ui_exists(self) -> None:
        """Test launch_ui function exists and is callable."""
        from log_essence.ui import launch_ui

        assert callable(launch_ui)
