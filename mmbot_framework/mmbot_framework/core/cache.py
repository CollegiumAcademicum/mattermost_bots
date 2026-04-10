"""Generic TTL-based cache with named entries and async loaders.

Register named entries with an async loader and a TTL.  The background task
inside :class:`~mmbot_framework.BaseBot` calls :meth:`CacheManager.refresh_stale`
every 60 seconds to keep data fresh automatically.  Any code can force an
immediate reload with :meth:`CacheManager.refresh`.

Example::

    class MyBot(BaseBot):

        async def on_start(self) -> None:
            self.cache.register("users", self._load_users, ttl=300)
            await self.cache.refresh("users")   # eager load at startup

        async def _load_users(self) -> dict:
            return {u["id"]: u for u in self.driver.users.get_users()}

        @command("!whoami")
        async def whoami(self, msg: ParsedMessage) -> None:
            users = self.cache.get("users") or {}
            name = users.get(msg.sender_id, {}).get("username", "unknown")
            await self.reply(msg, f"You are @{name}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# How often the background task wakes to check for stale entries (seconds).
# Operators control freshness via the per-entry TTL, not this constant.
_POLL_INTERVAL: int = 60


@dataclass
class CacheEntry:
    """Internal state for a single named cache entry.

    Attributes:
        loader: Async callable that fetches fresh data.  Must accept no
            arguments and return the value to cache.
        ttl: Seconds after which the entry is considered stale.
        data: The cached value.  ``None`` until the first :meth:`CacheManager.refresh`.
        loaded_at: Unix timestamp of the last successful load.  ``0.0`` until
            the first load, which guarantees the entry is treated as stale.
    """

    loader: Callable[[], Awaitable[Any]]
    ttl: float
    data: Any = None
    loaded_at: float = field(default=0.0)


class CacheManager:
    """Manages named TTL-based caches with async loaders.

    Each entry is identified by a string name, carries an async loader, and
    has its own TTL.  The :class:`~mmbot_framework.BaseBot` background task
    calls :meth:`refresh_stale` every 60 seconds.  Use :meth:`refresh` to
    force an immediate reload from any command handler.

    Typical usage inside a :class:`~mmbot_framework.BaseBot` subclass::

        # In on_start():
        self.cache.register("channels", self._load_channels, ttl=3600)
        await self.cache.refresh("channels")   # pre-warm before WebSocket opens

        # In a command handler:
        data = self.cache.get("channels")
        if data is None:
            await self.reply(msg, "Cache not ready yet.")
            return
        ...
    """

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}

    def register(
        self,
        name: str,
        loader: Callable[[], Awaitable[Any]],
        ttl: float,
    ) -> None:
        """Register a named cache entry.

        Safe to call multiple times with the same name — the existing entry is
        replaced.  Call :meth:`refresh` after registering to pre-warm the cache.

        Args:
            name: Unique key for this cache entry.
            loader: Async callable (no arguments) that returns the value to
                cache.  Called by :meth:`refresh` and :meth:`refresh_stale`.
            ttl: Seconds after which the cached value is considered stale.
        """
        self._entries[name] = CacheEntry(loader=loader, ttl=ttl)
        logger.debug(f"Cache entry {name!r} registered (TTL={ttl}s).")

    def get(self, name: str) -> Any:
        """Return the cached value for *name*, or ``None`` if not yet loaded.

        Does **not** trigger a refresh.  If the entry has never been loaded
        (e.g. :meth:`refresh` has not been called yet) this returns ``None``.

        Args:
            name: The cache entry name passed to :meth:`register`.

        Returns:
            The cached value, or ``None`` if the entry is unknown or unloaded.
        """
        entry = self._entries.get(name)
        return entry.data if entry is not None else None

    async def refresh(self, name: str) -> None:
        """Force-reload the named entry by calling its loader.

        Args:
            name: The cache entry name passed to :meth:`register`.

        Raises:
            KeyError: If *name* was never registered.
        """
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"No cache entry registered for {name!r}.")
        logger.info(f"Refreshing cache entry {name!r}.")
        entry.data = await entry.loader()
        entry.loaded_at = time.time()
        logger.debug(f"Cache entry {name!r} refreshed at {entry.loaded_at:.0f}.")

    async def refresh_stale(self) -> None:
        """Reload all entries whose TTL has elapsed (including never-loaded entries).

        Called periodically by the background task in
        :class:`~mmbot_framework.BaseBot`.  An entry is stale when
        ``time.time() - loaded_at > ttl``; since ``loaded_at`` starts at
        ``0.0``, a never-loaded entry is always stale.

        Raises:
            Any exception raised by a loader propagates directly.  The caller
            (typically the ``BaseBot`` background task) is responsible for
            catching and logging errors so that a single failed refresh does
            not terminate the loop.
        """
        now = time.time()
        for name, entry in list(self._entries.items()):
            if now - entry.loaded_at > entry.ttl:
                logger.debug(f"Cache entry {name!r} is stale; refreshing.")
                await self.refresh(name)
