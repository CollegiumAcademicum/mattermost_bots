"""Tests for CommandDispatcher and the @command class decorator."""

import pytest

from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.routing.dispatcher import CommandDispatcher, command


def _msg(text: str = "hello") -> ParsedMessage:
    return ParsedMessage(
        sender_id="u1",
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


async def test_dispatch_calls_matching_handler():
    called_with = []

    async def handler(msg: ParsedMessage) -> None:
        called_with.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    result = await dispatcher.dispatch(_msg("!ping"))
    assert result is True
    assert called_with == ["!ping"]


async def test_dispatch_matches_prefix_not_exact():
    called = []

    async def handler(msg):
        called.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.register("!help", handler)
    await dispatcher.dispatch(_msg("!help me please"))
    assert called == ["!help me please"]


async def test_dispatch_is_case_insensitive():
    called = []

    async def handler(msg):
        called.append(True)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    await dispatcher.dispatch(_msg("!PING"))
    assert called == [True]


async def test_dispatch_first_match_wins():
    order = []

    async def h1(msg):
        order.append("h1")

    async def h2(msg):
        order.append("h2")

    dispatcher = CommandDispatcher()
    dispatcher.register("!p", h1)
    dispatcher.register("!ping", h2)
    await dispatcher.dispatch(_msg("!ping"))
    assert order == ["h1"]  # "!p" is a prefix of "!ping"


async def test_dispatch_returns_false_when_no_match():
    dispatcher = CommandDispatcher()
    result = await dispatcher.dispatch(_msg("!unknown"))
    assert result is False


async def test_dispatch_calls_default_handler_on_no_match():
    called = []

    async def fallback(msg):
        called.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.set_default(fallback)
    result = await dispatcher.dispatch(_msg("anything"))
    assert result is True
    assert called == ["anything"]


async def test_dispatch_does_not_call_default_when_command_matched():
    default_called = []

    async def handler(msg):
        pass

    async def fallback(msg):
        default_called.append(True)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    dispatcher.set_default(fallback)
    await dispatcher.dispatch(_msg("!ping"))
    assert default_called == []


def test_command_decorator_sets_trigger_on_method():
    class MyBot:
        @command("!help")
        async def help_handler(self, msg):
            pass

    assert MyBot.help_handler._command_trigger == "!help"


async def test_command_decorator_methods_are_discovered_by_base_bot():
    """BaseBot.__init__ scans for _command_trigger and registers methods."""
    # We test the scanning logic directly without importing BaseBot to keep this isolated.
    called = []

    class FakeBot:
        def __init__(self):
            self._dispatcher = CommandDispatcher()
            for name in dir(type(self)):
                method = getattr(type(self), name, None)
                if callable(method) and hasattr(method, "_command_trigger"):
                    bound = getattr(self, name)
                    self._dispatcher.register(method._command_trigger, bound)

        @command("!ping")
        async def ping(self, msg):
            called.append(msg.text)

    bot = FakeBot()
    await bot._dispatcher.dispatch(_msg("!ping"))
    assert called == ["!ping"]
