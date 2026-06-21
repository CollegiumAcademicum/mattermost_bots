"""Tests for /api/tasks endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot
from task_runner import TaskEntry, TaskRegistry


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    bot.config.bot_log_channel_id = None
    bot.config.scheduler_toml_path = None
    return bot


def _make_registry() -> TaskRegistry:
    async def _noop(driver): pass

    entry1 = TaskEntry(name="example_task", run=_noop, description="Sends weekly digest")
    entry1.last_run = datetime(2026, 6, 21, 2, 0, 0, tzinfo=timezone.utc)
    entry2 = TaskEntry(name="cleanup_old_logs", run=_noop)  # description defaults to "—"
    return TaskRegistry(
        tasks={"example_task": entry1, "cleanup_old_logs": entry2},
        schedule={"example_task": "0 9 * * 1"},
    )


@pytest.fixture(autouse=True)
def reset_bot():
    from api import context
    original = context._bot
    yield
    context._bot = original


def test_get_tasks_returns_list():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.get("/api/tasks", headers={"Authorization": "Bearer test-secret"})

    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert len(data["tasks"]) == 2
    names = {t["name"] for t in data["tasks"]}
    assert names == {"example_task", "cleanup_old_logs"}


def test_get_tasks_scheduled_task_has_cron():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.get("/api/tasks", headers={"Authorization": "Bearer test-secret"})

    tasks_by_name = {t["name"]: t for t in resp.json()["tasks"]}
    assert tasks_by_name["example_task"]["schedule"] == "0 9 * * 1"
    assert tasks_by_name["example_task"]["last_run"] == "2026-06-21T02:00:00+00:00"
    assert tasks_by_name["example_task"]["description"] == "Sends weekly digest"


def test_get_tasks_unscheduled_task_has_nulls():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.get("/api/tasks", headers={"Authorization": "Bearer test-secret"})

    tasks_by_name = {t["name"]: t for t in resp.json()["tasks"]}
    assert tasks_by_name["cleanup_old_logs"]["schedule"] is None
    assert tasks_by_name["cleanup_old_logs"]["last_run"] is None


def test_run_task_unknown_returns_404():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.post(
        "/api/tasks/nonexistent/run",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert resp.status_code == 404


def test_run_task_dispatches_and_returns_ok():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    with patch("api.routes.tasks.task_runner_module._fire_task", new_callable=AsyncMock) as mock_fire:
        resp = client.post(
            "/api/tasks/example_task/run",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_fire.assert_called_once()
    call_args = mock_fire.call_args[0]
    assert call_args[0].name == "example_task"  # TaskEntry
