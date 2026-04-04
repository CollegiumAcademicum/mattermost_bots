"""Smoke tests for the public API surface."""


def test_top_level_imports():
    from mmbot_framework import (
        BaseBot,
        BotConfig,
        CommandDispatcher,
        ConfigError,
        ConfigLoader,
        IgnoreSelfMiddleware,
        LoggingMiddleware,
        MiddlewarePipeline,
        ParsedMessage,
        Session,
        SessionManager,
        command,
    )
    assert BaseBot is not None
    assert BotConfig is not None
    assert CommandDispatcher is not None
    assert ConfigError is not None
    assert ConfigLoader is not None
    assert IgnoreSelfMiddleware is not None
    assert LoggingMiddleware is not None
    assert MiddlewarePipeline is not None
    assert ParsedMessage is not None
    assert Session is not None
    assert SessionManager is not None
    assert command is not None


def test_subpackage_imports():
    from mmbot_framework.config import BotConfig, ConfigError, ConfigLoader
    from mmbot_framework.core import BaseBot, DriverFactory, ParsedMessage, Session, SessionManager
    from mmbot_framework.middleware import IgnoreSelfMiddleware, LoggingMiddleware, MiddlewarePipeline
    from mmbot_framework.routing import CommandDispatcher, command
    assert DriverFactory is not None
