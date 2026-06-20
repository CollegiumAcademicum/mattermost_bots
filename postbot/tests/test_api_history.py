"""Tests for GET /api/history."""
from unittest.mock import MagicMock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot
import database


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    return bot


@pytest.fixture(autouse=True)
def reset_bot_and_db(tmp_path: Path):
    """Reset bot singleton and database between tests."""
    from api import context
    original = context._bot

    # Reset database
    database.close_db_connection()
    database._db_path = None
    if hasattr(database._db_local, "conn"):
        database._db_local.conn = None

    # Initialize fresh database for this test
    db_file = tmp_path / "test.db"
    database.initialize_database(db_file)

    yield

    # Cleanup after test
    database.close_db_connection()
    database._db_path = None
    if hasattr(database._db_local, "conn"):
        database._db_local.conn = None
    context._bot = original


def test_get_history_returns_empty_when_no_broadcasts():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/history", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"total": 0, "page": 1, "per_page": 20, "results": []}


def test_get_history_returns_records():
    set_bot(_make_bot())
    database.log_broadcast("alice", "hello world", ["Channel A", "Channel B"])
    client = TestClient(app)
    resp = client.get("/api/history", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    record = data["results"][0]
    assert record["sender_name"] == "alice"
    assert record["message_content"] == "hello world"
    assert record["target_channels"] == ["Channel A", "Channel B"]
    assert "timestamp" in record
    assert "id" in record


def test_get_history_pagination():
    set_bot(_make_bot())
    database.log_broadcast("user1", "msg1", ["ch1"])
    database.log_broadcast("user2", "msg2", ["ch2"])
    database.log_broadcast("user3", "msg3", ["ch3"])
    client = TestClient(app)

    # Request page 2 with per_page=2
    resp = client.get("/api/history?page=2&per_page=2", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 2
    assert data["per_page"] == 2
    assert len(data["results"]) == 1
    # Should get the oldest record (user1)
    assert data["results"][0]["sender_name"] == "user1"


def test_get_history_per_page_capped_at_100():
    set_bot(_make_bot())
    client = TestClient(app)
    # per_page > 100 should be rejected by FastAPI Query validation
    resp = client.get("/api/history?per_page=999", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 422  # Unprocessable Entity


def test_get_history_requires_auth():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/history")
    assert resp.status_code == 401


def test_get_history_wrong_secret_returns_401():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/history", headers={"Authorization": "Bearer wrong-secret"})
    assert resp.status_code == 401
