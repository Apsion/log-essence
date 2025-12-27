"""Configuration file support for log-essence.

Loads configuration from YAML files and merges with CLI arguments.

Config file locations (checked in order):
1. ./.log-essence.yaml (current directory)
2. ~/.config/log-essence/config.yaml (XDG standard)
3. ~/.log-essence.yaml (home directory fallback)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

RedactionModeType = Literal["disabled", "minimal", "moderate", "strict"]
SeverityLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
OutputFormat = Literal["markdown", "json"]


class ConfigDefaults(BaseModel):
    """Default configuration values."""

    token_budget: int = Field(default=8000, ge=100, le=100000)
    clusters: int = Field(default=10, ge=1, le=100)
    redaction: RedactionModeType = Field(default="moderate")
    severity: list[SeverityLevel] | None = Field(default=None)
    output: OutputFormat = Field(default="markdown")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: list[str] | None) -> list[str] | None:
        """Convert empty list to None and uppercase values."""
        if v is None:
            return None
        if len(v) == 0:
            return None
        return [s.upper() for s in v]


class ConfigProfile(BaseModel):
    """A named configuration profile."""

    token_budget: int | None = Field(default=None, ge=100, le=100000)
    clusters: int | None = Field(default=None, ge=1, le=100)
    redaction: RedactionModeType | None = Field(default=None)
    severity: list[SeverityLevel] | None = Field(default=None)
    since: str | None = Field(default=None)
    output: OutputFormat | None = Field(default=None)


class Config(BaseModel):
    """Complete configuration schema."""

    defaults: ConfigDefaults = Field(default_factory=ConfigDefaults)
    profiles: dict[str, ConfigProfile] = Field(default_factory=dict)


# Default config file search locations
CONFIG_LOCATIONS = [
    Path(".log-essence.yaml"),
    Path(".log-essence.yml"),
    Path.home() / ".config" / "log-essence" / "config.yaml",
    Path.home() / ".config" / "log-essence" / "config.yml",
    Path.home() / ".log-essence.yaml",
    Path.home() / ".log-essence.yml",
]


def find_config_file() -> Path | None:
    """Find the first existing config file in standard locations.

    Returns:
        Path to config file or None if not found.
    """
    for path in CONFIG_LOCATIONS:
        if path.exists() and path.is_file():
            return path
    return None


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from a YAML file.

    Args:
        config_path: Optional explicit path to config file.
                    If None, searches standard locations.

    Returns:
        Config object with loaded values (or defaults if no file found).
    """
    if config_path is None:
        config_path = find_config_file()

    if config_path is None or not config_path.exists():
        return Config()

    try:
        content = config_path.read_text()
        data = yaml.safe_load(content)
        if data is None:
            return Config()
        return Config.model_validate(data)
    except (yaml.YAMLError, ValueError):
        # Return defaults on parse error
        return Config()


def get_profile_values(config: Config, profile_name: str | None) -> ConfigProfile | None:
    """Get values from a named profile.

    Args:
        config: The loaded configuration.
        profile_name: Name of the profile to load.

    Returns:
        ConfigProfile or None if profile doesn't exist.
    """
    if profile_name is None:
        return None
    return config.profiles.get(profile_name)


def merge_config_with_args(
    config: Config,
    profile_name: str | None = None,
    *,
    token_budget: int | None = None,
    clusters: int | None = None,
    redaction: str | None = None,
    severity: list[str] | None = None,
    since: str | None = None,
    output: str | None = None,
) -> dict[str, object]:
    """Merge config defaults, profile values, and CLI args.

    Priority (highest to lowest):
    1. CLI arguments (if explicitly provided)
    2. Profile values (if profile specified)
    3. Config defaults
    4. Built-in defaults

    Args:
        config: The loaded configuration.
        profile_name: Optional profile name to apply.
        token_budget: CLI --token-budget value.
        clusters: CLI --clusters value.
        redaction: CLI --redact value.
        severity: CLI --severity value.
        since: CLI --since value.
        output: CLI --output value.

    Returns:
        Dict with merged configuration values.
    """
    # Start with defaults from config file
    result: dict[str, object] = {
        "token_budget": config.defaults.token_budget,
        "clusters": config.defaults.clusters,
        "redaction": config.defaults.redaction,
        "severity": config.defaults.severity,
        "since": None,
        "output": config.defaults.output,
    }

    # Apply profile values (if any)
    profile = get_profile_values(config, profile_name)
    if profile:
        if profile.token_budget is not None:
            result["token_budget"] = profile.token_budget
        if profile.clusters is not None:
            result["clusters"] = profile.clusters
        if profile.redaction is not None:
            result["redaction"] = profile.redaction
        if profile.severity is not None:
            result["severity"] = profile.severity
        if profile.since is not None:
            result["since"] = profile.since
        if profile.output is not None:
            result["output"] = profile.output

    # Apply CLI arguments (highest priority)
    # Note: We need to know if the user explicitly provided a value
    # vs using the default. The caller should pass None for defaults.
    if token_budget is not None:
        result["token_budget"] = token_budget
    if clusters is not None:
        result["clusters"] = clusters
    if redaction is not None:
        result["redaction"] = redaction
    if severity is not None:
        result["severity"] = severity
    if since is not None:
        result["since"] = since
    if output is not None:
        result["output"] = output

    return result
