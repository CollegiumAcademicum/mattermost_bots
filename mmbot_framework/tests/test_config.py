"""Tests for BotConfig schema validation."""

import pytest
from pydantic import ValidationError

from mmbot_framework.config.schema import BotConfig, ConfigError


def _valid_kwargs() -> dict:
    return {"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}


def test_botconfig_defaults():
    config = BotConfig(**_valid_kwargs())
    assert config.scheme == "https"
    assert config.port == 443
    assert config.log_level == "INFO"
    assert config.log_file is None
    assert config.session_ttl_seconds == 3600
    assert config.session_cleanup_interval_seconds == 300


def test_botconfig_custom_values():
    config = BotConfig(
        url="http://localhost",
        token="abc",
        team_name="dev",
        scheme="http",
        port=8065,
        log_level="debug",
        log_file="/tmp/bot.log",
        session_ttl_seconds=600,
        session_cleanup_interval_seconds=60,
    )
    assert config.port == 8065
    assert config.scheme == "http"
    assert config.log_level == "DEBUG"   # normalised to upper
    assert config.session_ttl_seconds == 600


def test_botconfig_missing_url():
    with pytest.raises(ValidationError):
        BotConfig(token="tok", team_name="myteam")


def test_botconfig_missing_token():
    with pytest.raises(ValidationError):
        BotConfig(url="https://mm.example.com", team_name="myteam")


def test_botconfig_missing_team_name():
    with pytest.raises(ValidationError):
        BotConfig(url="https://mm.example.com", token="tok")


def test_botconfig_invalid_log_level():
    with pytest.raises(ValidationError, match="log_level"):
        BotConfig(**_valid_kwargs(), log_level="VERBOSE")


def test_botconfig_log_level_case_insensitive():
    config = BotConfig(**_valid_kwargs(), log_level="warning")
    assert config.log_level == "WARNING"


def test_config_error_is_exception():
    err = ConfigError("something went wrong")
    assert isinstance(err, Exception)
    assert str(err) == "something went wrong"
