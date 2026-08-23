"""Tests for POST /api/broadcast."""
import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    return bot


@pytest.fixture(autouse=True)
def reset_bot():
    from api import context
    original = context._bot
    yield
    context._bot = original


@pytest.fixture(autouse=True)
def mock_log_broadcast():
    with patch("api.routes.broadcast.db_module.log_broadcast"):
        yield


def test_broadcast_sends_to_all_channels():
    bot = _make_bot()
    set_bot(bot)
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello world", "channel_ids": ["id1", "id2"]},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 2
    assert data["failed"] == 0
    assert data["errors"] == []
    assert bot.driver.posts.create_post.call_count == 2


def test_broadcast_message_contains_sender():
    bot = _make_bot()
    set_bot(bot)
    client = TestClient(app)
    client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": ["id1"], "sender": "alice"},
        headers={"Authorization": "Bearer test-secret"},
    )
    posted = bot.driver.posts.create_post.call_args[0][0]
    assert "alice" in posted["message"]


def test_broadcast_reports_partial_failure():
    bot = _make_bot()
    # First call succeeds, second fails.
    bot.driver.posts.create_post.side_effect = [None, Exception("MM error")]
    set_bot(bot)
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hi", "channel_ids": ["id1", "id2"]},
        headers={"Authorization": "Bearer test-secret"},
    )
    data = resp.json()
    assert data["sent"] == 1
    assert data["failed"] == 1
    assert "id2" in data["errors"][0]


def test_broadcast_all_failed():
    bot = _make_bot()
    bot.driver.posts.create_post.side_effect = Exception("MM error")
    set_bot(bot)
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hi", "channel_ids": ["id1"]},
        headers={"Authorization": "Bearer test-secret"},
    )
    data = resp.json()
    assert data["sent"] == 0
    assert data["failed"] == 1


def test_broadcast_with_attachments_uploads_and_posts_file_ids():
    bot = _make_bot()
    bot.driver.files.upload_file.return_value = {"file_infos": [{"id": "uploaded-id"}]}
    set_bot(bot)
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={
            "message": "Hello",
            "channel_ids": ["id1"],
            "attachments": [{
                "filename": "doc.txt",
                "content_type": "text/plain",
                "content_base64": base64.b64encode(b"payload").decode("utf-8"),
            }],
        },
        headers={"Authorization": "Bearer " + bot.config.webui_api_secret},
    )
    assert resp.status_code == 200
    bot.driver.files.upload_file.assert_called_once_with(
        channel_id="id1",
        files={"files": ("doc.txt", b"payload", "text/plain")},
    )
    posted = bot.driver.posts.create_post.call_args[0][0]
    assert posted["file_ids"] == ["uploaded-id"]


def test_broadcast_requires_auth():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": ["id1"]},
    )
    assert resp.status_code == 401


def test_broadcast_wrong_secret_returns_401():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": ["id1"]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_broadcast_empty_channel_ids_returns_422():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": []},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert resp.status_code == 422
