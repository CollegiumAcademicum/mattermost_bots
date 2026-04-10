"""mmbot_framework — shared library for building Mattermost bots."""

from mmbot_framework.config import BotConfig, ConfigError, ConfigLoader
from mmbot_framework.core import BaseBot, CacheManager, DriverFactory, ParsedMessage, Session, SessionManager
from mmbot_framework.middleware import IgnoreSelfMiddleware, LoggingMiddleware, MiddlewarePipeline
from mmbot_framework.routing import CommandDispatcher, command

__all__ = [
    # Config
    "BotConfig",
    "ConfigError",
    "ConfigLoader",
    # Core
    "BaseBot",
    "CacheManager",
    "DriverFactory",
    "ParsedMessage",
    "Session",
    "SessionManager",
    # Middleware
    "IgnoreSelfMiddleware",
    "LoggingMiddleware",
    "MiddlewarePipeline",
    # Routing
    "CommandDispatcher",
    "command",
]
