"""Bot singleton shared between API routes and the FastAPI app."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import PostBot

_bot: "PostBot | None" = None


def set_bot(bot: "PostBot") -> None:
    """Store the running PostBot instance for API route access."""
    global _bot
    _bot = bot


def get_bot() -> "PostBot":
    """Return the running PostBot instance. Raises RuntimeError if not set."""
    if _bot is None:
        raise RuntimeError("PostBot not initialized before API request")
    return _bot
