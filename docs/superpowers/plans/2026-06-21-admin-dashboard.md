# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `admin_dashboard` Django app with broadcast history (via `GET /api/history`) and channel group CRUD (via `GET/PUT /api/config`), keeping webui and postbot fully isolated as separate containers.

**Architecture:** postbot exposes two new authenticated FastAPI endpoints; webui's `admin_dashboard` app calls them via `admin_client.py` (same pattern as existing `postbot_client.py`). No shared volumes — all cross-container communication is HTTP.

**Tech Stack:** FastAPI (postbot), Django + `requests` (webui), Bulma + CA CSS design system, pytest (both sides), Django TestCase + `unittest.mock`.

---

## File map

### postbot (create)
- `postbot/api/routes/history.py` — `GET /api/history`
- `postbot/api/routes/config.py` — `GET /api/config` + `PUT /api/config`
- `postbot/tests/test_api_history.py`
- `postbot/tests/test_api_config.py`

### postbot (modify)
- `postbot/database.py` — add `get_history(page, per_page)`
- `postbot/tests/test_database.py` — add `get_history` tests
- `postbot/api/app.py` — register new routers

### webui (create)
- `webui/broadcast/admin_dashboard/services/__init__.py`
- `webui/broadcast/admin_dashboard/services/admin_client.py`
- `webui/broadcast/admin_dashboard/views/__init__.py` — `require_bot_admin` decorator
- `webui/broadcast/admin_dashboard/views/history.py`
- `webui/broadcast/admin_dashboard/views/config.py`
- `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html`
- `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html`
- `webui/broadcast/admin_dashboard/urls.py`
- `webui/tests/test_admin_dashboard.py`

### webui (modify)
- `webui/webui/settings.py` — add `broadcast.admin_dashboard` to `INSTALLED_APPS`
- `webui/webui/urls.py` — mount admin-dashboard URLs

---

## Task 1: Add `get_history()` to `postbot/database.py`

**Files:**
- Modify: `postbot/database.py`
- Modify: `postbot/tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

Add to `postbot/tests/test_database.py`:

```python
from database import get_history  # add to existing imports at top


def test_get_history_empty_db(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_database(db_file)
    total, results = get_history()
    assert total == 0
    assert results == []


def test_get_history_returns_newest_first(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_database(db_file)
    log_broadcast("alice", "first", ["ch1"])
    log_broadcast("bob", "second", ["ch2"])
    total, results = get_history(page=1, per_page=10)
    assert total == 2
    assert results[0]["sender_name"] == "bob"
    assert results[1]["sender_name"] == "alice"


def test_get_history_pagination(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_database(db_file)
    for i in range(5):
        log_broadcast(f"user{i}", f"msg{i}", [f"ch{i}"])
    total, page1 = get_history(page=1, per_page=3)
    assert total == 5
    assert len(page1) == 3
    _, page2 = get_history(page=2, per_page=3)
    assert len(page2) == 2


def test_get_history_caps_per_page_at_100(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_database(db_file)
    # Must not raise with a huge per_page value.
    total, results = get_history(page=1, per_page=9999)
    assert total == 0


def test_get_history_deserializes_fields(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_database(db_file)
    log_broadcast("alice", "msg", ["Channel A", "Channel B"], file_ids=["f1"])
    _, results = get_history()
    r = results[0]
    assert r["target_channels"] == ["Channel A", "Channel B"]
    assert r["file_ids"] == ["f1"]
    assert r["sender_name"] == "alice"
    assert "timestamp" in r
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_database.py -k "get_history" -v
```

Expected: `ImportError` or `AttributeError` — `get_history` does not exist yet.

- [ ] **Step 3: Implement `get_history` in `postbot/database.py`**

Add after the `log_broadcast` function:

```python
def get_history(page: int = 1, per_page: int = 20) -> tuple[int, list[dict]]:
    """Return a paginated page of broadcast records, newest first.

    Args:
        page: 1-based page number.
        per_page: Records per page (capped at 100).

    Returns:
        ``(total, results)`` where ``total`` is the full record count and
        ``results`` is a list of dicts with keys ``id``, ``timestamp``,
        ``sender_name``, ``message_content``, ``target_channels`` (list),
        ``file_ids`` (list).
    """
    per_page = min(per_page, 100)
    offset = (page - 1) * per_page
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM broadcasts")
    total: int = cursor.fetchone()[0]
    cursor.execute(
        "SELECT id, timestamp, sender_name, message_content, target_channels, file_ids "
        "FROM broadcasts ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    )
    results = [
        {
            "id": row[0],
            "timestamp": row[1],
            "sender_name": row[2],
            "message_content": row[3],
            "target_channels": json.loads(row[4]) if row[4] else [],
            "file_ids": json.loads(row[5]) if row[5] else [],
        }
        for row in cursor.fetchall()
    ]
    return total, results
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_database.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add postbot/database.py postbot/tests/test_database.py
git commit -m "feat(postbot): add get_history() to database module"
```

---

## Task 2: Add `GET /api/history` endpoint to postbot

**Files:**
- Create: `postbot/api/routes/history.py`
- Create: `postbot/tests/test_api_history.py`

- [ ] **Step 1: Write the failing tests**

Create `postbot/tests/test_api_history.py`:

```python
"""Tests for GET /api/history."""
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
    set_bot(_make_bot())
    yield
    context._bot = original


client = TestClient(app)
HEADERS = {"Authorization": "Bearer test-secret"}


def test_history_empty_db():
    with patch("api.routes.history.db_module.get_history", return_value=(0, [])):
        resp = client.get("/api/history", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []
    assert data["page"] == 1
    assert data["per_page"] == 20


def test_history_returns_records():
    records = [
        {
            "id": 5,
            "sender_name": "alice",
            "message_content": "hi",
            "timestamp": "2026-06-21T10:00:00",
            "target_channels": ["ch1"],
            "file_ids": [],
        }
    ]
    with patch("api.routes.history.db_module.get_history", return_value=(1, records)):
        resp = client.get("/api/history", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["sender_name"] == "alice"


def test_history_passes_page_and_per_page_to_db():
    with patch("api.routes.history.db_module.get_history", return_value=(0, [])) as mock:
        client.get("/api/history?page=2&per_page=5", headers=HEADERS)
    mock.assert_called_once_with(page=2, per_page=5)


def test_history_caps_per_page_at_100():
    with patch("api.routes.history.db_module.get_history", return_value=(0, [])) as mock:
        client.get("/api/history?per_page=999", headers=HEADERS)
    _, kwargs = mock.call_args
    assert kwargs["per_page"] == 100


def test_history_requires_auth():
    resp = client.get("/api/history")
    assert resp.status_code == 401


def test_history_wrong_secret_returns_401():
    resp = client.get("/api/history", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_api_history.py -v
```

Expected: 404 responses (route not registered yet).

- [ ] **Step 3: Create `postbot/api/routes/history.py`**

```python
"""GET /api/history — paginated broadcast log."""
from fastapi import APIRouter, Depends

from api.auth import verify_api_secret
import database as db_module

router = APIRouter()


@router.get("/api/history", dependencies=[Depends(verify_api_secret)])
def get_history(page: int = 1, per_page: int = 20) -> dict:
    """Return a paginated page of the broadcast log, newest-first."""
    per_page = min(per_page, 100)
    total, results = db_module.get_history(page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "results": results}
```

- [ ] **Step 4: Register the router in `postbot/api/app.py`**

```python
"""FastAPI application for the postbot HTTP API."""
from fastapi import FastAPI

app = FastAPI(title="postbot API", docs_url=None, redoc_url=None)

# Import routers after app creation to avoid circular imports.
from api.routes import broadcast, channels, history  # noqa: E402

app.include_router(channels.router)
app.include_router(broadcast.router)
app.include_router(history.router)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_api_history.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full postbot test suite to check for regressions**

```bash
cd postbot && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add postbot/api/routes/history.py postbot/api/app.py postbot/tests/test_api_history.py
git commit -m "feat(postbot): add GET /api/history endpoint"
```

---

## Task 3: Add `GET /api/config` and `PUT /api/config` to postbot

**Files:**
- Create: `postbot/api/routes/config.py`
- Create: `postbot/tests/test_api_config.py`
- Modify: `postbot/api/app.py`

- [ ] **Step 1: Write the failing tests**

Create `postbot/tests/test_api_config.py`:

```python
"""Tests for GET /api/config and PUT /api/config."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.context import set_bot
from bot import GroupEntry, WhitelistEntry


def _make_bot(secret: str = "test-secret") -> MagicMock:
    bot = MagicMock()
    bot.config.webui_api_secret = secret
    bot._visible_groups = {
        "Group A": GroupEntry(channels=["id1", "id2"], aliases=[])
    }
    bot._private_groups = {}
    bot._whitelist = {
        "alice": WhitelistEntry(id="user_id_alice", label="alice", aliases=[])
    }
    return bot


@pytest.fixture(autouse=True)
def reset_bot():
    from api import context
    original = context._bot
    yield
    context._bot = original


client = TestClient(app)
HEADERS = {"Authorization": "Bearer test-secret"}


def test_get_config_returns_groups():
    set_bot(_make_bot())
    resp = client.get("/api/config", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "Group A" in data["groups"]
    assert data["groups"]["Group A"]["channels"] == ["id1", "id2"]
    assert data["groups"]["Group A"]["aliases"] == []


def test_get_config_returns_private_groups_and_whitelist():
    set_bot(_make_bot())
    resp = client.get("/api/config", headers=HEADERS)
    data = resp.json()
    assert data["private_groups"] == {}
    assert "alice" in data["whitelist"]
    assert data["whitelist"]["alice"]["id"] == "user_id_alice"


def test_put_config_updates_bot_state():
    bot = _make_bot()
    set_bot(bot)
    resp = client.put(
        "/api/config",
        json={
            "groups": {"New Group": {"channels": ["id3"], "aliases": []}},
            "private_groups": {},
            "whitelist": {},
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    bot._save_channel_data.assert_called_once()
    bot._build_alias_map.assert_called_once()
    assert "New Group" in bot._visible_groups
    assert bot._visible_groups["New Group"].channels == ["id3"]


def test_put_config_updates_whitelist():
    bot = _make_bot()
    set_bot(bot)
    client.put(
        "/api/config",
        json={
            "groups": {},
            "private_groups": {},
            "whitelist": {"bob": {"id": "bob_mm_id", "aliases": []}},
        },
        headers=HEADERS,
    )
    assert "bob" in bot._whitelist
    assert bot._whitelist["bob"].id == "bob_mm_id"


def test_put_config_invalid_body_returns_422():
    set_bot(_make_bot())
    resp = client.put(
        "/api/config",
        json={"groups": "not-a-dict"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_get_config_requires_auth():
    set_bot(_make_bot())
    resp = client.get("/api/config")
    assert resp.status_code == 401


def test_put_config_requires_auth():
    set_bot(_make_bot())
    resp = client.put(
        "/api/config",
        json={"groups": {}, "private_groups": {}, "whitelist": {}},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_api_config.py -v
```

Expected: 404 responses (route not registered yet).

- [ ] **Step 3: Create `postbot/api/routes/config.py`**

```python
"""GET /api/config and PUT /api/config — read and write channels.toml."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


class GroupPayload(BaseModel):
    channels: list[str] = []
    aliases: list[str] = []


class WhitelistPayload(BaseModel):
    id: str
    aliases: list[str] = []


class ConfigPayload(BaseModel):
    groups: dict[str, GroupPayload] = {}
    private_groups: dict[str, GroupPayload] = {}
    whitelist: dict[str, WhitelistPayload] = {}


@router.get("/api/config", dependencies=[Depends(verify_api_secret)])
def get_config() -> dict:
    """Return the current channels.toml contents as JSON."""
    bot = get_bot()
    return {
        "groups": {
            name: {"channels": e.channels, "aliases": e.aliases}
            for name, e in bot._visible_groups.items()
        },
        "private_groups": {
            name: {"channels": e.channels, "aliases": e.aliases}
            for name, e in bot._private_groups.items()
        },
        "whitelist": {
            label: {"id": e.id, "aliases": e.aliases}
            for label, e in bot._whitelist.items()
        },
    }


@router.put("/api/config", dependencies=[Depends(verify_api_secret)])
def put_config(body: ConfigPayload) -> dict:
    """Replace channels.toml with the supplied config and reload bot state."""
    from bot import GroupEntry, WhitelistEntry  # noqa: PLC0415

    bot = get_bot()
    bot._visible_groups = {
        name: GroupEntry(channels=v.channels, aliases=v.aliases)
        for name, v in body.groups.items()
    }
    bot._private_groups = {
        name: GroupEntry(channels=v.channels, aliases=v.aliases)
        for name, v in body.private_groups.items()
    }
    bot._whitelist = {
        label: WhitelistEntry(id=v.id, label=label, aliases=v.aliases)
        for label, v in body.whitelist.items()
    }
    bot._save_channel_data()
    bot._build_alias_map()
    return {"ok": True}
```

- [ ] **Step 4: Register the config router in `postbot/api/app.py`**

```python
"""FastAPI application for the postbot HTTP API."""
from fastapi import FastAPI

app = FastAPI(title="postbot API", docs_url=None, redoc_url=None)

# Import routers after app creation to avoid circular imports.
from api.routes import broadcast, channels, config, history  # noqa: E402

app.include_router(channels.router)
app.include_router(broadcast.router)
app.include_router(history.router)
app.include_router(config.router)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_api_config.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full postbot test suite**

```bash
cd postbot && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add postbot/api/routes/config.py postbot/api/app.py postbot/tests/test_api_config.py
git commit -m "feat(postbot): add GET/PUT /api/config endpoints"
```

---

## Task 4: Create `admin_client.py` in webui

**Files:**
- Create: `webui/broadcast/admin_dashboard/services/__init__.py`
- Create: `webui/broadcast/admin_dashboard/services/admin_client.py`
- Modify: `webui/tests/test_admin_dashboard.py` (create file)

- [ ] **Step 1: Create the empty `__init__.py`**

```python
# webui/broadcast/admin_dashboard/services/__init__.py
```

(empty file)

- [ ] **Step 2: Write failing tests for `admin_client.py`**

Create `webui/tests/test_admin_dashboard.py`:

```python
"""Tests for admin_dashboard — admin_client, views, and access control."""
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse


# ── admin_client ──────────────────────────────────────────────────────────────


class AdminClientGetHistoryTest(TestCase):
    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_history_calls_correct_url(self, mock_get):
        from broadcast.admin_dashboard.services import admin_client
        mock_get.return_value.json.return_value = {"total": 0, "page": 1, "per_page": 20, "results": []}
        mock_get.return_value.raise_for_status = MagicMock()
        result = admin_client.get_history(page=2, per_page=5)
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert "/api/history" in call_kwargs[0][0]
        assert call_kwargs[1]["params"] == {"page": 2, "per_page": 5}
        assert result["total"] == 0

    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_history_raises_on_http_error(self, mock_get):
        from broadcast.admin_dashboard.services import admin_client
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("500")
        with pytest.raises(requests.HTTPError):
            admin_client.get_history()


class AdminClientGetConfigTest(TestCase):
    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_config_calls_correct_url(self, mock_get):
        from broadcast.admin_dashboard.services import admin_client
        mock_get.return_value.json.return_value = {"groups": {}, "private_groups": {}, "whitelist": {}}
        mock_get.return_value.raise_for_status = MagicMock()
        result = admin_client.get_config()
        assert "/api/config" in mock_get.call_args[0][0]
        assert result["groups"] == {}

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_put_config_sends_json(self, mock_put):
        from broadcast.admin_dashboard.services import admin_client
        mock_put.return_value.json.return_value = {"ok": True}
        mock_put.return_value.raise_for_status = MagicMock()
        cfg = {"groups": {"G": {"channels": ["id1"], "aliases": []}}, "private_groups": {}, "whitelist": {}}
        result = admin_client.put_config(cfg)
        assert mock_put.call_args[1]["json"] == cfg
        assert result == {"ok": True}
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::AdminClientGetHistoryTest -v
```

Expected: `ImportError` — module does not exist yet.

- [ ] **Step 4: Create `webui/broadcast/admin_dashboard/services/admin_client.py`**

```python
"""HTTP client for postbot admin API (history and config)."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"}


def get_history(page: int = 1, per_page: int = 20) -> dict:
    """GET /api/history. Returns {"total", "page", "per_page", "results"}."""
    resp = requests.get(
        f"{settings.POSTBOT_API_URL}/api/history",
        params={"page": page, "per_page": per_page},
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_config() -> dict:
    """GET /api/config. Returns {"groups", "private_groups", "whitelist"}."""
    resp = requests.get(
        f"{settings.POSTBOT_API_URL}/api/config",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def put_config(config: dict) -> dict:
    """PUT /api/config. Returns {"ok": true}."""
    resp = requests.put(
        f"{settings.POSTBOT_API_URL}/api/config",
        json=config,
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::AdminClientGetHistoryTest tests/test_admin_dashboard.py::AdminClientGetConfigTest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add webui/broadcast/admin_dashboard/services/__init__.py \
        webui/broadcast/admin_dashboard/services/admin_client.py \
        webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): add admin_client for postbot history and config API"
```

---

## Task 5: `require_bot_admin` decorator, URLs, and settings wiring

**Files:**
- Create: `webui/broadcast/admin_dashboard/views/__init__.py`
- Create: `webui/broadcast/admin_dashboard/urls.py`
- Modify: `webui/webui/settings.py`
- Modify: `webui/webui/urls.py`

- [ ] **Step 1: Write failing tests for the decorator**

Add to `webui/tests/test_admin_dashboard.py`:

```python
# ── require_bot_admin decorator ───────────────────────────────────────────────


class RequireBotAdminTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user("admin", password="pw")
        self.bot_admins = Group.objects.create(name="BotAdmins")
        self.admin_user.groups.add(self.bot_admins)
        self.regular_user = User.objects.create_user("regular", password="pw")

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/admin-dashboard/history/")
        self.assertRedirects(resp, "/login/?next=/admin-dashboard/history/", fetch_redirect_response=False)

    def test_non_admin_gets_403(self):
        self.client.login(username="regular", password="pw")
        resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 403)

    def test_bot_admin_gets_200(self):
        self.client.login(username="admin", password="pw")
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value={"total": 0, "page": 1, "per_page": 20, "results": []}):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::RequireBotAdminTest -v
```

Expected: 404 (URL not registered yet).

- [ ] **Step 3: Create `webui/broadcast/admin_dashboard/views/__init__.py`**

```python
"""Admin dashboard views — shared access control decorator."""
from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def require_bot_admin(view_func):
    """Restrict a view to members of the BotAdmins Django group.

    Unauthenticated requests are redirected to the login page.
    Authenticated non-admins receive HTTP 403.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.get_full_path()}")
        if not request.user.groups.filter(name="BotAdmins").exists():
            return HttpResponseForbidden("Zugang nur für BotAdmins.")
        return view_func(request, *args, **kwargs)
    return wrapper
```

- [ ] **Step 4: Create placeholder views so URLs can be wired**

Create `webui/broadcast/admin_dashboard/views/history.py` (minimal, tests come in Task 6):

```python
"""Admin history view — broadcast log."""
import logging

import requests
from django.contrib import messages
from django.shortcuts import render

from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin

logger = logging.getLogger(__name__)


@require_bot_admin
def history(request):
    page = max(1, int(request.GET.get("page", 1)))
    try:
        data = admin_client.get_history(page=page, per_page=20)
    except (requests.ConnectionError, requests.HTTPError) as exc:
        messages.error(request, f"postbot nicht erreichbar: {exc}")
        data = {"total": 0, "page": page, "per_page": 20, "results": []}

    total_pages = max(1, (data["total"] + 19) // 20)
    return render(request, "admin_dashboard/history.html", {
        "results": data["results"],
        "page": page,
        "total_pages": total_pages,
        "total": data["total"],
    })
```

Create `webui/broadcast/admin_dashboard/views/config.py` (minimal):

```python
"""Admin config view — channel group CRUD."""
import logging

import requests
from django.contrib import messages
from django.shortcuts import redirect, render

from broadcast.admin_dashboard.services import admin_client
from broadcast.admin_dashboard.views import require_bot_admin
from broadcast.services.channel_service import get_channels

logger = logging.getLogger(__name__)


def _build_sections(cfg: dict, by_id: dict) -> list[dict]:
    """Return sections list with pre-resolved channel display names for the template."""
    result = []
    for section_key, section_label in [("groups", "Gruppen"), ("private_groups", "Private Gruppen")]:
        entries = []
        for name, entry in cfg.get(section_key, {}).items():
            channel_ids = entry.get("channels", [])
            entries.append({
                "name": name,
                "channels": channel_ids,
                "aliases": entry.get("aliases", []),
                "channel_display": [by_id.get(cid, cid) for cid in channel_ids],
            })
        result.append({"key": section_key, "label": section_label, "entries": entries})
    return result


@require_bot_admin
def config(request):
    if request.method == "POST":
        return _handle_post(request)

    try:
        cfg = admin_client.get_config()
        channels_data = get_channels()
    except (requests.ConnectionError, requests.HTTPError) as exc:
        messages.error(request, f"postbot nicht erreichbar: {exc}")
        cfg = {"groups": {}, "private_groups": {}, "whitelist": {}}
        channels_data = {"individual_channels": []}

    all_channels = channels_data.get("individual_channels", [])
    by_id = {ch["id"]: ch["display_name"] for ch in all_channels}
    return render(request, "admin_dashboard/config.html", {
        "cfg": cfg,
        "sections": _build_sections(cfg, by_id),
        "all_channels": all_channels,
    })


def _handle_post(request):
    action = request.POST.get("action")
    try:
        cfg = admin_client.get_config()
    except (requests.ConnectionError, requests.HTTPError) as exc:
        messages.error(request, f"postbot nicht erreichbar: {exc}")
        return redirect("admin_dashboard:config")

    if action == "delete_group":
        section = request.POST.get("section")
        name = request.POST.get("name")
        if section in ("groups", "private_groups") and name in cfg.get(section, {}):
            del cfg[section][name]

    elif action == "add_group":
        section = request.POST.get("section", "groups")
        name = request.POST.get("name", "").strip()
        channels = request.POST.getlist("channels")
        if not name:
            messages.error(request, "Gruppenname darf nicht leer sein.")
            return redirect("admin_dashboard:config")
        if section in ("groups", "private_groups"):
            cfg[section][name] = {"channels": channels, "aliases": []}

    elif action == "edit_group":
        section = request.POST.get("section")
        name = request.POST.get("name", "").strip()
        channels = request.POST.getlist("channels")
        if section in ("groups", "private_groups") and name in cfg.get(section, {}):
            cfg[section][name]["channels"] = channels

    elif action == "delete_whitelist":
        name = request.POST.get("name")
        if name in cfg.get("whitelist", {}):
            del cfg["whitelist"][name]

    elif action == "add_whitelist":
        name = request.POST.get("name", "").strip()
        mm_user_id = request.POST.get("mm_user_id", "").strip()
        if not name or not mm_user_id:
            messages.error(request, "Name und User-ID sind erforderlich.")
            return redirect("admin_dashboard:config")
        cfg["whitelist"][name] = {"id": mm_user_id, "aliases": []}

    try:
        admin_client.put_config(cfg)
        messages.success(request, "Konfiguration gespeichert.")
    except (requests.ConnectionError, requests.HTTPError) as exc:
        messages.error(request, f"Fehler beim Speichern: {exc}")

    return redirect("admin_dashboard:config")
```

- [ ] **Step 5: Create `webui/broadcast/admin_dashboard/urls.py`**

```python
from django.urls import path

from broadcast.admin_dashboard.views import config, history

app_name = "admin_dashboard"

urlpatterns = [
    path("history/", history.history, name="history"),
    path("config/", config.config, name="config"),
]
```

- [ ] **Step 6: Add `broadcast.admin_dashboard` to `INSTALLED_APPS` in `webui/webui/settings.py`**

Find the `INSTALLED_APPS` list and add the new app:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "broadcast",
    "broadcast.admin_dashboard",
]
```

- [ ] **Step 7: Mount admin-dashboard URLs in `webui/webui/urls.py`**

```python
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("broadcast/", include("broadcast.urls")),
    path("admin-dashboard/", include("broadcast.admin_dashboard.urls")),
]
```

- [ ] **Step 8: Run decorator tests**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::RequireBotAdminTest -v
```

Expected: all pass (views exist but templates don't yet — templates are created in Tasks 6 and 7).

Note: if the test fails because the template is missing, create a minimal placeholder template first:

```bash
mkdir -p webui/broadcast/admin_dashboard/templates/admin_dashboard
echo "{% extends 'base.html' %}{% block content %}placeholder{% endblock %}" \
  > webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html
echo "{% extends 'base.html' %}{% block content %}placeholder{% endblock %}" \
  > webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html
```

- [ ] **Step 9: Commit**

```bash
git add webui/broadcast/admin_dashboard/views/__init__.py \
        webui/broadcast/admin_dashboard/views/history.py \
        webui/broadcast/admin_dashboard/views/config.py \
        webui/broadcast/admin_dashboard/urls.py \
        webui/webui/settings.py \
        webui/webui/urls.py \
        webui/broadcast/admin_dashboard/templates/ \
        webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): wire admin_dashboard app — decorator, URLs, settings"
```

---

## Task 6: History view tests and template

**Files:**
- Modify: `webui/tests/test_admin_dashboard.py`
- Create: `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html`

- [ ] **Step 1: Add history view tests to `webui/tests/test_admin_dashboard.py`**

```python
# ── History view ──────────────────────────────────────────────────────────────

MOCK_HISTORY = {
    "total": 2,
    "page": 1,
    "per_page": 20,
    "results": [
        {
            "id": 2,
            "timestamp": "2026-06-21T10:00:00",
            "sender_name": "bob",
            "message_content": "Hello world, this is a broadcast message.",
            "target_channels": ["Channel A"],
            "file_ids": [],
        },
        {
            "id": 1,
            "timestamp": "2026-06-20T09:00:00",
            "sender_name": "alice",
            "message_content": "Earlier message.",
            "target_channels": ["Channel B", "Channel C"],
            "file_ids": ["f1"],
        },
    ],
}


class HistoryViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user("histadmin", password="pw")
        bot_admins = Group.objects.get_or_create(name="BotAdmins")[0]
        self.admin_user.groups.add(bot_admins)

    @patch(
        "broadcast.admin_dashboard.views.history.admin_client.get_history",
        return_value=MOCK_HISTORY,
    )
    def test_get_renders_table_rows(self, _):
        self.client.login(username="histadmin", password="pw")
        resp = self.client.get(reverse("admin_dashboard:history"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "bob")
        self.assertContains(resp, "alice")

    @patch(
        "broadcast.admin_dashboard.views.history.admin_client.get_history",
        return_value=MOCK_HISTORY,
    )
    def test_get_shows_total_count(self, _):
        self.client.login(username="histadmin", password="pw")
        resp = self.client.get(reverse("admin_dashboard:history"))
        self.assertContains(resp, "2")

    @patch(
        "broadcast.admin_dashboard.views.history.admin_client.get_history",
        side_effect=requests.ConnectionError("unreachable"),
    )
    def test_postbot_unreachable_shows_error(self, _):
        self.client.login(username="histadmin", password="pw")
        resp = self.client.get(reverse("admin_dashboard:history"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nicht erreichbar")

    @patch(
        "broadcast.admin_dashboard.views.history.admin_client.get_history",
        return_value={"total": 100, "page": 1, "per_page": 20, "results": []},
    )
    def test_pagination_shows_next_link(self, _):
        self.client.login(username="histadmin", password="pw")
        resp = self.client.get(reverse("admin_dashboard:history"))
        self.assertContains(resp, "page=2")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::HistoryViewTest -v
```

Expected: failures because template has placeholder content (no `bob`, `alice`, etc.).

- [ ] **Step 3: Create `webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html`**

```html
{% extends "base.html" %}
{% block title %}Broadcast-Verlauf{% endblock %}

{% block content %}
<div class="ca-card" style="max-width:900px;">
  <h1 class="ca-label" style="font-size:1.4rem;margin-bottom:0.25rem;">Broadcast-Verlauf</h1>
  <p style="color:#7a7a7a;font-size:0.9rem;margin-bottom:1.25rem;">{{ total }} Einträge gesamt</p>

  <div style="overflow-x:auto;">
    <table class="table is-fullwidth is-striped is-hoverable" style="font-size:0.9rem;">
      <thead>
        <tr>
          <th>Zeitpunkt</th>
          <th>Absender</th>
          <th>Nachricht</th>
          <th>Kanäle</th>
        </tr>
      </thead>
      <tbody>
        {% for entry in results %}
        <tr>
          <td style="white-space:nowrap;"><small>{{ entry.timestamp }}</small></td>
          <td>{{ entry.sender_name }}</td>
          <td>
            <details>
              <summary style="cursor:pointer;color:var(--ca-teal);">
                {{ entry.message_content|truncatechars:60 }}
              </summary>
              <pre style="white-space:pre-wrap;font-size:0.8rem;margin-top:0.5rem;">{{ entry.message_content }}</pre>
            </details>
          </td>
          <td>
            <ul style="margin:0;padding-left:1rem;">
              {% for ch in entry.target_channels %}<li>{{ ch }}</li>{% endfor %}
            </ul>
          </td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="4" style="text-align:center;color:#7a7a7a;">Keine Einträge vorhanden.</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <nav style="display:flex;gap:0.75rem;align-items:center;margin-top:1rem;">
    {% if page > 1 %}
      <a class="ca-button" style="padding:0.4rem 1rem;font-size:0.9rem;" href="?page={{ page|add:"-1" }}">← Zurück</a>
    {% endif %}
    <span style="color:#7a7a7a;font-size:0.9rem;">Seite {{ page }} / {{ total_pages }}</span>
    {% if page < total_pages %}
      <a class="ca-button" style="padding:0.4rem 1rem;font-size:0.9rem;" href="?page={{ page|add:"1" }}">Weiter →</a>
    {% endif %}
  </nav>
</div>
{% endblock %}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::HistoryViewTest -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add webui/broadcast/admin_dashboard/templates/admin_dashboard/history.html \
        webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): admin history view and template"
```

---

## Task 7: Config view tests and template

**Files:**
- Modify: `webui/tests/test_admin_dashboard.py`
- Create: `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html`

- [ ] **Step 1: Add config view tests to `webui/tests/test_admin_dashboard.py`**

```python
# ── Config view ───────────────────────────────────────────────────────────────

MOCK_CONFIG = {
    "groups": {
        "Group A": {"channels": ["id1"], "aliases": []},
    },
    "private_groups": {},
    "whitelist": {
        "alice": {"id": "user_id_alice", "aliases": []},
    },
}

MOCK_CHANNELS = {
    "groups": {},
    "private_groups": {},
    "individual_channels": [
        {"id": "id1", "display_name": "Channel One", "channel_name": "channel-one"},
        {"id": "id2", "display_name": "Channel Two", "channel_name": "channel-two"},
    ],
}


class ConfigViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user("cfgadmin", password="pw")
        bot_admins = Group.objects.get_or_create(name="BotAdmins")[0]
        self.admin_user.groups.add(bot_admins)
        self.client.login(username="cfgadmin", password="pw")

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.get_channels", return_value={"individual_channels": []})
    def test_get_renders_group_names(self, _, __):
        resp = self.client.get(reverse("admin_dashboard:config"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Group A")

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.get_channels", return_value={"individual_channels": []})
    def test_get_renders_whitelist(self, _, __):
        resp = self.client.get(reverse("admin_dashboard:config"))
        self.assertContains(resp, "alice")
        self.assertContains(resp, "user_id_alice")

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.admin_client.put_config", return_value={"ok": True})
    def test_post_delete_group_calls_put_config(self, mock_put, _):
        resp = self.client.post(
            reverse("admin_dashboard:config"),
            {"action": "delete_group", "section": "groups", "name": "Group A"},
        )
        self.assertRedirects(resp, reverse("admin_dashboard:config"))
        sent_cfg = mock_put.call_args[0][0]
        self.assertNotIn("Group A", sent_cfg["groups"])

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.admin_client.put_config", return_value={"ok": True})
    def test_post_add_group_calls_put_config(self, mock_put, _):
        self.client.post(
            reverse("admin_dashboard:config"),
            {"action": "add_group", "section": "groups", "name": "New Group", "channels": ["id2"]},
        )
        sent_cfg = mock_put.call_args[0][0]
        self.assertIn("New Group", sent_cfg["groups"])
        self.assertEqual(sent_cfg["groups"]["New Group"]["channels"], ["id2"])

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.admin_client.put_config", return_value={"ok": True})
    def test_post_add_whitelist_calls_put_config(self, mock_put, _):
        self.client.post(
            reverse("admin_dashboard:config"),
            {"action": "add_whitelist", "name": "bob", "mm_user_id": "bob_mm_id"},
        )
        sent_cfg = mock_put.call_args[0][0]
        self.assertIn("bob", sent_cfg["whitelist"])
        self.assertEqual(sent_cfg["whitelist"]["bob"]["id"], "bob_mm_id")

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    @patch("broadcast.admin_dashboard.views.config.admin_client.put_config", return_value={"ok": True})
    def test_post_delete_whitelist_calls_put_config(self, mock_put, _):
        self.client.post(
            reverse("admin_dashboard:config"),
            {"action": "delete_whitelist", "name": "alice"},
        )
        sent_cfg = mock_put.call_args[0][0]
        self.assertNotIn("alice", sent_cfg["whitelist"])

    @patch(
        "broadcast.admin_dashboard.views.config.admin_client.get_config",
        side_effect=requests.ConnectionError("down"),
    )
    def test_get_postbot_unreachable_shows_error(self, _):
        resp = self.client.get(reverse("admin_dashboard:config"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nicht erreichbar")

    @patch("broadcast.admin_dashboard.views.config.admin_client.get_config", return_value=MOCK_CONFIG)
    def test_post_add_group_empty_name_shows_error(self, _):
        resp = self.client.post(
            reverse("admin_dashboard:config"),
            {"action": "add_group", "section": "groups", "name": "", "channels": ["id1"]},
            follow=True,
        )
        self.assertContains(resp, "leer")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::ConfigViewTest -v
```

Expected: failures because template has placeholder content.

- [ ] **Step 3: Create `webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html`**

```html
{% extends "base.html" %}
{% block title %}Kanal-Konfiguration{% endblock %}

{% block content %}
<div class="ca-card" style="max-width:900px;">
  <h1 class="ca-label" style="font-size:1.4rem;margin-bottom:1.5rem;">Kanal-Konfiguration</h1>

  {# ── Groups and Private Groups ──────────────────────────────────────────── #}
  {% for section in sections %}
  <h2 style="font-weight:700;font-size:1.05rem;margin:1.5rem 0 0.75rem;color:var(--ca-teal);">
    {{ section.label }}
  </h2>

  <table class="table is-fullwidth is-striped" style="font-size:0.9rem;">
    <thead>
      <tr><th>Name</th><th>Kanäle</th><th></th></tr>
    </thead>
    <tbody>
      {% for entry in section.entries %}
      <tr>
        <td><strong>{{ entry.name }}</strong></td>
        <td>
          <details>
            <summary style="cursor:pointer;color:var(--ca-teal);">
              {{ entry.channels|length }} Kanal{% if entry.channels|length != 1 %}e{% endif %}
            </summary>
            <ul style="margin:0.5rem 0 0 1rem;font-size:0.85rem;">
              {% for name in entry.channel_display %}<li>{{ name }}</li>{% endfor %}
            </ul>
          </details>
        </td>
        <td style="white-space:nowrap;">
          <details style="display:inline;">
            <summary class="ca-button" style="display:inline;padding:0.3rem 0.75rem;font-size:0.85rem;cursor:pointer;">
              Bearbeiten
            </summary>
            <div style="margin-top:0.75rem;padding:1rem;background:#f5f5f5;border-radius:6px;">
              <form method="post">
                {% csrf_token %}
                <input type="hidden" name="action" value="edit_group">
                <input type="hidden" name="section" value="{{ section.key }}">
                <input type="hidden" name="name" value="{{ entry.name }}">
                <label class="ca-label" style="font-size:0.85rem;">Kanäle (Strg/Cmd zum Mehrfachauswählen):</label>
                <select name="channels" multiple size="6"
                  style="width:100%;font-size:0.85rem;border:1px solid #ccc;border-radius:4px;padding:0.25rem;">
                  {% for ch in all_channels %}
                    <option value="{{ ch.id }}"
                      {% if ch.id in entry.channels %} selected{% endif %}>
                      {{ ch.display_name }}
                    </option>
                  {% endfor %}
                </select>
                <button type="submit" class="ca-button"
                  style="margin-top:0.75rem;padding:0.35rem 1rem;font-size:0.85rem;">
                  Speichern
                </button>
              </form>
            </div>
          </details>
          <form method="post" style="display:inline;"
            onsubmit="return confirm('Gruppe löschen?')">
            {% csrf_token %}
            <input type="hidden" name="action" value="delete_group">
            <input type="hidden" name="section" value="{{ section.key }}">
            <input type="hidden" name="name" value="{{ entry.name }}">
            <button type="submit"
              style="margin-left:0.5rem;padding:0.3rem 0.75rem;font-size:0.85rem;
                     background:#fff0f0;border:1px solid #ffb3b3;border-radius:20px;
                     color:#cc0000;cursor:pointer;">
              Löschen
            </button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="3" style="text-align:center;color:#7a7a7a;">Keine Einträge.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <details style="margin-bottom:1rem;">
    <summary class="ca-button"
      style="display:inline;padding:0.35rem 1rem;font-size:0.85rem;cursor:pointer;background:var(--ca-teal-light,#e6f7f6);">
      + Gruppe hinzufügen
    </summary>
    <div style="margin-top:0.75rem;padding:1rem;background:#f5f5f5;border-radius:6px;">
      <form method="post">
        {% csrf_token %}
        <input type="hidden" name="action" value="add_group">
        <input type="hidden" name="section" value="{{ section.key }}">
        <div style="margin-bottom:0.75rem;">
          <label class="ca-label" style="font-size:0.85rem;">Gruppenname</label>
          <input class="input" type="text" name="name" required
            style="font-size:0.85rem;max-width:300px;">
        </div>
        <div style="margin-bottom:0.75rem;">
          <label class="ca-label" style="font-size:0.85rem;">Kanäle</label>
          <select name="channels" multiple size="6"
            style="width:100%;font-size:0.85rem;border:1px solid #ccc;border-radius:4px;padding:0.25rem;">
            {% for ch in all_channels %}
              <option value="{{ ch.id }}">{{ ch.display_name }}</option>
            {% endfor %}
          </select>
        </div>
        <button type="submit" class="ca-button"
          style="padding:0.35rem 1rem;font-size:0.85rem;">
          Hinzufügen
        </button>
      </form>
    </div>
  </details>
  {% endfor %}

  {# ── Whitelist ──────────────────────────────────────────────────────────── #}
  <h2 style="font-weight:700;font-size:1.05rem;margin:1.5rem 0 0.75rem;color:var(--ca-teal);">
    Whitelist
  </h2>
  <table class="table is-fullwidth is-striped" style="font-size:0.9rem;">
    <thead>
      <tr><th>Label</th><th>Mattermost User-ID</th><th></th></tr>
    </thead>
    <tbody>
      {% for name, entry in cfg.whitelist.items %}
      <tr>
        <td>{{ name }}</td>
        <td><code>{{ entry.id }}</code></td>
        <td>
          <form method="post"
            onsubmit="return confirm('Eintrag „{{ name }}" löschen?')">
            {% csrf_token %}
            <input type="hidden" name="action" value="delete_whitelist">
            <input type="hidden" name="name" value="{{ name }}">
            <button type="submit"
              style="padding:0.3rem 0.75rem;font-size:0.85rem;
                     background:#fff0f0;border:1px solid #ffb3b3;border-radius:20px;
                     color:#cc0000;cursor:pointer;">
              Löschen
            </button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="3" style="text-align:center;color:#7a7a7a;">Keine Einträge.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <details>
    <summary class="ca-button"
      style="display:inline;padding:0.35rem 1rem;font-size:0.85rem;cursor:pointer;background:var(--ca-teal-light,#e6f7f6);">
      + Whitelist-Eintrag hinzufügen
    </summary>
    <div style="margin-top:0.75rem;padding:1rem;background:#f5f5f5;border-radius:6px;">
      <form method="post">
        {% csrf_token %}
        <input type="hidden" name="action" value="add_whitelist">
        <div style="margin-bottom:0.75rem;">
          <label class="ca-label" style="font-size:0.85rem;">Label</label>
          <input class="input" type="text" name="name" required
            style="font-size:0.85rem;max-width:300px;">
        </div>
        <div style="margin-bottom:0.75rem;">
          <label class="ca-label" style="font-size:0.85rem;">Mattermost User-ID</label>
          <input class="input" type="text" name="mm_user_id" required
            style="font-size:0.85rem;max-width:300px;">
        </div>
        <button type="submit" class="ca-button"
          style="padding:0.35rem 1rem;font-size:0.85rem;">
          Hinzufügen
        </button>
      </form>
    </div>
  </details>
</div>
{% endblock %}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd webui && uv run pytest tests/test_admin_dashboard.py::ConfigViewTest -v
```

Expected: all pass.

- [ ] **Step 5: Run full webui test suite**

```bash
cd webui && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add webui/broadcast/admin_dashboard/templates/admin_dashboard/config.html \
        webui/tests/test_admin_dashboard.py
git commit -m "feat(webui): admin config view — channel group CRUD with postbot API"
```

---

## Task 8: Final integration check

- [ ] **Step 1: Run all postbot tests**

```bash
cd postbot && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 2: Run all webui tests**

```bash
cd webui && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 3: Commit if any stray files were missed**

```bash
git status
```

If clean, nothing to do. If there are untracked files from earlier steps, add and commit them now.
