# Channel Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic TTL-based `CacheManager` to `mmbot_framework` and wire postbot's channel API calls through it, eliminating repeated per-message API lookups.

**Architecture:** `CacheManager` (new class in the framework) holds named entries, each with an async loader callable and a TTL. `BaseBot` exposes `self.cache` and runs a background refresh task. postbot registers a `"channels"` loader in `on_start()` that fetches all channels in one API sweep; all handlers read from the cache with live-API fallback on a miss.

**Tech Stack:** Python 3.14, asyncio, mmbot_framework (existing BaseBot/BotConfig patterns), Pydantic (existing config validation), mattermostdriver (sync driver).

---

## File Structure

| Action | Path | Purpose |
|---|---|---|
| Create | `mmbot_framework/mmbot_framework/core/cache.py` | `CacheEntry` dataclass + `CacheManager` class |
| Create | `mmbot_framework/tests/test_cache.py` | Unit tests for `CacheManager` |
| Modify | `mmbot_framework/mmbot_framework/core/bot.py` | Add `self.cache`, `_cache_refresh_loop`, cancel task in finally |
| Modify | `mmbot_framework/mmbot_framework/core/__init__.py` | Export `CacheManager` |
| Modify | `mmbot_framework/mmbot_framework/__init__.py` | Export `CacheManager` |
| Modify | `mmbot_framework/tests/test_bot.py` | Test `bot.cache` type + loop |
| Modify | `postbot/config.py` | Add `channel_cache_ttl_seconds: int = 3600` |
| Modify | `postbot/tests/test_config.py` | Test new config field |
| Modify | `postbot/bot.py` | Loader, on_start, !refresh_channels, handler replacements |
| Create | `postbot/tests/test_cache.py` | Test loader, refresh command, all handler cache lookups |
| Modify | `mmbot_framework/README.md` | CacheManager API section |
| Modify | `postbot/README.md` | CHANNEL_CACHE_TTL_SECONDS + !refresh_channels docs |

---

## Task 1: CacheManager class

**Files:**
- Create: `mmbot_framework/mmbot_framework/core/cache.py`
- Create: `mmbot_framework/tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# mmbot_framework/tests/test_cache.py
"""Tests for CacheManager — register, get, refresh, refresh_stale."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from mmbot_framework.core.cache import CacheManager


class TestCacheManager:
    def test_get_before_load_returns_none(self):
        cache = CacheManager()
        cache.register("test", AsyncMock(return_value={"k": "v"}), ttl=60)
        assert cache.get("test") is None

    def test_get_unknown_name_returns_none(self):
        cache = CacheManager()
        assert cache.get("nonexistent") is None

    async def test_refresh_loads_data(self):
        cache = CacheManager()
        loader = AsyncMock(return_value={"k": "v"})
        cache.register("test", loader, ttl=60)
        await cache.refresh("test")
        assert cache.get("test") == {"k": "v"}
        loader.assert_awaited_once()

    async def test_refresh_replaces_stale_data(self):
        cache = CacheManager()
        loader = AsyncMock(side_effect=[{"v": 1}, {"v": 2}])
        cache.register("test", loader, ttl=60)
        await cache.refresh("test")
        await cache.refresh("test")
        assert cache.get("test") == {"v": 2}
        assert loader.await_count == 2

    async def test_refresh_unknown_name_raises_key_error(self):
        cache = CacheManager()
        with pytest.raises(KeyError, match="nonexistent"):
            await cache.refresh("nonexistent")

    async def test_refresh_stale_skips_fresh_entries(self):
        cache = CacheManager()
        loader = AsyncMock(return_value="data")
        cache.register("test", loader, ttl=3600)
        await cache.refresh("test")
        loader.reset_mock()
        await cache.refresh_stale()
        loader.assert_not_awaited()

    async def test_refresh_stale_refreshes_expired_entries(self):
        cache = CacheManager()
        loader = AsyncMock(return_value="data")
        cache.register("test", loader, ttl=1)
        await cache.refresh("test")
        # Backdate loaded_at to simulate expiry
        cache._entries["test"].loaded_at = time.time() - 2
        loader.reset_mock()
        await cache.refresh_stale()
        loader.assert_awaited_once()

    async def test_refresh_stale_skips_never_loaded_entries(self):
        """An entry that was never loaded (loaded_at=0) IS stale and gets refreshed."""
        cache = CacheManager()
        loader = AsyncMock(return_value="data")
        cache.register("test", loader, ttl=3600)
        # loaded_at=0.0 by default → time.time() - 0 >> ttl → stale
        await cache.refresh_stale()
        loader.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/mmbot_framework
uv run --extra dev pytest tests/test_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'mmbot_framework.core.cache'`

- [ ] **Step 3: Implement `cache.py`**

```python
# mmbot_framework/mmbot_framework/core/cache.py
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
        """
        now = time.time()
        for name, entry in list(self._entries.items()):
            if now - entry.loaded_at > entry.ttl:
                logger.debug(f"Cache entry {name!r} is stale; refreshing.")
                await self.refresh(name)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /path/to/mmbot_framework
uv run --extra dev pytest tests/test_cache.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /path/to/mmbot_framework
git add mmbot_framework/core/cache.py tests/test_cache.py
git commit -m "feat(framework): add CacheManager with TTL-based named entries"
```

---

## Task 2: Integrate CacheManager into BaseBot and export it

**Files:**
- Modify: `mmbot_framework/mmbot_framework/core/bot.py`
- Modify: `mmbot_framework/mmbot_framework/core/__init__.py`
- Modify: `mmbot_framework/mmbot_framework/__init__.py`
- Modify: `mmbot_framework/tests/test_bot.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to the bottom of `mmbot_framework/tests/test_bot.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/mmbot_framework
uv run --extra dev pytest tests/test_bot.py::test_bot_exposes_cache tests/test_bot.py::test_cache_refresh_loop_calls_refresh_stale -v
```

Expected: `AttributeError: 'BaseBot' object has no attribute 'cache'`

- [ ] **Step 3: Add `self.cache` and `_cache_refresh_loop` to `bot.py`**

In `mmbot_framework/mmbot_framework/core/bot.py`, add the import at the top of the file (after the existing imports):

```python
from mmbot_framework.core.cache import CacheManager
```

In `BaseBot.__init__`, add after `self._bot_id: str | None = None`:

```python
        self.cache = CacheManager()
```

Add the `_cache_refresh_loop` method after `_session_cleanup_loop`:

```python
    async def _cache_refresh_loop(self) -> None:
        """Background task: reload stale cache entries on a fixed interval.

        Wakes every 60 seconds and calls
        :meth:`~mmbot_framework.core.cache.CacheManager.refresh_stale`, which
        reloads any named entry whose TTL has elapsed.  The 60-second poll
        interval is a fixed internal constant; freshness is controlled by the
        per-entry TTL set in :meth:`~mmbot_framework.core.cache.CacheManager.register`.
        """
        from mmbot_framework.core.cache import _POLL_INTERVAL  # noqa: PLC0415
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            await self.cache.refresh_stale()
```

In `_async_main`, start the cache task alongside `cleanup_task` and cancel it in the `finally` block.

Replace the current `_async_main` body with:

```python
    async def _async_main(self) -> None:
        """Async entry point: lifecycle hooks, cleanup task, cache task, and WebSocket."""
        await self.on_start()
        cleanup_task = asyncio.create_task(self._session_cleanup_loop())
        cache_task = asyncio.create_task(self._cache_refresh_loop())

        async def _raw_ws_handler(raw_msg: str | dict) -> None:
            raw_str = raw_msg if isinstance(raw_msg, str) else json.dumps(raw_msg)
            msg = ParsedMessage.from_raw(raw_str)
            if msg is not None:
                await self._pipeline.run(msg, self._dispatch)

        # mattermostdriver.Driver.init_websocket() is a synchronous wrapper that
        # calls loop.run_until_complete() — incompatible with an already-running
        # loop. Bypass it and await the underlying async coroutine directly.
        from mattermostdriver.websocket import Websocket  # noqa: PLC0415

        self.driver.websocket = Websocket(self.driver.options, self.driver.client.token)

        try:
            logger.info("Opening WebSocket. Press Ctrl+C to stop.")
            await self.driver.websocket.connect(_raw_ws_handler)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Interrupted. Shutting down.")
        finally:
            logger.debug("Cancelling background tasks.")
            cleanup_task.cancel()
            cache_task.cancel()
            for task in (cleanup_task, cache_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            # on_stop() is called by run()
```

- [ ] **Step 4: Export `CacheManager` from `core/__init__.py`**

Replace the entire content of `mmbot_framework/mmbot_framework/core/__init__.py` with:

```python
"""Core bot components."""

from mmbot_framework.core.bot import BaseBot
from mmbot_framework.core.cache import CacheManager
from mmbot_framework.core.driver import DriverFactory
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.core.session import Session, SessionManager

__all__ = ["BaseBot", "CacheManager", "DriverFactory", "ParsedMessage", "Session", "SessionManager"]
```

- [ ] **Step 5: Export `CacheManager` from the top-level `__init__.py`**

Replace the entire content of `mmbot_framework/mmbot_framework/__init__.py` with:

```python
"""mmbot_framework — shared library for building Mattermost bots."""

from mmbot_framework.config import BotConfig, ConfigError, ConfigLoader
from mmbot_framework.core import BaseBot, CacheManager, DriverFactory, ParsedMessage, Session, SessionManager
from mmbot_framework.middleware import IgnoreSelfMiddleware, LoggingMiddleware, MiddlewarePipeline
from mmbot_framework.routing import CommandDispatcher, command

__all__ = [
    # Config
    "BotConfig",
    "ConfigError",
    "ConfigLoader",
    # Core
    "BaseBot",
    "CacheManager",
    "DriverFactory",
    "ParsedMessage",
    "Session",
    "SessionManager",
    # Middleware
    "IgnoreSelfMiddleware",
    "LoggingMiddleware",
    "MiddlewarePipeline",
    # Routing
    "CommandDispatcher",
    "command",
]
```

- [ ] **Step 6: Run all framework tests**

```bash
cd /path/to/mmbot_framework
uv run --extra dev pytest -v
```

Expected: all tests PASS (including the two new ones).

- [ ] **Step 7: Reinstall the framework in postbot**

```bash
cd /path/to/postbot
uv sync --reinstall-package mmbot-framework
```

Expected: `Installed 1 package` with the updated mmbot-framework.

- [ ] **Step 8: Commit**

```bash
cd /path/to/mmbot_framework
git add mmbot_framework/core/bot.py mmbot_framework/core/__init__.py mmbot_framework/__init__.py tests/test_bot.py
git commit -m "feat(framework): integrate CacheManager into BaseBot, export CacheManager"
```

---

## Task 3: Add `channel_cache_ttl_seconds` to PostBotConfig

**Files:**
- Modify: `postbot/config.py`
- Modify: `postbot/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add this test class to `postbot/tests/test_config.py`:

```python
class TestChannelCacheTTL:
    def test_default_ttl_is_3600(self, minimal_config_kwargs):
        config = PostBotConfig(**minimal_config_kwargs)
        assert config.channel_cache_ttl_seconds == 3600

    def test_custom_ttl_is_accepted(self, minimal_config_kwargs):
        config = PostBotConfig(**minimal_config_kwargs, channel_cache_ttl_seconds=600)
        assert config.channel_cache_ttl_seconds == 600
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/postbot
uv run pytest tests/test_config.py::TestChannelCacheTTL -v
```

Expected: `ValidationError` — `channel_cache_ttl_seconds` is not a recognised field.

- [ ] **Step 3: Add the field to `PostBotConfig`**

In `postbot/config.py`, add `channel_cache_ttl_seconds` in the field list (after `console_log_level`):

```python
    bot_log_channel_id: str = ""
    channels_toml_path: Path = Path("channels.toml")
    db_path: Path = Path("broadcast_log.db")
    console_log_level: str = "WARNING"
    channel_cache_ttl_seconds: int = 3600
```

Also update the class docstring's `Additional attributes:` list to include:
```
        channel_cache_ttl_seconds: How long (in seconds) the channel cache is
            considered fresh before the background task refreshes it.
            Defaults to 3600 (one hour).  Set via
            ``CHANNEL_CACHE_TTL_SECONDS`` in ``.env``.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /path/to/postbot
uv run pytest tests/test_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /path/to/postbot
git add config.py tests/test_config.py
git commit -m "feat(postbot): add channel_cache_ttl_seconds config field"
```

---

## Task 4: Channel cache loader, on_start registration, and !refresh_channels command

**Files:**
- Modify: `postbot/bot.py`
- Create: `postbot/tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# postbot/tests/test_cache.py
"""Tests for PostBot channel caching: loader, on_start, !refresh_channels."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import PostBot
from config import PostBotConfig
from mmbot_framework.core.cache import CacheManager


# ---------------------------------------------------------------------------
# Shared cache data used across multiple tests
# ---------------------------------------------------------------------------

_CACHE_DATA = {
    "by_id": {
        "ch_id_1": {
            "name": "test-channel-1",
            "display_name": "Test Channel 1",
            "team_name": "Test Team",
            "team_id": "team1",
        },
        "ch_id_2": {
            "name": "test-channel-2",
            "display_name": "Test Channel 2",
            "team_name": "Test Team",
            "team_id": "team1",
        },
        "ch_id_3": {
            "name": "private-channel",
            "display_name": "Private Channel",
            "team_name": "Test Team",
            "team_id": "team1",
        },
        "whitelisted_id": {
            "name": "whitelisted",
            "display_name": "Whitelisted",
            "team_name": "Test Team",
            "team_id": "team1",
        },
    },
    "by_name": {
        "test-channel-1": "ch_id_1",
        "test-channel-2": "ch_id_2",
        "private-channel": "ch_id_3",
        "whitelisted": "whitelisted_id",
    },
    "all_rows": [
        "| `Test Channel 1` | test-channel-1 | `ch_id_1` | Test Team |",
        "| `Test Channel 2` | test-channel-2 | `ch_id_2` | Test Team |",
    ],
}


def _seed_cache(bot: PostBot) -> None:
    """Pre-populate bot.cache with _CACHE_DATA so handlers can read from it."""
    loader = AsyncMock(return_value=_CACHE_DATA)
    bot.cache.register("channels", loader, ttl=3600)
    asyncio.run(bot.cache.refresh("channels"))


# ---------------------------------------------------------------------------
# Fixtures (reuse conftest bot fixture via import)
# ---------------------------------------------------------------------------


@pytest.fixture
def config(channels_file, tmp_path):
    from pathlib import Path
    return PostBotConfig(
        url="mm.example.com",
        token="test-token",
        team_name="test-team",
        channels_toml_path=channels_file,
        db_path=tmp_path / "test.db",
        bot_log_channel_id="",
        console_log_level="WARNING",
        log_file=None,
        channel_cache_ttl_seconds=3600,
    )


@pytest.fixture
def mock_driver():
    return MagicMock()


@pytest.fixture
def bot(config, mock_driver):
    with patch("mmbot_framework.core.driver.DriverFactory.create", return_value=mock_driver):
        b = PostBot(config)
    b._team_id = "test-team-id"
    b._bot_username = "testbot"
    b._visible_groups = {"TestGroup": ["ch_id_1", "ch_id_2"]}
    b._private_groups = {"PrivateGroup": ["ch_id_3"]}
    b._whitelist = {"ch_id_1", "ch_id_2", "ch_id_3", "whitelisted_id"}
    return b


def _last_post(bot: PostBot) -> str:
    return bot.driver.posts.create_post.call_args_list[-1][0][0]["message"]


# ---------------------------------------------------------------------------
# Tests for _load_channel_cache
# ---------------------------------------------------------------------------


class TestLoadChannelCache:
    async def test_builds_by_id_and_by_name(self, bot):
        bot.driver.teams.get_user_teams.return_value = [
            {"id": "team1", "display_name": "Test Team"}
        ]
        bot.driver.channels.get_channels_for_user.return_value = [
            {
                "id": "ch1",
                "name": "general",
                "display_name": "General",
                "team_id": "team1",
            },
            {
                "id": "ch2",
                "name": "random",
                "display_name": "Random",
                "team_id": "team1",
            },
        ]

        result = await bot._load_channel_cache()

        assert result["by_id"]["ch1"] == {
            "name": "general",
            "display_name": "General",
            "team_name": "Test Team",
            "team_id": "team1",
        }
        assert result["by_name"]["general"] == "ch1"
        assert result["by_name"]["random"] == "ch2"
        assert len(result["all_rows"]) == 2

    async def test_skips_channels_without_team_id(self, bot):
        """DM and group-message channels have an empty team_id and must be excluded."""
        bot.driver.teams.get_user_teams.return_value = [
            {"id": "team1", "display_name": "Test Team"}
        ]
        bot.driver.channels.get_channels_for_user.return_value = [
            {
                "id": "dm1",
                "name": "dm-channel",
                "display_name": "DM",
                "team_id": "",
            },
        ]

        result = await bot._load_channel_cache()

        assert "dm1" not in result["by_id"]
        assert "dm-channel" not in result["by_name"]
        assert result["all_rows"] == []

    async def test_covers_multiple_teams(self, bot):
        bot.driver.teams.get_user_teams.return_value = [
            {"id": "t1", "display_name": "Team A"},
            {"id": "t2", "display_name": "Team B"},
        ]
        bot.driver.channels.get_channels_for_user.side_effect = [
            [{"id": "c1", "name": "alpha", "display_name": "Alpha", "team_id": "t1"}],
            [{"id": "c2", "name": "beta", "display_name": "Beta", "team_id": "t2"}],
        ]

        result = await bot._load_channel_cache()

        assert result["by_id"]["c1"]["team_name"] == "Team A"
        assert result["by_id"]["c2"]["team_name"] == "Team B"


# ---------------------------------------------------------------------------
# Tests for !refresh_channels command
# ---------------------------------------------------------------------------


class TestRefreshChannelsCommand:
    async def test_refresh_channels_calls_cache_refresh(self, bot, make_msg):
        bot.cache.refresh = AsyncMock()
        msg = make_msg(text="!refresh_channels")
        await bot._handle_refresh_channels(msg)
        bot.cache.refresh.assert_awaited_once_with("channels")

    async def test_refresh_channels_replies_with_timestamp(self, bot, make_msg):
        bot.cache.refresh = AsyncMock()
        msg = make_msg(text="!refresh_channels")
        await bot._handle_refresh_channels(msg)
        reply = _last_post(bot)
        assert "✅" in reply
        assert "UTC" in reply

    async def test_refresh_channels_driver_not_called_directly(self, bot, make_msg):
        """The handler must delegate to cache.refresh, not call the driver itself."""
        bot.cache.refresh = AsyncMock()
        msg = make_msg(text="!refresh_channels")
        await bot._handle_refresh_channels(msg)
        bot.driver.teams.get_user_teams.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/postbot
uv run pytest tests/test_cache.py -v
```

Expected: `AttributeError: 'PostBot' object has no attribute '_load_channel_cache'`

- [ ] **Step 3: Add `_load_channel_cache` to `PostBot`**

Add this method to `PostBot` in `postbot/bot.py`, after `_add_group_impl` and before `_load_channel_data`:

```python
    async def _load_channel_cache(self) -> dict:
        """Fetch all channel data from the Mattermost API in one sweep.

        Called by :attr:`~mmbot_framework.BaseBot.cache` automatically on TTL
        expiry and on demand via ``!refresh_channels``.  Never call directly —
        use :meth:`~mmbot_framework.core.cache.CacheManager.refresh` instead.

        The returned dict has three keys:

        - ``"by_id"`` — maps channel ID → info dict with ``name``,
          ``display_name``, ``team_name``, and ``team_id``.
        - ``"by_name"`` — maps channel system name → channel ID.
        - ``"all_rows"`` — pre-formatted Markdown table rows for ``!channels``,
          built here so ``!channels`` is a zero-API-call string join.

        Returns:
            Dict with keys ``"by_id"``, ``"by_name"``, ``"all_rows"``.
        """
        by_id: dict[str, dict] = {}
        by_name: dict[str, str] = {}
        all_rows: list[str] = []

        teams = self.driver.teams.get_user_teams("me")
        for team in teams:
            team_name = team.get("display_name", "N/A")
            channels = self.driver.channels.get_channels_for_user("me", team["id"])
            for ch in channels:
                if not ch.get("team_id"):
                    continue  # skip DM / group-message channels
                cid = ch["id"]
                info = {
                    "name": ch["name"],
                    "display_name": ch["display_name"],
                    "team_name": team_name,
                    "team_id": ch["team_id"],
                }
                by_id[cid] = info
                by_name[ch["name"]] = cid
                all_rows.append(
                    f"| `{ch['display_name']}` | {ch['name']} "
                    f"| `{cid}` | {team_name} |"
                )

        logger.info(f"Channel cache loaded: {len(by_id)} channel(s).")
        return {"by_id": by_id, "by_name": by_name, "all_rows": all_rows}
```

- [ ] **Step 4: Register the loader in `on_start`**

In `PostBot.on_start()`, add these two lines after `self._load_channel_data()`:

```python
        self.cache.register(
            "channels", self._load_channel_cache, ttl=self.config.channel_cache_ttl_seconds
        )
        await self.cache.refresh("channels")
        logger.info("Channel cache pre-warmed.")
```

- [ ] **Step 5: Add `_handle_refresh_channels` and register the command**

Add the handler method to `PostBot`, after `_handle_add_private_group`:

```python
    async def _handle_refresh_channels(self, msg: ParsedMessage) -> None:
        """Force-reload the channel cache immediately.

        Triggered by: ``!refresh_channels``

        Any user can trigger this.  Useful when channels have been created,
        renamed, or deleted since the last automatic refresh.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} triggered channel cache refresh.")
        await self.cache.refresh("channels")
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        self._post(msg.channel_id, f"✅ Channel cache refreshed at **{ts} UTC**.")
```

In `PostBot.__init__`, add the command registration alongside the others:

```python
        self._dispatcher.register("!refresh_channels", self._handle_refresh_channels)
```

- [ ] **Step 6: Run the new tests**

```bash
cd /path/to/postbot
uv run pytest tests/test_cache.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run the full postbot test suite**

```bash
cd /path/to/postbot
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
cd /path/to/postbot
git add bot.py tests/test_cache.py
git commit -m "feat(postbot): add channel cache loader, on_start registration, !refresh_channels command"
```

---

## Task 5: Replace API calls with cache lookups in all handlers

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/test_cache.py`

- [ ] **Step 1: Add failing tests for cache-backed handlers**

Append these test classes to `postbot/tests/test_cache.py`:

```python
# ---------------------------------------------------------------------------
# Tests for cache-backed handlers
# ---------------------------------------------------------------------------


class TestHandleChannelsWithCache:
    async def test_uses_cache_rows_no_driver_calls(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        bot.driver.teams.get_user_teams.assert_not_called()
        bot.driver.channels.get_channels_for_user.assert_not_called()

    async def test_reply_contains_all_rows(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        reply = _last_post(bot)
        assert "Test Channel 1" in reply
        assert "Test Channel 2" in reply

    async def test_warns_when_cache_empty(self, bot, make_msg):
        # cache not seeded — get("channels") returns None
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        reply = _last_post(bot)
        assert "⚠️" in reply


class TestHandleIdWithCache:
    async def test_resolves_name_from_cache(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="!id test-channel-1")
        await bot._handle_id(msg)
        bot.driver.channels.get_channel_by_name.assert_not_called()
        reply = _last_post(bot)
        assert "ch_id_1" in reply

    async def test_falls_back_to_api_on_cache_miss(self, bot, make_msg):
        _seed_cache(bot)
        bot.driver.channels.get_channel_by_name.return_value = {"id": "new_id"}
        msg = make_msg(text="!id brand-new-channel")
        await bot._handle_id(msg)
        bot.driver.channels.get_channel_by_name.assert_called_once()
        reply = _last_post(bot)
        assert "new_id" in reply
        assert "!refresh_channels" in reply  # stale-cache notice


class TestHandleGetGroupsWithCache:
    async def test_resolves_channel_names_from_cache(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="!get_groups")
        await bot._handle_get_groups(msg)
        bot.driver.channels.get_channel.assert_not_called()
        reply = _last_post(bot)
        assert "TestGroup" in reply

    async def test_falls_back_to_api_on_cache_miss(self, bot, make_msg):
        # cache not seeded — IDs not in cache → fallback to driver
        bot.driver.channels.get_channel.return_value = {"name": "fallback-name"}
        msg = make_msg(text="!get_groups")
        await bot._handle_get_groups(msg)
        assert bot.driver.channels.get_channel.call_count > 0


class TestHandleGetPrivateGroupsWithCache:
    async def test_resolves_channel_names_from_cache(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="!get_private_groups")
        await bot._handle_get_private_groups(msg)
        bot.driver.channels.get_channel.assert_not_called()

    async def test_falls_back_to_api_on_cache_miss(self, bot, make_msg):
        bot.driver.channels.get_channel.return_value = {"name": "fallback-name"}
        msg = make_msg(text="!get_private_groups")
        await bot._handle_get_private_groups(msg)
        assert bot.driver.channels.get_channel.call_count > 0


class TestHandleNewSessionWithCache:
    async def test_whitelist_display_uses_cache(self, bot, make_msg):
        _seed_cache(bot)
        msg = make_msg(text="Hello world broadcast")
        bot._known_users.add(msg.sender_id)
        await bot._handle_new_session(msg)
        bot.driver.channels.get_channel.assert_not_called()
        bot.driver.teams.get_team.assert_not_called()
        reply = _last_post(bot)
        assert "Test Channel 1" in reply or "test-channel-1" in reply

    async def test_whitelist_falls_back_to_api_on_cache_miss(self, bot, make_msg):
        # cache not seeded
        bot.driver.channels.get_channel.return_value = {
            "name": "ch", "display_name": "Ch", "team_id": "t1"
        }
        bot.driver.teams.get_team.return_value = {"display_name": "T"}
        msg = make_msg(text="Hello world broadcast")
        bot._known_users.add(msg.sender_id)
        await bot._handle_new_session(msg)
        assert bot.driver.channels.get_channel.call_count > 0


class TestResolveTargetsWithCache:
    def test_resolves_channel_name_from_cache(self, bot):
        _seed_cache(bot)
        valid_ids, valid_names, invalid = bot._resolve_targets({"test-channel-1"})
        bot.driver.channels.get_channel_by_name.assert_not_called()
        assert "ch_id_1" in valid_ids

    def test_falls_back_to_api_on_name_cache_miss(self, bot):
        _seed_cache(bot)
        bot.driver.channels.get_channel_by_name.return_value = {"id": "whitelisted_id"}
        valid_ids, _, _ = bot._resolve_targets({"not-in-cache"})
        bot.driver.channels.get_channel_by_name.assert_called_once()

    def test_resolves_display_name_from_cache(self, bot):
        _seed_cache(bot)
        _, valid_names, _ = bot._resolve_targets({"TestGroup"})
        bot.driver.channels.get_channel.assert_not_called()
        assert "Test Channel 1" in valid_names or "Test Channel 2" in valid_names
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd /path/to/postbot
uv run pytest tests/test_cache.py::TestHandleChannelsWithCache tests/test_cache.py::TestHandleIdWithCache -v
```

Expected: FAIL — `_handle_channels` still makes driver calls.

- [ ] **Step 3: Replace `_handle_channels`**

Replace the entire `_handle_channels` method in `postbot/bot.py`:

```python
    async def _handle_channels(self, msg: ParsedMessage) -> None:
        """List all Mattermost channels the bot has access to.

        Reads from the channel cache (populated at startup and refreshed every
        ``channel_cache_ttl_seconds``).  If the cache is not yet loaded, the
        user is asked to retry or run ``!refresh_channels``.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested the channel list.")
        ch_cache = self.cache.get("channels")
        if ch_cache is None:
            self._post(
                msg.channel_id,
                "⚠️ Channel cache not yet loaded. Please try again shortly "
                "or run `!refresh_channels`.",
            )
            return
        lines = [
            "| display_name | name | ID | team_name |",
            "| :--- | :--- | :--- | :--- |",
        ] + ch_cache["all_rows"]
        self._post(msg.channel_id, "\n".join(lines))
```

- [ ] **Step 4: Replace `_handle_id`**

Replace the entire `_handle_id` method:

```python
    async def _handle_id(self, msg: ParsedMessage) -> None:
        """Look up and return the Mattermost channel ID for a given channel name.

        Usage: ``!id <channel-name>``

        Reads from the channel cache first.  Falls back to a live API call on a
        cache miss and appends a notice suggesting ``!refresh_channels``.

        Args:
            msg: The incoming message.  The channel name is the text after the
                ``!id`` prefix (system name, e.g. ``town-square``).
        """
        channel_name = msg.text[len("!id"):].strip()
        if not channel_name:
            logger.warning(
                f"User @{msg.sender_name} used !id without a channel name."
            )
            self._post(
                msg.channel_id,
                "Please provide a channel name after `!id`, "
                "e.g. `!id town-square`.",
            )
            return

        logger.info(
            f"User @{msg.sender_name} requested ID for channel {channel_name!r}."
        )

        ch_cache = self.cache.get("channels")
        channel_id = ch_cache["by_name"].get(channel_name) if ch_cache else None

        if channel_id is not None:
            self._post(
                msg.channel_id,
                f"The ID for channel `{channel_name}` is: `{channel_id}`",
            )
            return

        # Cache miss: fall back to live API.
        logger.warning(
            f"Cache miss for channel name {channel_name!r}; falling back to live API."
        )
        try:
            channel = self.driver.channels.get_channel_by_name(
                self._team_id, channel_name
            )
            channel_id = channel["id"]
        except Exception as exc:
            logger.error(f"Could not find channel {channel_name!r}: {exc}")
            self._post(
                msg.channel_id,
                f"⚠️ Could not find a channel named `{channel_name}`.",
            )
            return

        self._post(
            msg.channel_id,
            f"The ID for channel `{channel_name}` is: `{channel_id}`\n"
            f"⚠️ This channel was not in the cache — run `!refresh_channels` to update.",
        )
```

- [ ] **Step 5: Replace `_handle_get_groups`**

Replace the entire `_handle_get_groups` method:

```python
    async def _handle_get_groups(self, msg: ParsedMessage) -> None:
        """List all visible channel groups and their resolved channel names.

        Reads channel names from the cache.  Falls back to a live API call per
        channel on a cache miss.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested visible groups.")
        ch_cache = self.cache.get("channels")
        lines: list[str] = []
        for name, channel_ids in self._visible_groups.items():
            resolved: list[str] = []
            for cid in channel_ids:
                if ch_cache and cid in ch_cache["by_id"]:
                    resolved.append(ch_cache["by_id"][cid]["name"])
                else:
                    logger.warning(
                        f"Cache miss for channel {cid!r} in group {name!r}; "
                        f"falling back to live API."
                    )
                    try:
                        resolved.append(self.driver.channels.get_channel(cid)["name"])
                    except Exception as exc:
                        logger.error(
                            f"Error resolving channel {cid!r} for group {name!r}: {exc}"
                        )
                        resolved.append(f"(error: {cid})")
            lines.append(f"**{name}:** {resolved}\n")
        self._post(
            msg.channel_id,
            "\n".join(lines) if lines else "No groups configured.",
        )
```

- [ ] **Step 6: Replace `_handle_get_private_groups`**

Replace the entire `_handle_get_private_groups` method:

```python
    async def _handle_get_private_groups(self, msg: ParsedMessage) -> None:
        """List all private channel groups and their resolved channel names.

        Reads channel names from the cache.  Falls back to a live API call per
        channel on a cache miss.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested private groups.")
        ch_cache = self.cache.get("channels")
        lines: list[str] = []
        for name, channel_ids in self._private_groups.items():
            resolved: list[str] = []
            for cid in channel_ids:
                if ch_cache and cid in ch_cache["by_id"]:
                    resolved.append(ch_cache["by_id"][cid]["name"])
                else:
                    logger.warning(
                        f"Cache miss for channel {cid!r} in private group {name!r}; "
                        f"falling back to live API."
                    )
                    try:
                        resolved.append(self.driver.channels.get_channel(cid)["name"])
                    except Exception as exc:
                        logger.error(
                            f"Error resolving channel {cid!r} for private group "
                            f"{name!r}: {exc}"
                        )
                        resolved.append(f"(error: {cid})")
            lines.append(f"**{name}:** {resolved}\n")
        self._post(
            msg.channel_id,
            "\n".join(lines) if lines else "No private groups configured.",
        )
```

- [ ] **Step 7: Replace the whitelist-display section of `_handle_new_session`**

Replace the block inside `_handle_new_session` that builds `allowed_channels` (from
`allowed_channels: list[str] = []` through `allowed_channels.sort()`):

```python
        # Build the displayed list of whitelisted channels.
        ch_cache = self.cache.get("channels")
        allowed_channels: list[str] = []
        for channel_id in self._whitelist:
            if ch_cache and channel_id in ch_cache["by_id"]:
                info = ch_cache["by_id"][channel_id]
                allowed_channels.append(
                    f"- name: `{info['name']}`    "
                    f"(display name: `{info['display_name']}` — "
                    f"ID: `{channel_id}` — team: `{info['team_name']}`)"
                )
            else:
                logger.warning(
                    f"Cache miss for whitelisted channel {channel_id!r}; "
                    f"falling back to live API."
                )
                try:
                    info = self.driver.channels.get_channel(channel_id)
                    team_name = (
                        self.driver.teams.get_team(info["team_id"]).get(
                            "display_name", "N/A"
                        )
                        if info["team_id"]
                        else "N/A"
                    )
                    allowed_channels.append(
                        f"- name: `{info['name']}`    "
                        f"(display name: `{info['display_name']}` — "
                        f"ID: `{channel_id}` — team: `{team_name}`)"
                    )
                except Exception as exc:
                    logger.error(
                        f"Error fetching info for channel {channel_id!r}: {exc}"
                    )
                    allowed_channels.append(f"- `(ID not found)` (`{channel_id}`)")
        allowed_channels.sort()
```

- [ ] **Step 8: Replace `_resolve_targets`**

Replace the entire `_resolve_targets` method:

```python
    def _resolve_targets(
        self, inputs: set[str]
    ) -> tuple[list[str], list[str], list[str]]:
        """Resolve user-supplied channel names, IDs, and group names to channel IDs.

        Lookup order for each non-group input:

        1. Check the channel cache (``by_name`` lookup) — zero API calls.
        2. On a cache miss, call ``get_channel_by_name`` and log a warning.
        3. If the API call also fails, treat the input as a raw ID.
        4. Reject any resolved ID not in :attr:`_whitelist`.

        Display names are resolved from the cache (``by_id`` lookup), with a
        live ``get_channel`` fallback on a miss.

        Args:
            inputs: Raw user inputs, typically split on commas.

        Returns:
            A three-tuple ``(valid_ids, valid_names, invalid_names)``.
        """
        ch_cache = self.cache.get("channels")
        all_groups: dict[str, list[str]] = {
            **self._visible_groups,
            **self._private_groups,
        }
        valid_ids: set[str] = set()
        invalid_inputs: set[str] = set()

        for item in inputs:
            stripped = item.strip()
            if stripped in all_groups:
                valid_ids.update(all_groups[stripped])
                logger.debug(
                    f"Resolved group {stripped!r} to {all_groups[stripped]}."
                )
            else:
                clean = stripped.lower().lstrip("#")

                # Try cache first.
                channel_id = (
                    ch_cache["by_name"].get(clean) if ch_cache else None
                )

                if channel_id is None:
                    # Cache miss: fall back to live API.
                    logger.warning(
                        f"Cache miss for {clean!r}; falling back to live API. "
                        f"Run !refresh_channels to update the cache."
                    )
                    try:
                        channel = self.driver.channels.get_channel_by_name(
                            self._team_id, clean
                        )
                        channel_id = channel["id"]
                    except Exception:
                        channel_id = clean
                        logger.debug(
                            f"Could not resolve {clean!r} as a channel name; "
                            f"treating as raw ID."
                        )

                if channel_id in self._whitelist:
                    valid_ids.add(channel_id)
                else:
                    invalid_inputs.add(stripped)
                    logger.warning(
                        f"Channel {stripped!r} (resolved to {channel_id!r}) "
                        f"is not in the whitelist."
                    )

        valid_names: list[str] = []
        for cid in valid_ids:
            if ch_cache and cid in ch_cache["by_id"]:
                valid_names.append(ch_cache["by_id"][cid]["display_name"])
            else:
                logger.warning(
                    f"Cache miss for display name of {cid!r}; "
                    f"falling back to live API."
                )
                try:
                    valid_names.append(
                        self.driver.channels.get_channel(cid)["display_name"]
                    )
                except Exception:
                    valid_names.append(cid)
                    logger.warning(
                        f"Could not get display name for channel {cid!r}."
                    )

        return list(valid_ids), valid_names, list(invalid_inputs)
```

- [ ] **Step 9: Run all tests**

```bash
cd /path/to/postbot
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
cd /path/to/postbot
git add bot.py tests/test_cache.py
git commit -m "feat(postbot): replace per-request API calls with channel cache lookups"
```

---

## Task 6: Update READMEs

**Files:**
- Modify: `mmbot_framework/README.md`
- Modify: `postbot/README.md`

- [ ] **Step 1: Add a `## Caching` section to `mmbot_framework/README.md`**

Insert the following section between the `## Sessions` and `## Lifecycle hooks` sections:

```markdown
## Caching

`BaseBot` exposes a `cache` attribute (`CacheManager`) for storing data that is
expensive to fetch on every request.  Each named entry has an async **loader**
callable and a **TTL**; a background task refreshes stale entries every 60 seconds.

### Registering a cache entry

Call `cache.register()` in `on_start()`, then `await cache.refresh()` to
pre-warm the entry before the WebSocket opens:

```python
class MyBot(BaseBot):

    async def on_start(self) -> None:
        self.cache.register("users", self._load_users, ttl=300)
        await self.cache.refresh("users")   # pre-warm at startup

    async def _load_users(self) -> dict:
        """Fetch all users and index them by ID."""
        return {u["id"]: u for u in self.driver.users.get_users()}
```

### Reading cached data

Use `cache.get(name)` inside command handlers.  It returns `None` if the entry
has never been loaded:

```python
    @command("!whoami")
    async def whoami(self, msg: ParsedMessage) -> None:
        users = self.cache.get("users")
        if users is None:
            await self.reply(msg, "Cache not ready — try again shortly.")
            return
        name = users.get(msg.sender_id, {}).get("username", "unknown")
        await self.reply(msg, f"You are @{name}")
```

### Forcing a refresh

Call `await cache.refresh(name)` to reload a single entry immediately (e.g.
from a `!refresh` command):

```python
    @command("!refresh_users")
    async def refresh_users(self, msg: ParsedMessage) -> None:
        await self.cache.refresh("users")
        await self.reply(msg, "User cache refreshed.")
```

### CacheManager API

| Method | Description |
|---|---|
| `register(name, loader, ttl)` | Register a named entry with an async loader and TTL (seconds). |
| `get(name)` | Return cached data or `None` if not yet loaded. |
| `refresh(name)` | Force-reload the named entry. Raises `KeyError` if not registered. |
| `refresh_stale()` | Reload all entries whose TTL has elapsed. Called by the background task. |
```

- [ ] **Step 2: Add caching docs to `postbot/README.md`**

In the `## Configuration` section, add `CHANNEL_CACHE_TTL_SECONDS` to the `.env` example block, after `SESSION_CLEANUP_INTERVAL_SECONDS`:

```dotenv
CHANNEL_CACHE_TTL_SECONDS=3600  # How long the channel cache stays fresh (seconds)
```

Add `!refresh_channels` to the **Bot Commands** table:

```markdown
| `!refresh_channels` | Force-reload the channel cache immediately |
```

Add a **Channel Cache** subsection after the **Broadcast Log** section:

```markdown
## Channel Cache

At startup the bot fetches all channel and team data in one API sweep and stores
it in memory.  All command handlers (`!channels`, `!id`, `!get_groups`,
`!get_private_groups`, and the broadcast wizard) read from this cache instead of
calling the Mattermost API on every request.

The cache is refreshed automatically in the background every
`CHANNEL_CACHE_TTL_SECONDS` seconds (default: 3600 / one hour).  If a channel
has been created or renamed since the last refresh, any user can force an
immediate reload with `!refresh_channels`.

On a cache miss (a channel that was created after the last refresh), the bot
falls back to a live API call and appends a note suggesting `!refresh_channels`.
```

- [ ] **Step 3: Commit**

```bash
cd /path/to/mattermost_bots
git add mmbot_framework/README.md postbot/README.md
git commit -m "docs: document CacheManager in framework README, channel cache in postbot README"
```
