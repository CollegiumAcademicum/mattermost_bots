"""Tests for DriverFactory."""

from unittest.mock import MagicMock, patch

import pytest

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.driver import DriverFactory


def _config(**kwargs) -> BotConfig:
    return BotConfig(url="https://mm.example.com", token="mytoken", team_name="myteam", **kwargs)


def test_driver_factory_passes_correct_params():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        MockDriver.return_value = MagicMock()
        DriverFactory.create(_config())
        MockDriver.assert_called_once_with(
            {"url": "https://mm.example.com", "token": "mytoken", "scheme": "https", "port": 443}
        )


def test_driver_factory_respects_custom_scheme_and_port():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        MockDriver.return_value = MagicMock()
        DriverFactory.create(_config(scheme="http", port=8065))
        call_kwargs = MockDriver.call_args[0][0]
        assert call_kwargs["scheme"] == "http"
        assert call_kwargs["port"] == 8065


def test_driver_factory_does_not_call_login():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        mock_driver = MagicMock()
        MockDriver.return_value = mock_driver
        DriverFactory.create(_config())
        mock_driver.login.assert_not_called()


def test_driver_factory_returns_driver_instance():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        mock_driver = MagicMock()
        MockDriver.return_value = mock_driver
        result = DriverFactory.create(_config())
        assert result is mock_driver
