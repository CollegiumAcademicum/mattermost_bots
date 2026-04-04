"""mmbot_framework — shared library for building Mattermost bots."""

from mmbot_framework.config import BotConfig, ConfigError, ConfigLoader
from mmbot_framework.core import BaseBot, ParsedMessage, Session, SessionManager
from mmbot_framework.middleware import IgnoreSelfMiddleware, LoggingMiddleware, MiddlewarePipeline
from mmbot_framework.routing import CommandDispatcher, command

__all__ = [
    # Config
    "BotConfig",
    "ConfigError",
    "ConfigLoader",
    # Core
    "BaseBot",
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
