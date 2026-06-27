"""Command routing — maps trigger strings to async handler functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from mmbot_framework.core.message import ParsedMessage

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


def command(trigger: str) -> Callable[[Handler], Handler]:
    """Marks a method as a command handler by attaching its trigger string.

    Use this inside a :class:`BaseBot` subclass. :class:`BaseBot` discovers
    marked methods in ``__init__`` and registers them with its dispatcher
    automatically::

        class MyBot(BaseBot):
            @command("!help")
            async def help_handler(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "Help text here...")

    Args:
        trigger: Prefix to match (case-insensitive ``startswith``).

    Returns:
        The original method unchanged, with ``_command_trigger`` set to *trigger*.
    """

    def decorator(fn: Handler) -> Handler:
        fn._command_trigger = trigger  # type: ignore[attr-defined]
        return fn

    return decorator


class CommandDispatcher:
    """Routes incoming messages to registered async handler functions.

    Matching uses ``msg.text.lower().startswith(trigger)`` checked in
    registration order. The first match wins.

    Can be used standalone or via :class:`BaseBot`::

        dispatcher = CommandDispatcher()
        dispatcher.register("!ping", ping_handler)
        matched = await dispatcher.dispatch(msg)
    """

    def __init__(self) -> None:
        self._commands: list[tuple[str, Handler]] = []
        self._default: Handler | None = None
        self._max_trigger_len: int = 0

    def register(self, trigger: str, handler: Handler) -> None:
        """Register *handler* for messages starting with *trigger*.

        Args:
            trigger: Prefix string (case-insensitive).
            handler: Async callable ``(msg: ParsedMessage) -> None``.
        """
        logger.debug("Registering command handler for trigger %r.", trigger)
        t = trigger.lower()
        self._commands.append((t, handler))
        self._max_trigger_len = max(self._max_trigger_len, len(t))

    def set_default(self, handler: Handler) -> None:
        """Set the fallback handler invoked when no command matches.

        Equivalent to overriding :meth:`BaseBot.on_message`.

        Args:
            handler: Async callable ``(msg: ParsedMessage) -> None``.
        """
        self._default = handler

    async def dispatch(self, msg: ParsedMessage) -> bool:
        """Dispatch *msg* to the first matching handler.

        Args:
            msg: The parsed incoming message.

        Returns:
            ``True`` if a handler (or the default) was invoked,
            ``False`` if no command matched and no default is set.
        """
        prefix = msg.text[:self._max_trigger_len].lower()

        for trigger, handler in self._commands:
            if prefix.startswith(trigger):
                logger.debug("Matched trigger %r for message %r.", trigger, msg.text[:50])
                await handler(msg)
                return True

        if self._default is not None:
            logger.debug("No command matched; invoking default handler.")
            await self._default(msg)
            return True

        logger.debug("No command matched and no default handler registered.")
        return False
