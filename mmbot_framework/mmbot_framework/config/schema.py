"""BotConfig — validated configuration model for a Mattermost bot."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""


class BotConfig(BaseModel):
    """Validated configuration for a Mattermost bot.

    Required fields (must be present in every config source):
        url: Mattermost server URL (e.g. ``https://mattermost.example.com``).
        token: Bot authentication token.
        team_name: Mattermost team name (not display name).

    Optional fields:
        scheme: HTTP scheme. Defaults to ``"https"``.
        port: Server port. Defaults to ``443``.
        log_level: Python log level name. Defaults to ``"INFO"``.
        log_file: Path for rotating file logging. ``None`` means console only.
        session_ttl_seconds: Seconds of inactivity before a session expires. Defaults to ``3600``.
        session_cleanup_interval_seconds: How often the background cleanup task runs. Defaults to ``300``.
    """

    url: str
    token: str
    team_name: str
    scheme: str = "https"
    port: int = 443
    log_level: str = "INFO"
    log_file: str | None = None
    session_ttl_seconds: int = 3600
    session_cleanup_interval_seconds: int = 300

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError(f"port must be between 1 and 65535, got {value}")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in valid:
            raise ValueError(
                f"log_level must be one of {sorted(valid)}, got {value!r}"
            )
        return upper
