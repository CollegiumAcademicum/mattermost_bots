"""Tests for GET /api/config and PUT /api/config."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot
from bot import GroupEntry, WhitelistEntry


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    bot._visible_groups = {
        "Group A": GroupEntry(channels=["id1", "id2"], aliases=["ga"]),
    }
    bot._private_groups = {
        "Private B": GroupEntry(channels=["id3"], aliases=[]),
    }
    bot._whitelist = {
        "channel-one": WhitelistEntry(id="id1", label="channel-one", aliases=["c1"]),
    }
    return bot


@pytest.fixture(autouse=True)
def reset_bot():
    """Reset bot singleton between tests."""
    from api import context
    original = context._bot
    yield
    context._bot = original


# ── GET /api/config ───────────────────────────────────────────────────────────

def test_get_config_returns_groups_and_whitelist():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/config", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert "private_groups" in data
    assert "whitelist" in data
    assert "Group A" in data["groups"]
    assert data["groups"]["Group A"]["channels"] == ["id1", "id2"]
    assert data["groups"]["Group A"]["aliases"] == ["ga"]
    assert "Private B" in data["private_groups"]
    assert "channel-one" in data["whitelist"]
    assert data["whitelist"]["channel-one"]["id"] == "id1"
    assert data["whitelist"]["channel-one"]["aliases"] == ["c1"]


def test_get_config_empty():
    bot = _make_bot()
    bot._visible_groups = {}
    bot._private_groups = {}
    bot._whitelist = {}
    set_bot(bot)
    client = TestClient(app)
    resp = client.get("/api/config", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    assert resp.json() == {"groups": {}, "private_groups": {}, "whitelist": {}}


# ── PUT /api/config ───────────────────────────────────────────────────────────

def test_put_config_updates_bot_state():
    bot = _make_bot()
    set_bot(bot)
    client = TestClient(app)

    payload = {
        "groups": {
            "NewGroup": {"channels": ["id10", "id11"], "aliases": ["ng"]},
        },
        "private_groups": {},
        "whitelist": {},
    }

    with patch.object(bot, "_save_channel_data") as mock_save, \
         patch.object(bot, "_build_alias_map") as mock_build:
        resp = client.put(
            "/api/config",
            json=payload,
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert "NewGroup" in bot._visible_groups
    assert bot._visible_groups["NewGroup"].channels == ["id10", "id11"]
    assert bot._visible_groups["NewGroup"].aliases == ["ng"]
    assert bot._private_groups == {}

    mock_save.assert_called_once()
    mock_build.assert_called_once()


def test_put_config_updates_whitelist():
    bot = _make_bot()
    set_bot(bot)
    client = TestClient(app)

    payload = {
        "groups": {},
        "private_groups": {},
        "whitelist": {
            "my-channel": {"id": "ch99", "aliases": ["mc", "mychan"]},
        },
    }

    with patch.object(bot, "_save_channel_data"), \
         patch.object(bot, "_build_alias_map"):
        resp = client.put(
            "/api/config",
            json=payload,
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert "my-channel" in bot._whitelist
    entry = bot._whitelist["my-channel"]
    assert entry.id == "ch99"
    assert entry.label == "my-channel"
    assert entry.aliases == ["mc", "mychan"]


def test_put_config_invalid_body_returns_422():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.put(
        "/api/config",
        json={"groups": "not_a_dict"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert resp.status_code == 422


# ── Auth checks ───────────────────────────────────────────────────────────────

def test_get_config_requires_auth():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/config")
    assert resp.status_code == 401


def test_put_config_requires_auth():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.put("/api/config", json={})
    assert resp.status_code == 401
