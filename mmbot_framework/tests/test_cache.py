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

    async def test_refresh_stale_refreshes_never_loaded_entries(self):
        """An entry that was never loaded (loaded_at=0) IS stale and gets refreshed."""
        cache = CacheManager()
        loader = AsyncMock(return_value="data")
        cache.register("test", loader, ttl=3600)
        # loaded_at=0.0 by default → time.time() - 0 >> ttl → stale
        await cache.refresh_stale()
        loader.assert_awaited_once()
