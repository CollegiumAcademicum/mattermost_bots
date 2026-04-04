"""ParsedMessage — a structured representation of an incoming Mattermost WebSocket event."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedMessage:
    """A parsed Mattermost ``posted`` WebSocket event.

    Attributes:
        sender_id: Mattermost user ID of the message author.
        sender_name: Username of the author (leading ``@`` stripped).
        channel_id: ID of the channel the message was posted in.
        channel_type: Channel type — ``"D"`` direct, ``"O"`` public, ``"P"`` private group.
        text: Message body, whitespace-trimmed.
        file_ids: List of attached file IDs (empty list if none).
        raw: Original WebSocket payload dict for advanced use.
    """

    sender_id: str
    sender_name: str
    channel_id: str
    channel_type: str
    text: str
    file_ids: list[str]
    raw: dict = field(repr=False)

    @classmethod
    def from_raw(cls, raw_str: str) -> ParsedMessage | None:
        """Parse a WebSocket message string into a :class:`ParsedMessage`.

        Returns ``None`` for non-``posted`` events, malformed JSON, or messages
        missing required fields (``user_id`` or ``channel_id``).

        Args:
            raw_str: Raw JSON string received from the WebSocket.

        Returns:
            A :class:`ParsedMessage` instance, or ``None`` if the message
            should be ignored.
        """
        try:
            payload = json.loads(raw_str)
        except json.JSONDecodeError:
            logger.error("Could not decode WebSocket message: %.200s", raw_str)
            return None

        if payload.get("event") != "posted":
            logger.debug("Ignoring non-post event: %r", payload.get("event"))
            return None

        data = payload.get("data", {})

        try:
            post = json.loads(data.get("post", "{}"))
        except json.JSONDecodeError:
            logger.error("Could not decode nested post payload.")
            return None

        sender_id: str = post.get("user_id", "")
        channel_id: str = post.get("channel_id", "")

        if not sender_id or not channel_id:
            logger.debug("Ignoring message with missing sender_id or channel_id.")
            return None

        return cls(
            sender_id=sender_id,
            sender_name=data.get("sender_name", "").lstrip("@"),
            channel_id=channel_id,
            channel_type=data.get("channel_type", ""),
            text=post.get("message", "").strip(),
            file_ids=post.get("file_ids", []),
            raw=payload,
        )
