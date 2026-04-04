"""Async middleware pipeline and built-in middlewares."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from mmbot_framework.core.bot import BaseBot
    from mmbot_framework.core.message import ParsedMessage

logger = logging.getLogger(__name__)

MiddlewareFn = Callable[["ParsedMessage", Callable], Awaitable[None]]
EndpointFn = Callable[["ParsedMessage"], Awaitable[None]]


class MiddlewarePipeline:
    """Chains async middleware functions before a terminal endpoint.

    Each middleware has the signature::

        async def my_middleware(msg: ParsedMessage, next: Callable) -> None:
            # pre-processing
            await next(msg)   # forward to the next middleware or endpoint
            # post-processing (optional)

    Not calling ``next`` **short-circuits** the chain — no further middleware
    or the endpoint will be called. This is useful for guards (auth, rate limiting, etc.).

    Example::

        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware())
        pipeline.add(IgnoreSelfMiddleware(bot))
        await pipeline.run(msg, dispatcher.dispatch)
    """

    def __init__(self) -> None:
        self._middlewares: list[MiddlewareFn] = []

    def add(self, middleware: MiddlewareFn) -> None:
        """Append *middleware* to the chain.

        Middleware is executed in the order it is added.

        Args:
            middleware: Async callable ``(msg, next) -> None``.
        """
        self._middlewares.append(middleware)

    async def run(self, msg: ParsedMessage, endpoint: EndpointFn) -> None:
        """Execute the middleware chain, terminating at *endpoint*.

        Args:
            msg: The incoming parsed message.
            endpoint: Final async callable invoked after all middleware passes.
        """
        index = 0

        async def _next(current_msg: ParsedMessage) -> None:
            nonlocal index
            if index < len(self._middlewares):
                mw = self._middlewares[index]
                index += 1
                await mw(current_msg, _next)
            else:
                await endpoint(current_msg)

        await _next(msg)


class LoggingMiddleware:
    """Logs every incoming message at DEBUG level and passes it through.

    Logs the sender name, channel ID, channel type, and a truncated message body.

    Example::

        bot.add_middleware(LoggingMiddleware())
    """

    async def __call__(self, msg: ParsedMessage, next: Callable) -> None:
        logger.debug(
            "Incoming message — sender=%s channel=%s (%s): %.100r",
            msg.sender_name,
            msg.channel_id,
            msg.channel_type,
            msg.text,
        )
        await next(msg)


class IgnoreSelfMiddleware:
    """Drops messages sent by the bot itself.

    You almost always want this as the first middleware so the bot does not
    react to its own posts and enter a feedback loop.

    Example::

        bot.add_middleware(IgnoreSelfMiddleware(bot))
    """

    def __init__(self, bot: BaseBot) -> None:
        """Args:
            bot: The :class:`BaseBot` instance. Its ``_bot_id`` is read at
                message-handling time, so it is safe to add this middleware
                before ``run()`` is called.
        """
        self._bot = bot

    async def __call__(self, msg: ParsedMessage, next: Callable) -> None:
        if self._bot._bot_id is not None and msg.sender_id == self._bot._bot_id:
            logger.debug("Dropping message from self (bot_id=%s).", self._bot._bot_id)
            return
        await next(msg)
