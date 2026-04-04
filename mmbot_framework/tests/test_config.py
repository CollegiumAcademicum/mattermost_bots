"""Tests for BotConfig schema validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mmbot_framework.config.loader import ConfigLoader
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
    assert config.session_cleanup_interval_seconds == 60


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


def test_botconfig_invalid_port():
    with pytest.raises(ValidationError):
        BotConfig(**_valid_kwargs(), port=0)


def test_botconfig_invalid_port_too_high():
    with pytest.raises(ValidationError):
        BotConfig(**_valid_kwargs(), port=99999)


def test_config_error_is_exception():
    err = ConfigError("something went wrong")
    assert isinstance(err, Exception)
    assert str(err) == "something went wrong"


# ── ConfigLoader tests ───────────────────────────────────────────────────────

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_from_file_env(tmp_path):
    p = _write(tmp_path, ".env", "URL=https://mm.example.com\nTOKEN=tok\nTEAM_NAME=myteam\n")
    config = ConfigLoader.from_file(p)
    assert isinstance(config, BotConfig)
    assert config.url == "https://mm.example.com"
    assert config.token == "tok"


def test_from_file_toml(tmp_path):
    p = _write(
        tmp_path,
        "config.toml",
        'url = "https://mm.example.com"\ntoken = "tok"\nteam_name = "myteam"\n',
    )
    config = ConfigLoader.from_file(p)
    assert config.team_name == "myteam"


def test_from_file_json(tmp_path):
    p = _write(
        tmp_path,
        "config.json",
        json.dumps({"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}),
    )
    config = ConfigLoader.from_file(p)
    assert config.token == "tok"


def test_from_file_unsupported_extension(tmp_path):
    p = _write(tmp_path, "config.yaml", "url: https://mm.example.com")
    with pytest.raises(ConfigError, match="Unsupported"):
        ConfigLoader.from_file(p)


def test_from_file_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        ConfigLoader.from_file("/nonexistent/path/.env")


def test_from_file_missing_required_field(tmp_path):
    p = _write(tmp_path, "config.json", json.dumps({"url": "https://mm.example.com"}))
    with pytest.raises(ConfigError, match="Invalid configuration"):
        ConfigLoader.from_file(p)


def test_auto_detect_prefers_env_over_toml(tmp_path):
    _write(tmp_path, ".env", "URL=https://env.example.com\nTOKEN=tok\nTEAM_NAME=myteam\n")
    _write(tmp_path, "config.toml", 'url = "https://toml.example.com"\ntoken = "tok"\nteam_name = "myteam"\n')
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.url == "https://env.example.com"


def test_auto_detect_falls_back_to_toml(tmp_path):
    _write(tmp_path, "config.toml", 'url = "https://mm.example.com"\ntoken = "tok"\nteam_name = "myteam"\n')
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.url == "https://mm.example.com"


def test_auto_detect_falls_back_to_json(tmp_path):
    _write(
        tmp_path,
        "config.json",
        json.dumps({"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}),
    )
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.team_name == "myteam"


def test_auto_detect_raises_when_no_file(tmp_path):
    with pytest.raises(ConfigError, match="No config file found"):
        ConfigLoader.auto_detect(tmp_path)


def test_from_file_keys_are_case_insensitive(tmp_path):
    p = _write(
        tmp_path,
        "config.json",
        json.dumps({"URL": "https://mm.example.com", "TOKEN": "tok", "TEAM_NAME": "myteam"}),
    )
    config = ConfigLoader.from_file(p)
    assert config.url == "https://mm.example.com"
