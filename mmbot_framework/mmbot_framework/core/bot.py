"""BaseBot — the central class for building Mattermost bots."""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
from typing import Callable

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.driver import DriverFactory
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.core.session import SessionManager
from mmbot_framework.middleware.pipeline import MiddlewarePipeline
from mmbot_framework.routing.dispatcher import CommandDispatcher

logger = logging.getLogger(__name__)


class BaseBot:
    """Base class for Mattermost bots.

    Subclass it to define commands and lifecycle hooks, or use it directly
    with instance decorators.

    **Subclass example (class-based commands):**

    .. code-block:: python

        from mmbot_framework import BaseBot, BotConfig, ParsedMessage
        from mmbot_framework.config import ConfigLoader
        from mmbot_framework.routing import command
        from mmbot_framework.middleware import LoggingMiddleware, IgnoreSelfMiddleware

        class MyBot(BaseBot):
            async def on_start(self) -> None:
                print("Bot is ready!")

            @command("!ping")
            async def ping(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "pong")

            async def on_message(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "I don't understand that command.")

        config = ConfigLoader.auto_detect()
        bot = MyBot(config)
        bot.add_middleware(IgnoreSelfMiddleware(bot))
        bot.add_middleware(LoggingMiddleware())
        bot.run()

    **Decorator example (instance-based commands):**

    .. code-block:: python

        config = ConfigLoader.auto_detect()
        bot = BaseBot(config)

        @bot.command("!ping")
        async def ping(msg: ParsedMessage) -> None:
            await bot.reply(msg, "pong")

        @bot.default_handler
        async def fallback(msg: ParsedMessage) -> None:
            await bot.reply(msg, "Unknown command.")

        bot.add_middleware(IgnoreSelfMiddleware(bot))
        bot.run()
    """

    def __init__(self, config: BotConfig) -> None:
        """Args:
            config: Validated bot configuration. Use :class:`ConfigLoader` to build one.
        """
        self.config = config
        self.driver = DriverFactory.create(config)
        self.sessions = SessionManager(ttl_seconds=config.session_ttl_seconds)
        self._dispatcher = CommandDispatcher()
        self._pipeline = MiddlewarePipeline()
        self._bot_id: str | None = None

        # Discover class-level @command-decorated methods and register them.
        for name in dir(type(self)):
            method = getattr(type(self), name, None)
            if callable(method) and hasattr(method, "_command_trigger"):
                bound = getattr(self, name)
                self._dispatcher.register(method._command_trigger, bound)

    # ── Public registration API ─────────────────────────────────────────────

    def command(self, trigger: str) -> Callable:
        """Instance decorator: register an async function as a command handler.

        Use this when you prefer a functional style over subclassing::

            @bot.command("!help")
            async def help_handler(msg: ParsedMessage) -> None:
                await bot.reply(msg, "Help text here...")

        Args:
            trigger: Prefix string to match (case-insensitive ``startswith``).

        Returns:
            A decorator that registers the function and returns it unchanged.
        """

        def decorator(fn: Callable) -> Callable:
            self._dispatcher.register(trigger, fn)
            return fn

        return decorator

    @property
    def default_handler(self) -> Callable:
        """Instance decorator: register the fallback handler for unmatched messages.

        Equivalent to overriding :meth:`on_message` in a subclass::

            @bot.default_handler
            async def fallback(msg: ParsedMessage) -> None:
                await bot.reply(msg, "Unknown command.")
        """

        def decorator(fn: Callable) -> Callable:
            self._dispatcher.set_default(fn)
            return fn

        return decorator

    def add_middleware(self, middleware: Callable) -> None:
        """Add a middleware to the processing pipeline.

        Middleware is executed in the order it is added, before the dispatcher.
        Each middleware has the signature ``async (msg, call_next) -> None``.
        Not calling ``call_next`` short-circuits the chain. (this could be
        used intentionally when you want to drop messages silently. e.g. when
        the caller has reached its message quota)

        Args:
            middleware: Async callable ``(msg: ParsedMessage, call_next: Callable) -> None``.
        """
        self._pipeline.add(middleware)

    # ── Lifecycle hooks ──────────────────────────────────────────────────────

    async def on_start(self) -> None:
        """Called after driver login, before the WebSocket opens.

        Override to run setup logic (open database connections, seed caches, etc.).
        """

    async def on_stop(self) -> None:
        """Called on clean shutdown (KeyboardInterrupt / SIGTERM).

        Override to run teardown logic (close connections, flush state, etc.).
        """

    async def on_message(self, msg: ParsedMessage) -> None:
        """Fallback called when a message clears the middleware pipeline but matches no command.

        Override this or use ``@bot.default_handler`` to handle unmatched messages.

        Args:
            msg: The unmatched parsed message.
        """

    # ── Helper ───────────────────────────────────────────────────────────────

    async def reply(self, msg: ParsedMessage, text: str) -> None:
        """Post *text* back to the channel *msg* came from.

        ``mattermostdriver`` is synchronous; ``async def`` is used so callers
        can ``await`` this method uniformly.
        """
        self.driver.posts.create_post({"channel_id": msg.channel_id, "message": text})

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the bot. Blocks until interrupted (Ctrl+C).

        This method:

        1. Configures logging from :attr:`config`.
        2. Calls ``driver.login()`` and fetches the bot's own user ID.
        3. Runs the async main loop which:
           a. Awaits :meth:`on_start`.
           b. Starts the background session cleanup task.
           c. Opens the WebSocket listener (via executor so we stay in async context).
        4. On KeyboardInterrupt: awaits :meth:`on_stop` and shuts down cleanly.
        """
        self._setup_logging()
        logger.info("Bot starting up.")

        self.driver.login()
        me = self.driver.users.get_user("me")
        self._bot_id = me["id"]
        logger.info(f"Logged in as {me.get("username")} (id={self._bot_id}).")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._async_main())
        except KeyboardInterrupt:
            logger.info("Shutdown requested.")
        finally:
            loop.run_until_complete(self.on_stop())   # always called here
            pending = asyncio.all_tasks(loop)
            if pending:
                results = loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                for result in results:
                    if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                        logger.warning(f"Pending task raised during shutdown: {result}")
            loop.close()
        logger.info("Bot shut down cleanly.")

    async def _async_main(self) -> None:
        """Async entry point: lifecycle hooks, cleanup task, and WebSocket."""
        await self.on_start()
        cleanup_task = asyncio.create_task(self._session_cleanup_loop())

        def _raw_ws_handler(raw_msg: str | dict) -> None:
            raw_str = raw_msg if isinstance(raw_msg, str) else json.dumps(raw_msg)
            msg = ParsedMessage.from_raw(raw_str)
            if msg is not None:
                asyncio.run_coroutine_threadsafe(
                    self._pipeline.run(msg, self._dispatch), asyncio.get_running_loop()
                )

        try:
            logger.info("Opening WebSocket. Press Ctrl+C to stop.")
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.driver.init_websocket(_raw_ws_handler),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Interrupted. Shutting down.")
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            # on_stop() is called by run()

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _dispatch(self, msg: ParsedMessage) -> None:
        """Run the dispatcher; fall through to on_message if nothing matched."""
        matched = await self._dispatcher.dispatch(msg)
        if not matched:
            await self.on_message(msg)

    async def _session_cleanup_loop(self) -> None:
        """Background task: purge expired sessions on a fixed interval."""
        interval = self.config.session_cleanup_interval_seconds
        while True:
            await asyncio.sleep(interval)
            count = self.sessions.purge_expired()
            if count:
                logger.info(f"Session cleanup: removed {count} expired session(s).")

    def _setup_logging(self) -> None:
        """Configure the root logger from :attr:`config`."""
        level = getattr(logging, self.config.log_level, logging.INFO)
        handlers: list[logging.Handler] = [logging.StreamHandler()]
        if self.config.log_file:
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    self.config.log_file,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=3,
                )
            )
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=handlers,
            force=True,
        )
        logger.debug(
            f"Logging configured — level={self.config.log_level} file={self.config.log_file}"
        )
