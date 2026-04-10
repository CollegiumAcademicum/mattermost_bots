"""Tests for BaseBot — command registration, reply, middleware wiring."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.bot import BaseBot
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.routing.dispatcher import command


def _config(**kwargs) -> BotConfig:
    return BotConfig(url="https://mm.example.com", token="tok", team_name="myteam", **kwargs)


def _msg(text: str = "hello", sender_id: str = "u1") -> ParsedMessage:
    return ParsedMessage(
        sender_id=sender_id,
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


def _make_bot(config: BotConfig | None = None) -> BaseBot:
    """Return a BaseBot with a mocked Driver (no network calls)."""
    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = BaseBot(config or _config())
    return bot


def test_bot_exposes_sessions():
    bot = _make_bot()
    from mmbot_framework.core.session import SessionManager
    assert isinstance(bot.sessions, SessionManager)


async def test_instance_command_decorator_registers_handler():
    bot = _make_bot()
    called = []

    @bot.command("!ping")
    async def ping(msg: ParsedMessage) -> None:
        called.append(msg.text)

    await bot._dispatcher.dispatch(_msg("!ping"))
    assert called == ["!ping"]


async def test_instance_default_handler_decorator():
    bot = _make_bot()
    called = []

    @bot.default_handler
    async def fallback(msg: ParsedMessage) -> None:
        called.append(msg.text)

    await bot._dispatcher.dispatch(_msg("!unknown"))
    assert called == ["!unknown"]


async def test_class_command_decorator_registered_on_init():
    called = []

    class MyBot(BaseBot):
        @command("!greet")
        async def greet(self, msg: ParsedMessage) -> None:
            called.append(msg.text)

    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = MyBot(_config())

    await bot._dispatcher.dispatch(_msg("!greet world"))
    assert called == ["!greet world"]


async def test_reply_calls_driver_posts_create_post():
    bot = _make_bot()
    msg = _msg()
    await bot.reply(msg, "hi there")
    bot.driver.posts.create_post.assert_called_once_with(
        {"channel_id": "c1", "message": "hi there"}
    )


async def test_add_middleware_appends_to_pipeline():
    bot = _make_bot()
    called = []

    async def mw(msg, call_next):
        called.append("mw")
        await call_next(msg)

    bot.add_middleware(mw)

    endpoint = AsyncMock()
    await bot._pipeline.run(_msg(), endpoint)
    assert called == ["mw"]
    endpoint.assert_awaited_once()


async def test_on_start_is_noop_by_default():
    bot = _make_bot()
    await bot.on_start()   # must not raise


async def test_on_stop_is_noop_by_default():
    bot = _make_bot()
    await bot.on_stop()    # must not raise


async def test_on_message_is_noop_by_default():
    bot = _make_bot()
    await bot.on_message(_msg())   # must not raise


async def test_dispatch_falls_through_to_on_message():
    received = []

    class MyBot(BaseBot):
        async def on_message(self, msg: ParsedMessage) -> None:
            received.append(msg.text)

    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = MyBot(_config())

    await bot._dispatch(_msg("unmatched"))
    assert received == ["unmatched"]


def test_lifecycle_on_start_called_before_websocket():
    """on_start must be awaited before init_websocket is called."""
    call_order = []

    class OrderBot(BaseBot):
        async def on_start(self):
            call_order.append("on_start")

    with patch("mmbot_framework.core.bot.DriverFactory") as mock_factory:
        mock_driver = MagicMock()
        mock_factory.create.return_value = mock_driver

        def fake_websocket(handler):
            call_order.append("websocket")

        mock_driver.init_websocket.side_effect = fake_websocket

        bot = OrderBot(_config())
        bot.driver = mock_driver
        bot.run()

    assert call_order.index("on_start") < call_order.index("websocket")


def test_lifecycle_on_stop_always_called():
    """on_stop must be called even if KeyboardInterrupt terminates the WebSocket."""
    on_stop_called = []

    class StopBot(BaseBot):
        async def on_stop(self):
            on_stop_called.append(True)

    with patch("mmbot_framework.core.bot.DriverFactory") as mock_factory:
        mock_driver = MagicMock()
        mock_factory.create.return_value = mock_driver

        def raise_keyboard_interrupt(handler):
            raise KeyboardInterrupt

        mock_driver.init_websocket.side_effect = raise_keyboard_interrupt

        bot = StopBot(_config())
        bot.driver = mock_driver
        bot.run()

    assert on_stop_called == [True]


def test_bot_exposes_cache():
    """BaseBot.__init__ must create a CacheManager instance."""
    from mmbot_framework.core.cache import CacheManager
    bot = _make_bot()
    assert isinstance(bot.cache, CacheManager)


async def test_cache_refresh_loop_calls_refresh_stale():
    """_cache_refresh_loop must call cache.refresh_stale after each sleep interval."""
    bot = _make_bot()
    bot.cache.refresh_stale = AsyncMock()

    call_count = 0

    async def fake_sleep(_n: float) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    with patch("mmbot_framework.core.bot.asyncio.sleep", side_effect=fake_sleep):
        try:
            await bot._cache_refresh_loop()
        except asyncio.CancelledError:
            pass

    bot.cache.refresh_stale.assert_awaited_once()
