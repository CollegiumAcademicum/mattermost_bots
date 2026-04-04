"""Tests for MiddlewarePipeline, LoggingMiddleware, and IgnoreSelfMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.middleware.pipeline import (
    IgnoreSelfMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
)


def _msg(sender_id: str = "u1", text: str = "hello") -> ParsedMessage:
    return ParsedMessage(
        sender_id=sender_id,
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


async def test_pipeline_calls_endpoint_when_no_middleware():
    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    msg = _msg()
    await pipeline.run(msg, endpoint)
    endpoint.assert_awaited_once_with(msg)


async def test_pipeline_calls_middleware_in_order():
    order = []

    async def mw1(msg, next):
        order.append("mw1")
        await next(msg)

    async def mw2(msg, next):
        order.append("mw2")
        await next(msg)

    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    pipeline.add(mw1)
    pipeline.add(mw2)
    await pipeline.run(_msg(), endpoint)
    assert order == ["mw1", "mw2"]
    endpoint.assert_awaited_once()


async def test_pipeline_short_circuits_when_next_not_called():
    endpoint = AsyncMock()
    second_mw = AsyncMock()

    async def guard(msg, next):
        return  # does not call next

    pipeline = MiddlewarePipeline()
    pipeline.add(guard)
    pipeline.add(second_mw)
    await pipeline.run(_msg(), endpoint)
    endpoint.assert_not_awaited()
    second_mw.assert_not_awaited()


async def test_pipeline_middleware_can_modify_message():
    received = []

    async def mw(msg, next):
        modified = ParsedMessage(
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            channel_id=msg.channel_id,
            channel_type=msg.channel_type,
            text=msg.text.upper(),
            file_ids=msg.file_ids,
            raw=msg.raw,
        )
        await next(modified)

    async def endpoint(msg):
        received.append(msg.text)

    pipeline = MiddlewarePipeline()
    pipeline.add(mw)
    await pipeline.run(_msg(text="hello"), endpoint)
    assert received == ["HELLO"]


async def test_logging_middleware_calls_next():
    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    pipeline.add(LoggingMiddleware())
    await pipeline.run(_msg(), endpoint)
    endpoint.assert_awaited_once()


async def test_ignore_self_middleware_drops_bot_messages():
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = "bot123"

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="bot123"), endpoint)
    endpoint.assert_not_awaited()


async def test_ignore_self_middleware_passes_other_users():
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = "bot123"

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="user456"), endpoint)
    endpoint.assert_awaited_once()


async def test_ignore_self_middleware_passes_when_bot_id_not_set():
    """Before login, _bot_id is None — messages should pass through."""
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = None

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="anyuser"), endpoint)
    endpoint.assert_awaited_once()
