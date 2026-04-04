"""TTL-based session management for per-user conversation state."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Holds conversation state for a single user.

    Attributes:
        sender_id: Mattermost user ID this session belongs to.
        data: Arbitrary bot-specific state. The bot owns the keys in this dict.
        created_at: Unix timestamp when the session was created.
        last_active: Unix timestamp of the last access via
            :meth:`SessionManager.get` or :meth:`SessionManager.get_or_create`.
            Updated on every access.
        ttl_seconds: Seconds of inactivity after which the session is expired.
    """

    sender_id: str
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    last_active: float = field(default_factory=lambda: time.time())
    ttl_seconds: int = 3600

    def is_expired(self) -> bool:
        """Return ``True`` if the session has been inactive longer than its TTL."""
        return time.time() - self.last_active > self.ttl_seconds


class SessionManager:
    """Manages TTL-bounded per-user sessions.

    Sessions expire after :attr:`Session.ttl_seconds` seconds of inactivity.
    Expiry is checked lazily on every :meth:`get` / :meth:`get_or_create` call,
    and eagerly by :meth:`purge_expired` (called by the background cleanup task
    inside :class:`BaseBot`).

    Example::

        sessions = SessionManager(ttl_seconds=3600)

        # Retrieve or create a session
        session = sessions.get_or_create("user123")
        session.data["step"] = "awaiting_confirmation"

        # Later: retrieve only if alive
        session = sessions.get("user123")
        if session is None:
            # Session expired — treat as a fresh start
            ...

        # Explicit cleanup after a completed flow
        sessions.clear("user123")
    """

    def __init__(self, ttl_seconds: int) -> None:
        """Args:
            ttl_seconds: Default TTL applied to all newly created sessions.
        """
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, sender_id: str) -> Session | None:
        """Return the live session for *sender_id*, or ``None`` if absent or expired.

        Updates :attr:`Session.last_active` on a live session.

        Args:
            sender_id: Mattermost user ID.

        Returns:
            The live :class:`Session`, or ``None``.
        """
        session = self._sessions.get(sender_id)
        if session is None:
            return None
        if session.is_expired():
            logger.debug("Session for %s expired on access; discarding.", sender_id)
            del self._sessions[sender_id]
            return None
        session.last_active = time.time()
        return session

    def get_or_create(self, sender_id: str) -> Session:
        """Return a live session or create a fresh one.

        If an expired session exists it is cleared before a new one is created,
        so the caller always receives a session with a clean ``data`` dict.

        Args:
            sender_id: Mattermost user ID.

        Returns:
            A live :class:`Session` (possibly newly created).
        """
        existing = self.get(sender_id)
        if existing is not None:
            return existing
        session = Session(sender_id=sender_id, ttl_seconds=self._ttl_seconds)
        self._sessions[sender_id] = session
        logger.debug("Created new session for %s (TTL=%ds).", sender_id, self._ttl_seconds)
        return session

    def clear(self, sender_id: str) -> None:
        """Explicitly delete the session for *sender_id*.

        Safe to call even if no session exists.

        Args:
            sender_id: Mattermost user ID.
        """
        if self._sessions.pop(sender_id, None) is not None:
            logger.debug("Session for %s explicitly cleared.", sender_id)

    def is_alive(self, sender_id: str) -> bool:
        """Return ``True`` if a non-expired session exists for *sender_id*.

        Does **not** update :attr:`Session.last_active`.

        Args:
            sender_id: Mattermost user ID.
        """
        session = self._sessions.get(sender_id)
        return session is not None and not session.is_expired()

    def purge_expired(self) -> int:
        """Remove all expired sessions.

        Called by the background cleanup task in :class:`BaseBot`.

        Returns:
            The number of sessions removed.
        """
        expired = [sid for sid, s in list(self._sessions.items()) if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]
            logger.info("Purged expired session for user %s.", sid)
        return len(expired)
