# Tasks Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Aufgaben" tab to the admin dashboard where BotAdmins can view all tasks, trigger them manually, and edit their cron schedules.

**Architecture:** Three new FastAPI endpoints in `postbot/api/routes/tasks.py` → three new Django `admin_client` methods → new `views/tasks.py` → `tasks.html` template with inline cron editor. The "Aufgaben" tab appears in-page alongside Verlauf and Konfiguration across all three admin dashboard templates.

**Tech Stack:** FastAPI, Pydantic, croniter, toml, Django, Bulma CSS, vanilla JS

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `postbot/api/routes/tasks.py` | GET /api/tasks, POST /api/tasks/{name}/run, PUT /api/tasks/{name}/schedule |
| Create | `postbot/tests/test_api_tasks.py` | Tests for all three API endpoints |
| Modify | `postbot/api/app.py` | Register tasks router |
| Modify | `webui/broadcast/admin_dashboard/services/admin_client.py` | Add get_tasks(), run_task(), set_task_schedule() |
| Create | `webui/broadcast/admin_dashboard/views/tasks.py` | Tasks view (GET + POST) |
| Modify | `webui/broadcast/admin_dashboard/urls.py` | Add tasks/ route |
| Create | `webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html` | Aufgaben tab template |
| Modify | `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html` | Add in-page tab nav |
| Modify | `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html` | Add in-page tab nav |
| Modify | `webui/broadcast/templates/base.html` | Add Aufgaben link to navbar |
| Modify | `webui/tests/test_admin_dashboard.py` | Add admin_client + view tests |

---

## Task 1: GET /api/tasks endpoint

**Files:**
- Create: `postbot/api/routes/tasks.py`
- Create: `postbot/tests/test_api_tasks.py`

- [ ] **Step 1: Write the failing test**

Create `postbot/tests/test_api_tasks.py`:

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py -v
```

Expected: `ImportError` or `404` — `api/routes/tasks.py` does not exist yet.

- [ ] **Step 3: Create the routes file with GET /api/tasks**

Create `postbot/api/routes/tasks.py`:

```python
"""GET /api/tasks, POST /api/tasks/{name}/run, PUT /api/tasks/{name}/schedule."""
import asyncio

import toml
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


@router.get("/api/tasks", dependencies=[Depends(verify_api_secret)])
def get_tasks() -> dict:
    """Return all discovered tasks with their schedule and last-run time."""
    bot = get_bot()
    registry = bot._task_registry
    tasks = []
    for entry in registry.all_tasks():
        tasks.append({
            "name": entry.name,
            "description": entry.description,
            "last_run": entry.last_run.isoformat() if entry.last_run else None,
            "schedule": registry.schedule.get(entry.name),
        })
    return {"tasks": tasks}
```

Note: the router is not registered yet — that happens in Task 4.

- [ ] **Step 4: Register the router temporarily for this test run**

Edit `postbot/api/app.py` — add the tasks import and `include_router` call:

```python
"""FastAPI application for the postbot HTTP API."""
from fastapi import FastAPI

app = FastAPI(title="postbot API", docs_url=None, redoc_url=None)

# Import routers after app creation to avoid circular imports.
from api.routes import broadcast, channels, config, history, tasks  # noqa: E402

app.include_router(channels.router)
app.include_router(broadcast.router)
app.include_router(history.router)
app.include_router(config.router)
app.include_router(tasks.router)
```

- [ ] **Step 5: Run the GET tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py::test_get_tasks_returns_list tests/test_api_tasks.py::test_get_tasks_scheduled_task_has_cron tests/test_api_tasks.py::test_get_tasks_unscheduled_task_has_nulls -v
```

Expected: PASS (3 tests)

---

## Task 2: POST /api/tasks/{name}/run endpoint

**Files:**
- Modify: `postbot/api/routes/tasks.py`
- Modify: `postbot/tests/test_api_tasks.py`

- [ ] **Step 1: Write the failing tests**

Append to `postbot/tests/test_api_tasks.py`:

```python
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

    with patch("api.routes.tasks.task_runner._fire_task", new_callable=AsyncMock) as mock_fire:
        resp = client.post(
            "/api/tasks/example_task/run",
            headers={"Authorization": "Bearer test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_fire.assert_called_once()
    call_args = mock_fire.call_args[0]
    assert call_args[0].name == "example_task"  # TaskEntry
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py::test_run_task_unknown_returns_404 tests/test_api_tasks.py::test_run_task_dispatches_and_returns_ok -v
```

Expected: FAIL — endpoint does not exist yet.

- [ ] **Step 3: Add the run endpoint to tasks.py**

Add to `postbot/api/routes/tasks.py`, after the `get_tasks` function:

```python
import task_runner as task_runner_module  # alias to allow patching in tests


@router.post("/api/tasks/{name}/run", dependencies=[Depends(verify_api_secret)])
async def run_task(name: str) -> dict:
    """Manually trigger a task. Fire-and-forget — returns immediately."""
    bot = get_bot()
    registry = bot._task_registry
    entry = registry.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Task {name!r} not found.")
    asyncio.create_task(
        task_runner_module._fire_task(
            entry,
            bot.driver,
            bot._post,
            bot.config.bot_log_channel_id,
        )
    )
    return {"ok": True}
```

Also add the alias import at the top of the file (replace the plain `import` section):

```python
"""GET /api/tasks, POST /api/tasks/{name}/run, PUT /api/tasks/{name}/schedule."""
import asyncio

import toml
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import task_runner as task_runner_module
from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()
```

- [ ] **Step 4: Run the run-task tests**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py::test_run_task_unknown_returns_404 tests/test_api_tasks.py::test_run_task_dispatches_and_returns_ok -v
```

Expected: PASS (2 tests)

---

## Task 3: PUT /api/tasks/{name}/schedule endpoint

**Files:**
- Modify: `postbot/api/routes/tasks.py`
- Modify: `postbot/tests/test_api_tasks.py`

- [ ] **Step 1: Write the failing tests**

Append to `postbot/tests/test_api_tasks.py`:

```python
def test_set_schedule_unknown_task_returns_404():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.put(
        "/api/tasks/nonexistent/schedule",
        json={"cron": "0 9 * * 1"},
        headers={"Authorization": "Bearer test-secret"},
    )

    assert resp.status_code == 404


def test_set_schedule_invalid_cron_returns_422():
    bot = _make_bot()
    bot._task_registry = _make_registry()
    set_bot(bot)
    client = TestClient(app)

    resp = client.put(
        "/api/tasks/example_task/schedule",
        json={"cron": "not-a-cron"},
        headers={"Authorization": "Bearer test-secret"},
    )

    assert resp.status_code == 422
    assert "Invalid cron" in resp.json()["detail"]


def test_set_schedule_valid_cron_updates_registry_and_writes_file(tmp_path):
    import toml as toml_module

    scheduler_file = tmp_path / "scheduler.toml"
    registry = _make_registry()
    bot = _make_bot()
    bot._task_registry = registry
    bot.config.scheduler_toml_path = scheduler_file
    set_bot(bot)
    client = TestClient(app)

    resp = client.put(
        "/api/tasks/example_task/schedule",
        json={"cron": "0 8 * * 1"},
        headers={"Authorization": "Bearer test-secret"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert registry.schedule["example_task"] == "0 8 * * 1"
    data = toml_module.load(scheduler_file)
    assert data["tasks"]["example_task"] == "0 8 * * 1"


def test_set_schedule_null_removes_from_registry_and_file(tmp_path):
    import toml as toml_module

    scheduler_file = tmp_path / "scheduler.toml"
    registry = _make_registry()  # example_task is scheduled
    bot = _make_bot()
    bot._task_registry = registry
    bot.config.scheduler_toml_path = scheduler_file
    set_bot(bot)
    client = TestClient(app)

    resp = client.put(
        "/api/tasks/example_task/schedule",
        json={"cron": None},
        headers={"Authorization": "Bearer test-secret"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "example_task" not in registry.schedule
    data = toml_module.load(scheduler_file)
    assert "example_task" not in data.get("tasks", {})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py::test_set_schedule_unknown_task_returns_404 tests/test_api_tasks.py::test_set_schedule_invalid_cron_returns_422 tests/test_api_tasks.py::test_set_schedule_valid_cron_updates_registry_and_writes_file tests/test_api_tasks.py::test_set_schedule_null_removes_from_registry_and_file -v
```

Expected: FAIL — endpoint does not exist yet.

- [ ] **Step 3: Add the schedule endpoint to tasks.py**

Add after the `run_task` function. The full `postbot/api/routes/tasks.py` now looks like this:

```python
"""GET /api/tasks, POST /api/tasks/{name}/run, PUT /api/tasks/{name}/schedule."""
import asyncio

import toml
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import task_runner as task_runner_module
from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


@router.get("/api/tasks", dependencies=[Depends(verify_api_secret)])
def get_tasks() -> dict:
    """Return all discovered tasks with their schedule and last-run time."""
    bot = get_bot()
    registry = bot._task_registry
    tasks = []
    for entry in registry.all_tasks():
        tasks.append({
            "name": entry.name,
            "description": entry.description,
            "last_run": entry.last_run.isoformat() if entry.last_run else None,
            "schedule": registry.schedule.get(entry.name),
        })
    return {"tasks": tasks}


@router.post("/api/tasks/{name}/run", dependencies=[Depends(verify_api_secret)])
async def run_task(name: str) -> dict:
    """Manually trigger a task. Fire-and-forget — returns immediately."""
    bot = get_bot()
    registry = bot._task_registry
    entry = registry.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Task {name!r} not found.")
    asyncio.create_task(
        task_runner_module._fire_task(
            entry,
            bot.driver,
            bot._post,
            bot.config.bot_log_channel_id,
        )
    )
    return {"ok": True}


class SchedulePayload(BaseModel):
    cron: str | None


@router.put("/api/tasks/{name}/schedule", dependencies=[Depends(verify_api_secret)])
def set_task_schedule(name: str, payload: SchedulePayload) -> dict:
    """Set or remove a task's cron schedule, persisting to scheduler.toml."""
    bot = get_bot()
    registry = bot._task_registry
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Task {name!r} not found.")

    if payload.cron is not None:
        if not croniter.is_valid(payload.cron):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid cron expression: {payload.cron!r}",
            )
        registry.schedule[name] = payload.cron
    else:
        registry.schedule.pop(name, None)

    with open(bot.config.scheduler_toml_path, "w", encoding="utf-8") as fh:
        toml.dump({"tasks": registry.schedule}, fh)

    return {"ok": True}
```

- [ ] **Step 4: Run all tasks API tests**

```bash
cd postbot && uv run pytest tests/test_api_tasks.py -v
```

Expected: PASS (all 9 tests)

- [ ] **Step 5: Run the full postbot test suite to check for regressions**

```bash
cd postbot && uv run pytest -v
```

Expected: all tests pass (no regressions from adding the router in app.py).

- [ ] **Step 6: Commit**

```bash
git add postbot/api/routes/tasks.py postbot/api/app.py postbot/tests/test_api_tasks.py
git commit -m "feat(postbot): add /api/tasks GET/run/schedule endpoints"
```

---

## Task 4: Django admin_client methods

**Files:**
- Modify: `webui/broadcast/admin_dashboard/services/admin_client.py`
- Modify: `webui/tests/test_admin_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Append to `webui/tests/test_admin_dashboard.py`:

```python
MOCK_TASKS = {
    "tasks": [
        {
            "name": "example_task",
            "description": "Sends weekly digest",
            "last_run": "2026-06-21T02:00:00+00:00",
            "schedule": "0 9 * * 1",
        },
        {
            "name": "cleanup_old_logs",
            "description": "—",
            "last_run": None,
            "schedule": None,
        },
    ]
}


class AdminClientTasksTest(TestCase):
    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_tasks_calls_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TASKS
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.get_tasks()

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "/api/tasks" in call_url
        assert result == MOCK_TASKS

    @patch("broadcast.admin_dashboard.services.admin_client.requests.post")
    def test_run_task_calls_correct_url(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.run_task("example_task")

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/tasks/example_task/run" in call_url
        assert result == {"ok": True}

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_set_task_schedule_calls_correct_url(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.set_task_schedule("example_task", "0 9 * * 1")

        mock_put.assert_called_once()
        call_url = mock_put.call_args[0][0]
        assert "/api/tasks/example_task/schedule" in call_url
        call_json = mock_put.call_args[1]["json"]
        assert call_json == {"cron": "0 9 * * 1"}
        assert result == {"ok": True}

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_set_task_schedule_null_sends_none(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        admin_client.set_task_schedule("example_task", None)

        call_json = mock_put.call_args[1]["json"]
        assert call_json == {"cron": None}
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd webui && uv run python manage.py test tests.test_admin_dashboard.AdminClientTasksTest -v 2
```

Expected: `AttributeError` — `get_tasks`, `run_task`, `set_task_schedule` not defined yet.

- [ ] **Step 3: Add the three methods to admin_client.py**

Append to `webui/broadcast/admin_dashboard/services/admin_client.py`:

```python
def get_tasks() -> dict:
    """Fetch task list from postbot.

    Returns dict with key: tasks (list of {name, description, last_run, schedule}).
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.get(
        f"{settings.POSTBOT_API_URL}/api/tasks",
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def run_task(name: str) -> dict:
    """Trigger a task manually (fire-and-forget).

    Returns {"ok": True} on success.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.post(
        f"{settings.POSTBOT_API_URL}/api/tasks/{name}/run",
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def set_task_schedule(name: str, cron: str | None) -> dict:
    """Set or remove a task's cron schedule.

    Pass cron=None to remove the schedule.
    Returns {"ok": True} on success.
    Raises requests.HTTPError on non-2xx response (including 422 for bad cron).
    """
    resp = requests.put(
        f"{settings.POSTBOT_API_URL}/api/tasks/{name}/schedule",
        json={"cron": cron},
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: Run the admin_client tests**

```bash
cd webui && uv run python manage.py test tests.test_admin_dashboard.AdminClientTasksTest -v 2
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add webui/broadcast/admin_dashboard/services/admin_client.py webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): add get_tasks/run_task/set_task_schedule to admin_client"
```

---

## Task 5: Django tasks view and URL

**Files:**
- Create: `webui/broadcast/admin_dashboard/views/tasks.py`
- Modify: `webui/broadcast/admin_dashboard/urls.py`
- Modify: `webui/tests/test_admin_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Append to `webui/tests/test_admin_dashboard.py`:

```python
class TasksViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("admin", password="pw")
        group = Group.objects.create(name="BotAdmins")
        self.user.groups.add(group)
        self.client.login(username="admin", password="pw")

    def test_tasks_get_renders_task_list(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            return_value=MOCK_TASKS,
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["tasks"]), 2)
        self.assertEqual(resp.context["tasks"][0]["name"], "example_task")

    def test_tasks_get_formats_last_run(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            return_value=MOCK_TASKS,
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        tasks_by_name = {t["name"]: t for t in resp.context["tasks"]}
        self.assertIn("2026", tasks_by_name["example_task"]["last_run_display"])
        self.assertEqual(tasks_by_name["cleanup_old_logs"]["last_run_display"], "Noch nie")

    def test_tasks_get_on_api_error_shows_empty_list(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            side_effect=Exception("connection refused"),
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["tasks"], [])

    def test_tasks_post_run_calls_run_task_and_redirects(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.run_task",
            return_value={"ok": True},
        ) as mock_run:
            resp = self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "run", "name": "example_task"},
            )

        mock_run.assert_called_once_with("example_task")
        self.assertRedirects(resp, "/admin-dashboard/tasks/")

    def test_tasks_post_set_schedule_calls_set_schedule_and_redirects(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.set_task_schedule",
            return_value={"ok": True},
        ) as mock_set:
            resp = self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "set_schedule", "name": "example_task", "cron": "0 8 * * 1"},
            )

        mock_set.assert_called_once_with("example_task", "0 8 * * 1")
        self.assertRedirects(resp, "/admin-dashboard/tasks/")

    def test_tasks_post_set_schedule_empty_cron_sends_none(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.set_task_schedule",
            return_value={"ok": True},
        ) as mock_set:
            self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "set_schedule", "name": "example_task", "cron": ""},
            )

        mock_set.assert_called_once_with("example_task", None)
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd webui && uv run python manage.py test tests.test_admin_dashboard.TasksViewTest -v 2
```

Expected: `404` — URL not registered yet.

- [ ] **Step 3: Create the view**

Create `webui/broadcast/admin_dashboard/views/tasks.py`:

```python
from datetime import datetime

import requests
from django.contrib import messages
from django.shortcuts import redirect, render

from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin


def _format_last_run(last_run_str: str | None) -> str:
    if not last_run_str:
        return "Noch nie"
    dt = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
    return dt.strftime("%d.%m.%Y %H:%M UTC")


@require_bot_admin
def tasks_view(request):
    if request.method == "POST":
        action = request.POST.get("action")
        name = request.POST.get("name", "")

        if action == "run":
            try:
                admin_client.run_task(name)
                messages.success(request, f"Aufgabe '{name}' gestartet.")
            except Exception as exc:
                messages.error(request, f"Fehler beim Starten von '{name}': {exc}")

        elif action == "set_schedule":
            cron = request.POST.get("cron") or None
            try:
                admin_client.set_task_schedule(name, cron)
                if cron:
                    messages.success(request, f"Zeitplan für '{name}' auf '{cron}' gesetzt.")
                else:
                    messages.success(request, f"Zeitplan für '{name}' entfernt.")
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 422:
                    detail = exc.response.json().get("detail", str(exc))
                    messages.error(request, f"Ungültiger Cron-Ausdruck: {detail}")
                else:
                    messages.error(request, f"Fehler beim Setzen des Zeitplans: {exc}")
            except Exception as exc:
                messages.error(request, f"Fehler beim Setzen des Zeitplans: {exc}")

        return redirect("admin_dashboard:tasks")

    # GET
    task_list = []
    try:
        data = admin_client.get_tasks()
        for t in data.get("tasks", []):
            t["last_run_display"] = _format_last_run(t.get("last_run"))
            task_list.append(t)
    except Exception as exc:
        messages.error(request, f"Fehler beim Laden der Aufgaben: {exc}")

    return render(request, "admin_dashboard/tasks.html", {"tasks": task_list})
```

- [ ] **Step 4: Register the URL**

Edit `webui/broadcast/admin_dashboard/urls.py`:

```python
from django.urls import path
from broadcast.admin_dashboard.views import history as history_view
from broadcast.admin_dashboard.views import config as config_view
from broadcast.admin_dashboard.views import tasks as tasks_view

app_name = "admin_dashboard"

urlpatterns = [
    path("history/", history_view.history, name="history"),
    path("config/", config_view.config, name="config"),
    path("tasks/", tasks_view.tasks_view, name="tasks"),
]
```

- [ ] **Step 5: Create a minimal tasks template so the view can render**

Create `webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html` with a placeholder (full template comes in Task 6):

```html
{% extends "base.html" %}
{% block title %}Aufgaben{% endblock %}
{% block content %}
<div class="ca-card">
  <p>{{ tasks|length }} Aufgabe(n)</p>
</div>
{% endblock %}
```

- [ ] **Step 6: Run the view tests**

```bash
cd webui && uv run python manage.py test tests.test_admin_dashboard.TasksViewTest -v 2
```

Expected: PASS (6 tests)

- [ ] **Step 7: Run the full webui test suite**

```bash
cd webui && uv run python manage.py test -v 2
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add webui/broadcast/admin_dashboard/views/tasks.py webui/broadcast/admin_dashboard/urls.py webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): add tasks view, URL route, and stub template"
```

---

## Task 6: Full tasks template with inline cron editor

**Files:**
- Modify: `webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html`

The stub template from Task 5 is replaced with the full implementation.

- [ ] **Step 1: Write the full tasks template**

Replace `webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html` with:

```html
{% extends "base.html" %}
{% block title %}Aufgaben{% endblock %}

{% block content %}
<div class="ca-card">

  <!-- In-page tab navigation -->
  <div class="tabs" style="margin-bottom:1.5rem;">
    <ul>
      <li><a href="{% url 'admin_dashboard:history' %}">Verlauf</a></li>
      <li><a href="{% url 'admin_dashboard:config' %}">Konfiguration</a></li>
      <li class="is-active"><a href="{% url 'admin_dashboard:tasks' %}">Aufgaben</a></li>
    </ul>
  </div>

  <h2 class="ca-label" style="font-size:1.3rem;margin-bottom:1rem;">Aufgaben</h2>

  {% if tasks %}
  <div style="overflow-x:auto;">
    <table class="table is-fullwidth is-striped is-hoverable" style="font-size:0.9rem;">
      <thead>
        <tr>
          <th>Name</th>
          <th>Beschreibung</th>
          <th>Letzter Lauf</th>
          <th>Zeitplan (Cron)</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for task in tasks %}
        <tr>
          <td style="font-weight:bold;">{{ task.name }}</td>
          <td style="color:#555;">{{ task.description }}</td>
          <td style="color:{% if task.last_run %}#555{% else %}#aaa{% endif %};">{{ task.last_run_display }}</td>

          <!-- Schedule cell -->
          <td style="min-width:220px;">
            <!-- Normal state -->
            <span id="display-{{ task.name }}">
              {% if task.schedule %}
              <code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;cursor:pointer;border:1px solid transparent;"
                    onclick="openEdit('{{ task.name }}', '{{ task.schedule }}')">{{ task.schedule }}</code>
              <span style="color:#999;margin-left:4px;cursor:pointer;font-size:0.85rem;"
                    onclick="openEdit('{{ task.name }}', '{{ task.schedule }}')">✎</span>
              {% else %}
              <a style="color:#aaa;font-size:0.85rem;cursor:pointer;"
                 onclick="openEdit('{{ task.name }}', '')">+ Zeitplan hinzufügen</a>
              {% endif %}
            </span>

            <!-- Edit state (hidden) -->
            <span id="edit-{{ task.name }}" style="display:none;">
              <input type="text" id="cron-input-{{ task.name }}"
                     value="{{ task.schedule|default:'' }}"
                     style="font-family:monospace;padding:3px 6px;border:1px solid #35ADA4;border-radius:3px;width:110px;font-size:0.85rem;" />
              <button onclick="handleSave('{{ task.name }}')"
                      style="background:#35ADA4;color:#fff;border:none;padding:3px 10px;border-radius:3px;cursor:pointer;font-size:0.85rem;margin-left:4px;">Speichern</button>
              <button onclick="closeEdit('{{ task.name }}')"
                      style="background:#fff;color:#666;border:1px solid #ccc;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:0.85rem;margin-left:2px;">✕</button>
              {% if task.schedule %}
              <button onclick="handleRemove('{{ task.name }}')"
                      style="background:#fff;color:#c0392b;border:1px solid #c0392b;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:0.85rem;margin-left:2px;">Entfernen</button>
              {% endif %}
              <div id="cron-error-{{ task.name }}"
                   style="color:#c0392b;font-size:0.8rem;margin-top:3px;display:none;"></div>
            </span>

            <!-- Confirmation dialog (hidden) -->
            <div id="confirm-{{ task.name }}"
                 style="display:none;margin-top:8px;border:1px solid #f0c040;background:#fffbe6;border-radius:6px;padding:10px 14px;">
              <div id="confirm-text-{{ task.name }}" style="font-size:0.85rem;margin-bottom:8px;"></div>
              <form method="post" style="display:inline;">
                {% csrf_token %}
                <input type="hidden" name="action" value="set_schedule" />
                <input type="hidden" name="name" value="{{ task.name }}" />
                <input type="hidden" id="confirm-cron-{{ task.name }}" name="cron" value="" />
                <button type="submit"
                        style="background:#35ADA4;color:#fff;border:none;padding:3px 14px;border-radius:4px;cursor:pointer;font-size:0.85rem;">Bestätigen</button>
                <button type="button" onclick="closeConfirm('{{ task.name }}')"
                        style="background:#fff;color:#666;border:1px solid #ccc;padding:3px 12px;border-radius:4px;cursor:pointer;font-size:0.85rem;margin-left:6px;">Abbrechen</button>
              </form>
            </div>
          </td>

          <!-- Run button -->
          <td>
            <form method="post" style="display:inline;">
              {% csrf_token %}
              <input type="hidden" name="action" value="run" />
              <input type="hidden" name="name" value="{{ task.name }}" />
              <button type="submit"
                      style="background:#35ADA4;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.85rem;">▶ Ausführen</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <p style="color:#7a7a7a;font-size:0.9rem;">Keine Aufgaben gefunden.</p>
  {% endif %}
</div>

<script>
function isValidCron(expr) {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return false;
  const f = /^(\*|\d+(-\d+)?(\/\d+)?|\*(\/\d+)?|\d+(,\d+)*)$/;
  return fields.every(field => f.test(field));
}

function openEdit(name, currentCron) {
  document.getElementById('display-' + name).style.display = 'none';
  document.getElementById('edit-' + name).style.display = '';
  document.getElementById('cron-input-' + name).value = currentCron;
  document.getElementById('cron-error-' + name).style.display = 'none';
  document.getElementById('confirm-' + name).style.display = 'none';
}

function closeEdit(name) {
  document.getElementById('edit-' + name).style.display = 'none';
  document.getElementById('display-' + name).style.display = '';
  document.getElementById('confirm-' + name).style.display = 'none';
}

function closeConfirm(name) {
  document.getElementById('confirm-' + name).style.display = 'none';
}

function handleSave(name) {
  const cron = document.getElementById('cron-input-' + name).value.trim();
  const errEl = document.getElementById('cron-error-' + name);

  if (cron === '') {
    handleRemove(name);
    return;
  }

  if (!isValidCron(cron)) {
    errEl.textContent = 'Ungültiger Cron-Ausdruck (5 Felder erwartet, z.B. "0 9 * * 1").';
    errEl.style.display = '';
    return;
  }
  errEl.style.display = 'none';

  document.getElementById('confirm-text-' + name).innerHTML =
    '<strong>' + name + '</strong>: Zeitplan setzen auf <code>' + cron + '</code>';
  document.getElementById('confirm-cron-' + name).value = cron;
  document.getElementById('confirm-' + name).style.display = '';
}

function handleRemove(name) {
  document.getElementById('confirm-text-' + name).innerHTML =
    '<strong>' + name + '</strong>: Zeitplan wird entfernt.';
  document.getElementById('confirm-cron-' + name).value = '';
  document.getElementById('confirm-' + name).style.display = '';
}
</script>
{% endblock %}
```

- [ ] **Step 2: Run the view tests to confirm nothing broke**

```bash
cd webui && uv run python manage.py test tests.test_admin_dashboard.TasksViewTest -v 2
```

Expected: PASS (6 tests — the template change doesn't affect view logic tests).

- [ ] **Step 3: Commit**

```bash
git add webui/broadcast/admin_dashboard/templates/admin_dashboard/tasks.html
git commit -m "feat(webui): full tasks template with inline cron editor"
```

---

## Task 7: Tab nav in history.html, config.html, and base.html navbar

**Files:**
- Modify: `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html`
- Modify: `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html`
- Modify: `webui/broadcast/templates/base.html`

- [ ] **Step 1: Add in-page tab nav to history.html**

In `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html`, insert the tab nav block immediately after `{% block content %}` and before `<div class="ca-card">`:

Old:
```html
{% block content %}
<div class="ca-card">
  <h2 class="ca-label" style="font-size:1.3rem;margin-bottom:1rem;">
    Broadcast-Verlauf
```

New:
```html
{% block content %}
<div class="ca-card">
  <!-- In-page tab navigation -->
  <div class="tabs" style="margin-bottom:1.5rem;">
    <ul>
      <li class="is-active"><a href="{% url 'admin_dashboard:history' %}">Verlauf</a></li>
      <li><a href="{% url 'admin_dashboard:config' %}">Konfiguration</a></li>
      <li><a href="{% url 'admin_dashboard:tasks' %}">Aufgaben</a></li>
    </ul>
  </div>

  <h2 class="ca-label" style="font-size:1.3rem;margin-bottom:1rem;">
    Broadcast-Verlauf
```

- [ ] **Step 2: Add in-page tab nav to config.html**

In `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html`, insert after `{% block content %}` and before `<div class="ca-card">`:

Old:
```html
{% block content %}
<div class="ca-card">
  <h2 class="ca-label" style="font-size:1.3rem;margin-bottom:1rem;">Kanal-Konfiguration</h2>
```

New:
```html
{% block content %}
<div class="ca-card">
  <!-- In-page tab navigation -->
  <div class="tabs" style="margin-bottom:1.5rem;">
    <ul>
      <li><a href="{% url 'admin_dashboard:history' %}">Verlauf</a></li>
      <li class="is-active"><a href="{% url 'admin_dashboard:config' %}">Konfiguration</a></li>
      <li><a href="{% url 'admin_dashboard:tasks' %}">Aufgaben</a></li>
    </ul>
  </div>

  <h2 class="ca-label" style="font-size:1.3rem;margin-bottom:1rem;">Kanal-Konfiguration</h2>
```

- [ ] **Step 3: Add Aufgaben link to the base.html navbar**

In `webui/broadcast/templates/base.html`, the `{% if is_bot_admin %}` block currently has two links. Add a third:

Old:
```html
    {% if is_bot_admin %}
    <a href="/admin-dashboard/history/" class="ca-navbar-admin">Verlauf</a>
    <a href="/admin-dashboard/config/" class="ca-navbar-admin">Konfiguration</a>
    {% endif %}
```

New:
```html
    {% if is_bot_admin %}
    <a href="/admin-dashboard/history/" class="ca-navbar-admin">Verlauf</a>
    <a href="/admin-dashboard/config/" class="ca-navbar-admin">Konfiguration</a>
    <a href="/admin-dashboard/tasks/" class="ca-navbar-admin">Aufgaben</a>
    {% endif %}
```

- [ ] **Step 4: Run the full webui test suite**

```bash
cd webui && uv run python manage.py test -v 2
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html webui/broadcast/templates/base.html
git commit -m "feat(webui): add Aufgaben tab nav to history, config, and navbar"
```

---

## Final check

- [ ] **Run both full test suites one last time**

```bash
cd postbot && uv run pytest -v
cd webui && uv run python manage.py test -v 2
```

Expected: all tests pass in both projects.
