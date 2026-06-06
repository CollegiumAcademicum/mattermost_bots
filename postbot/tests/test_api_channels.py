"""Tests for GET /api/channels."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot
from bot import GroupEntry


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    bot._visible_groups = {
        "Group A": GroupEntry(channels=["id1", "id2"], aliases=[]),
    }
    bot._private_groups = {
        "Private B": GroupEntry(channels=["id3"], aliases=[]),
    }
    bot.cache.get.return_value = {
        "by_id": {
            "id1": {"display_name": "Channel One", "name": "channel-one", "team_name": "T", "team_id": "t1"},
            "id2": {"display_name": "Channel Two", "name": "channel-two", "team_name": "T", "team_id": "t1"},
            "id3": {"display_name": "Private Channel", "name": "private-ch", "team_name": "T", "team_id": "t1"},
        },
        "by_name": {},
        "all_rows": [],
    }
    return bot


@pytest.fixture(autouse=True)
def reset_bot():
    """Reset bot singleton between tests."""
    from api import context
    original = context._bot
    yield
    context._bot = original


def test_get_channels_returns_groups():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert "Group A" in data["groups"]
    assert any(c["id"] == "id1" for c in data["groups"]["Group A"])
    assert any(c["id"] == "id2" for c in data["groups"]["Group A"])


def test_get_channels_includes_display_and_channel_name():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer test-secret"})
    ch = resp.json()["groups"]["Group A"][0]
    assert ch["display_name"] == "Channel One"
    assert ch["channel_name"] == "channel-one"


def test_get_channels_includes_private_groups():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer test-secret"})
    assert "Private B" in resp.json()["private_groups"]


def test_get_channels_individual_channels_deduped_and_sorted():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer test-secret"})
    individual = resp.json()["individual_channels"]
    ids = [c["id"] for c in individual]
    # All three unique IDs present (deduplication)
    assert set(ids) == {"id1", "id2", "id3"}
    # Sorted by display_name: "Channel One" < "Channel Two" < "Private Channel"
    names = [c["display_name"] for c in individual]
    assert names == sorted(names)


def test_get_channels_missing_auth_returns_401():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels")
    assert resp.status_code == 401


def test_get_channels_wrong_secret_returns_401():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_get_channels_unconfigured_secret_returns_503():
    set_bot(_make_bot(secret=""))
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == 503


def test_get_channels_empty_cache_uses_id_as_fallback():
    bot = _make_bot()
    # Simulate cache returning None (not yet populated)
    bot.cache.get.return_value = None
    set_bot(bot)
    client = TestClient(app)
    resp = client.get("/api/channels", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    # Channels should still appear, falling back to ID as display_name and channel_name
    channels = data["groups"]["Group A"]
    assert len(channels) == 2
    for ch in channels:
        # When cache is empty, display_name and channel_name should fall back to id
        assert ch["display_name"] == ch["id"]
        assert ch["channel_name"] == ch["id"]
