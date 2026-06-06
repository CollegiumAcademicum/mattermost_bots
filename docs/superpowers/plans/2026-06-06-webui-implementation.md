# Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Django web interface (`webui`) for broadcasting Mattermost messages, backed by a FastAPI HTTP API added to `postbot`.

**Architecture:** `webui` is a new uv workspace sub-project (Django + LDAP auth) that calls `postbot`'s internal HTTP API to send broadcasts. `postbot` gains a FastAPI server running in the same asyncio event loop as its existing WebSocket loop. Both run as separate Docker containers.

**Tech Stack:** Django 4.2+, django-auth-ldap, FastAPI (already in postbot), uvicorn (already in postbot), requests, gunicorn, pytest-django.

---

## Key Facts (read before coding)

- `postbot/` uses `pythonpath = "."` → `from api.app import ...` resolves to `postbot/api/app.py`
- postbot reads channel groups from `channels.toml` (TOML format) — **not** `channels.json`
- FastAPI and uvicorn are **already** in `postbot/pyproject.toml` — no new postbot deps needed
- `PostBot._async_main` in `postbot/bot.py` is where background tasks and the WebSocket start
- `PostBot._visible_groups` / `_private_groups` are `dict[str, GroupEntry]` (GroupEntry has `.channels: list[str]`)
- `PostBot.cache.get("channels")` returns `{"by_id": {cid: {name, display_name, team_name, team_id}}, "by_name": {...}, "all_rows": [...]}`
- `bot.driver.posts.create_post({"channel_id": ..., "message": ...})` sends a Mattermost post
- The root `Dockerfile` builds postbot from the repo root context; `webui` needs its own `webui/Dockerfile`

---

## File Map

### New files in `postbot/`
| File | Purpose |
|------|---------|
| `postbot/api/__init__.py` | package marker |
| `postbot/api/context.py` | bot singleton (`set_bot` / `get_bot`) |
| `postbot/api/app.py` | FastAPI app, mounts routers |
| `postbot/api/auth.py` | `verify_api_secret` dependency |
| `postbot/api/routes/__init__.py` | package marker |
| `postbot/api/routes/channels.py` | `GET /api/channels` |
| `postbot/api/routes/broadcast.py` | `POST /api/broadcast` |
| `postbot/tests/test_api_channels.py` | tests for channels endpoint |
| `postbot/tests/test_api_broadcast.py` | tests for broadcast endpoint |

### Modified files in `postbot/`
| File | Change |
|------|--------|
| `postbot/config.py` | add `webui_api_secret: str = ""` field |
| `postbot/bot.py` | start uvicorn in `_async_main` when secret is set |

### New `webui/` project
| File | Purpose |
|------|---------|
| `webui/pyproject.toml` | project deps (django, django-auth-ldap, requests, gunicorn) |
| `webui/Dockerfile` | production image |
| `webui/manage.py` | Django management entrypoint |
| `webui/webui/__init__.py` | package marker |
| `webui/webui/settings.py` | Django settings (LDAP, postbot API config from env) |
| `webui/webui/settings_test.py` | test overrides (in-memory DB, no LDAP) |
| `webui/webui/urls.py` | root URL config |
| `webui/webui/wsgi.py` | WSGI entrypoint |
| `webui/broadcast/__init__.py` | package marker |
| `webui/broadcast/apps.py` | AppConfig |
| `webui/broadcast/auth.py` | `CustomLDAPBackend` (maps LDAP group → BotAdmins) |
| `webui/broadcast/urls.py` | broadcast URL namespace |
| `webui/broadcast/views/compose.py` | compose view |
| `webui/broadcast/views/confirm.py` | confirm view |
| `webui/broadcast/views/result.py` | result view |
| `webui/broadcast/services/postbot_client.py` | HTTP calls to postbot API |
| `webui/broadcast/services/channel_service.py` | fetches + caches `/api/channels` |
| `webui/broadcast/templates/base.html` | base layout |
| `webui/broadcast/templates/registration/login.html` | login page |
| `webui/broadcast/templates/broadcast/compose.html` | compose form |
| `webui/broadcast/templates/broadcast/confirm.html` | confirmation page |
| `webui/broadcast/templates/broadcast/result.html` | result page |
| `webui/broadcast/admin_dashboard/__init__.py` | placeholder app |
| `webui/broadcast/admin_dashboard/apps.py` | placeholder AppConfig |
| `webui/tests/__init__.py` | package marker |
| `webui/tests/test_views.py` | Django test client tests |
| `webui/tests/test_services.py` | service unit tests |

### Modified root files
| File | Change |
|------|--------|
| `pyproject.toml` | add `[tool.uv.workspace]` members list |
| `docker-compose.yaml` | new file: define postbot + webui services |

---

## Part 1: postbot HTTP API

---

### Task 1: postbot API scaffolding (config, context, auth, app)

**Files:**
- Modify: `postbot/config.py`
- Create: `postbot/api/__init__.py`
- Create: `postbot/api/context.py`
- Create: `postbot/api/auth.py`
- Create: `postbot/api/routes/__init__.py`
- Create: `postbot/api/app.py`

- [ ] **Step 1: Add `webui_api_secret` to PostBotConfig**

In `postbot/config.py`, add one field after `scheduler_toml_path`:

```python
    scheduler_toml_path: Path = Path("scheduler.toml")
    webui_api_secret: str = ""
```

- [ ] **Step 2: Create `postbot/api/__init__.py`**

```python
```
(empty file)

- [ ] **Step 3: Create `postbot/api/context.py`**

```python
"""Bot singleton shared between API routes and the FastAPI app."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import PostBot

_bot: "PostBot | None" = None


def set_bot(bot: "PostBot") -> None:
    """Store the running PostBot instance for API route access."""
    global _bot
    _bot = bot


def get_bot() -> "PostBot":
    """Return the running PostBot instance. Raises RuntimeError if not set."""
    if _bot is None:
        raise RuntimeError("PostBot not initialized before API request")
    return _bot
```

- [ ] **Step 4: Create `postbot/api/auth.py`**

```python
"""Bearer token authentication dependency for the postbot HTTP API."""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.context import get_bot

_bearer = HTTPBearer()


def verify_api_secret(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> None:
    """Raise 401 if the Bearer token does not match WEBUI_API_SECRET."""
    bot = get_bot()
    if not bot.config.webui_api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API not configured (WEBUI_API_SECRET not set)",
        )
    if credentials.credentials != bot.config.webui_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API secret",
        )
```

- [ ] **Step 5: Create `postbot/api/routes/__init__.py`**

```python
```
(empty file)

- [ ] **Step 6: Create `postbot/api/app.py`**

```python
"""FastAPI application for the postbot HTTP API."""
from fastapi import FastAPI

app = FastAPI(title="postbot API", docs_url=None, redoc_url=None)

# Import routers after app creation to avoid circular imports.
from api.routes import broadcast, channels  # noqa: E402

app.include_router(channels.router)
app.include_router(broadcast.router)
```

- [ ] **Step 7: Verify existing tests still pass**

```bash
cd postbot && uv run --extra dev pytest -v
```

Expected: all existing tests pass (no new tests yet for API).

- [ ] **Step 8: Commit**

```bash
git add postbot/config.py postbot/api/
git commit -m "feat(postbot): scaffold HTTP API module with auth and bot context"
```

---

### Task 2: `GET /api/channels` endpoint + tests

**Files:**
- Create: `postbot/api/routes/channels.py`
- Create: `postbot/tests/test_api_channels.py`

- [ ] **Step 1: Write the failing tests**

Create `postbot/tests/test_api_channels.py`:

```python
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
    assert set(ids) == {"id1", "id2", "id3"}
    assert ids == sorted(ids, key=lambda i: next(
        c["display_name"] for c in individual if c["id"] == i
    ))


def test_get_channels_missing_auth_returns_403():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.get("/api/channels")
    assert resp.status_code == 403


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run --extra dev pytest tests/test_api_channels.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` (channels route doesn't exist yet).

- [ ] **Step 3: Implement `postbot/api/routes/channels.py`**

```python
"""GET /api/channels — returns all channel groups with resolved MM names."""
from fastapi import APIRouter, Depends

from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


def _resolve(channel_ids: list[str], by_id: dict) -> list[dict]:
    result = []
    for cid in channel_ids:
        info = by_id.get(cid, {})
        result.append({
            "id": cid,
            "display_name": info.get("display_name", cid),
            "channel_name": info.get("name", cid),
        })
    return result


@router.get("/api/channels", dependencies=[Depends(verify_api_secret)])
def get_channels() -> dict:
    """Return all channel groups with Mattermost display and system names."""
    bot = get_bot()
    ch_cache = bot.cache.get("channels") or {}
    by_id: dict = ch_cache.get("by_id", {})

    groups = {
        name: _resolve(entry.channels, by_id)
        for name, entry in bot._visible_groups.items()
    }
    private_groups = {
        name: _resolve(entry.channels, by_id)
        for name, entry in bot._private_groups.items()
    }

    # All unique channel IDs across every group, sorted by display name.
    all_ids: set[str] = set()
    for entry in list(bot._visible_groups.values()) + list(bot._private_groups.values()):
        all_ids.update(entry.channels)
    individual = _resolve(list(all_ids), by_id)
    individual.sort(key=lambda c: c["display_name"])

    return {
        "groups": groups,
        "private_groups": private_groups,
        "individual_channels": individual,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd postbot && uv run --extra dev pytest tests/test_api_channels.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add postbot/api/routes/channels.py postbot/tests/test_api_channels.py
git commit -m "feat(postbot): add GET /api/channels endpoint"
```

---

### Task 3: `POST /api/broadcast` endpoint + tests

**Files:**
- Create: `postbot/api/routes/broadcast.py`
- Create: `postbot/tests/test_api_broadcast.py`

- [ ] **Step 1: Write the failing tests**

Create `postbot/tests/test_api_broadcast.py`:

```python
"""Tests for POST /api/broadcast."""
from unittest.mock import MagicMock, call

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


def test_broadcast_requires_auth():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": ["id1"]},
    )
    assert resp.status_code == 403


def test_broadcast_wrong_secret_returns_401():
    set_bot(_make_bot())
    client = TestClient(app)
    resp = client.post(
        "/api/broadcast",
        json={"message": "Hello", "channel_ids": ["id1"]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run --extra dev pytest tests/test_api_broadcast.py -v
```

Expected: `ImportError` (broadcast route doesn't exist yet).

- [ ] **Step 3: Implement `postbot/api/routes/broadcast.py`**

```python
"""POST /api/broadcast — send a message to a list of Mattermost channels."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import verify_api_secret
from api.context import get_bot

logger = logging.getLogger(__name__)
router = APIRouter()


class BroadcastRequest(BaseModel):
    message: str
    channel_ids: list[str]
    sender: str = "Web Interface"


class BroadcastResponse(BaseModel):
    sent: int
    failed: int
    errors: list[str]


@router.post("/api/broadcast", dependencies=[Depends(verify_api_secret)])
def post_broadcast(body: BroadcastRequest) -> BroadcastResponse:
    """Send `body.message` to each channel in `body.channel_ids`."""
    bot = get_bot()
    broadcast_text = (
        f"📢 **Message from {body.sender}**\n\n\n"
        f"{body.message}"
        f"\n\n\n\n*--- END of Message ---*\n"
    )
    sent = 0
    failed = 0
    errors: list[str] = []

    for channel_id in body.channel_ids:
        try:
            bot.driver.posts.create_post(
                {"channel_id": channel_id, "message": broadcast_text}
            )
            sent += 1
            logger.info(f"API broadcast: posted to channel {channel_id!r}")
        except Exception as exc:
            failed += 1
            errors.append(f"{channel_id}: {exc}")
            logger.error(
                f"API broadcast: failed to post to channel {channel_id!r}: {exc}"
            )

    return BroadcastResponse(sent=sent, failed=failed, errors=errors)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd postbot && uv run --extra dev pytest tests/test_api_broadcast.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run the full postbot test suite**

```bash
cd postbot && uv run --extra dev pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add postbot/api/routes/broadcast.py postbot/tests/test_api_broadcast.py
git commit -m "feat(postbot): add POST /api/broadcast endpoint"
```

---

### Task 4: Wire uvicorn into `PostBot._async_main`

**Files:**
- Modify: `postbot/bot.py`

- [ ] **Step 1: Add uvicorn import to `postbot/bot.py`**

At the top of `postbot/bot.py`, add after the existing imports:

```python
import uvicorn
```

- [ ] **Step 2: Modify `_async_main` to start the API server**

In `postbot/bot.py`, find `_async_main`. Replace the method body with the version below. The only changes are the three blocks marked with `# NEW`:

```python
    async def _async_main(self) -> None:
        """Start background tasks and open WebSocket.

        If WEBUI_API_SECRET is set, also starts a FastAPI HTTP server on
        port 8000 for the web UI to call.
        """
        await self.on_start()

        # NEW: start the HTTP API server if a secret is configured.
        api_server: uvicorn.Server | None = None
        api_task = None
        if self.config.webui_api_secret:
            from api.app import app  # noqa: PLC0415
            from api.context import set_bot  # noqa: PLC0415

            set_bot(self)
            uv_config = uvicorn.Config(
                app, host="0.0.0.0", port=8000, loop="none", log_level="warning"
            )
            api_server = uvicorn.Server(uv_config)
            api_task = asyncio.create_task(api_server.serve())
            logger.info("HTTP API server started on 0.0.0.0:8000.")

        cleanup_task = asyncio.create_task(self._session_cleanup_loop())
        cache_task = asyncio.create_task(self._cache_refresh_loop())
        scheduler_task = asyncio.create_task(
            task_runner.scheduler_loop(
                self._task_registry,
                self.driver,
                self._post,
                self.config.bot_log_channel_id,
            )
        )

        async def _raw_ws_handler(raw_msg: str | dict) -> None:
            raw_str = raw_msg if isinstance(raw_msg, str) else json.dumps(raw_msg)
            msg = ParsedMessage.from_raw(raw_str)
            if msg is not None:
                await self._pipeline.run(msg, self._dispatch)

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
            scheduler_task.cancel()
            # NEW: shut down HTTP API if it was started.
            if api_server is not None and api_task is not None:
                api_server.should_exit = True
                try:
                    await api_task
                except asyncio.CancelledError:
                    pass
            for task in (cleanup_task, cache_task, scheduler_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
```

- [ ] **Step 3: Run the full postbot test suite to verify no regressions**

```bash
cd postbot && uv run --extra dev pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add postbot/bot.py
git commit -m "feat(postbot): start uvicorn HTTP API in _async_main when WEBUI_API_SECRET is set"
```

---

## Part 2: webui Django Project

---

### Task 5: Scaffold the webui Django project

**Files:**
- Create: `webui/pyproject.toml`
- Create: `webui/manage.py`
- Create: `webui/webui/__init__.py`
- Create: `webui/webui/settings.py`
- Create: `webui/webui/settings_test.py`
- Create: `webui/webui/urls.py`
- Create: `webui/webui/wsgi.py`
- Create: `webui/broadcast/__init__.py`
- Create: `webui/broadcast/apps.py`
- Create: `webui/broadcast/admin_dashboard/__init__.py`
- Create: `webui/broadcast/admin_dashboard/apps.py`
- Create: `webui/tests/__init__.py`
- Modify: `pyproject.toml` (root)

- [ ] **Step 1: Create `webui/pyproject.toml`**

```toml
[project]
name = "webui"
version = "0.1.0"
description = "Mattermost broadcast web interface"
requires-python = ">=3.14"
dependencies = [
    "django>=4.2",
    "django-auth-ldap>=4.8",
    "requests>=2.33",
    "gunicorn>=22.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-django>=4.9",
    "pytest-cov>=7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["."]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
DJANGO_SETTINGS_MODULE = "webui.settings_test"
```

- [ ] **Step 2: Create `webui/manage.py`**

```python
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webui.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create `webui/webui/__init__.py`** (empty)

- [ ] **Step 4: Create `webui/webui/settings.py`**

```python
"""Django settings for webui."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-do-not-use-in-production")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "broadcast",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "webui.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "webui.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/broadcast/"
LOGOUT_REDIRECT_URL = "/login/"

AUTHENTICATION_BACKENDS = [
    "broadcast.auth.CustomLDAPBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# LDAP — configured via environment variables.
# django-auth-ldap reads AUTH_LDAP_* settings automatically.
import ldap  # noqa: E402
from django_auth_ldap.config import LDAPSearch  # noqa: E402

AUTH_LDAP_SERVER_URI = os.environ.get("LDAP_SERVER_URI", "ldap://localhost")
AUTH_LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
AUTH_LDAP_USER_SEARCH = LDAPSearch(
    os.environ.get("LDAP_USER_SEARCH_BASE", "dc=example,dc=com"),
    ldap.SCOPE_SUBTREE,
    "(uid=%(user)s)",
)
AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}
# DN of the LDAP group whose members become "BotAdmins" in Django.
LDAP_ADMIN_GROUP_DN = os.environ.get("LDAP_ADMIN_GROUP_DN", "")

# postbot HTTP API
POSTBOT_API_URL = os.environ.get("POSTBOT_API_URL", "http://localhost:8000")
POSTBOT_API_SECRET = os.environ.get("POSTBOT_API_SECRET", "")
```

- [ ] **Step 5: Create `webui/webui/settings_test.py`**

```python
"""Test settings: skip LDAP imports, use in-memory DB."""
# Override LDAP and ModelBackend only — no python-ldap needed in CI.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "broadcast",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "webui.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/broadcast/"
LOGOUT_REDIRECT_URL = "/login/"
POSTBOT_API_URL = "http://postbot-test:8000"
POSTBOT_API_SECRET = "test-secret"
STATIC_URL = "static/"
```

- [ ] **Step 6: Create `webui/webui/urls.py`**

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
]
```

- [ ] **Step 7: Create `webui/webui/wsgi.py`**

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webui.settings")
application = get_wsgi_application()
```

- [ ] **Step 8: Create `webui/broadcast/__init__.py`** (empty)

- [ ] **Step 9: Create `webui/broadcast/apps.py`**

```python
from django.apps import AppConfig


class BroadcastConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "broadcast"
```

- [ ] **Step 10: Create `webui/broadcast/admin_dashboard/__init__.py`** (empty)

- [ ] **Step 11: Create `webui/broadcast/admin_dashboard/apps.py`**

```python
from django.apps import AppConfig


class AdminDashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "broadcast.admin_dashboard"
    label = "admin_dashboard"
```

- [ ] **Step 12: Create `webui/tests/__init__.py`** (empty)

- [ ] **Step 13: Update root `pyproject.toml` to declare the workspace**

Replace the entire content of `/pyproject.toml` with:

```toml
[project]
name = "mattermost-bots"
version = "0.1.0"
description = "Mattermost bots monorepo"
readme = "README.md"
requires-python = ">=3.14"

[tool.uv.workspace]
members = ["postbot", "mmbot_framework", "webui"]

[tool.uv.sources]
mailman = { workspace = true }
mmbot-framework = { workspace = true }
webui = { workspace = true }
```

- [ ] **Step 14: Install webui dependencies**

```bash
cd webui && uv sync --extra dev
```

Expected: Django, django-auth-ldap, pytest-django installed.

- [ ] **Step 15: Run migrations and verify the project loads**

```bash
cd webui && uv run python manage.py migrate --settings=webui.settings_test
```

Expected: migration runs without error.

- [ ] **Step 16: Commit**

```bash
git add webui/ pyproject.toml
git commit -m "feat(webui): scaffold Django project with settings, urls, apps"
```

---

### Task 6: LDAP + local auth backend

**Files:**
- Create: `webui/broadcast/auth.py`

- [ ] **Step 1: Create `webui/broadcast/auth.py`**

```python
"""Custom LDAP authentication backend.

Maps a configured LDAP group (LDAP_ADMIN_GROUP_DN) to the Django group
"BotAdmins" on every successful LDAP login. Falls through to
ModelBackend for local accounts (Django's default multi-backend behaviour).
"""
import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django_auth_ldap.backend import LDAPBackend

logger = logging.getLogger(__name__)


class CustomLDAPBackend(LDAPBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None:
            self._sync_bot_admins_group(user)
        return user

    def _sync_bot_admins_group(self, user) -> None:
        """Add or remove user from BotAdmins based on their LDAP group membership."""
        admin_group_dn = getattr(settings, "LDAP_ADMIN_GROUP_DN", "")
        if not admin_group_dn:
            return
        try:
            ldap_groups: list[str] = user.ldap_user.attrs.get("memberOf", [])
            group, _ = Group.objects.get_or_create(name="BotAdmins")
            if admin_group_dn in ldap_groups:
                user.groups.add(group)
                logger.info(f"User {user.username!r} added to BotAdmins.")
            else:
                user.groups.remove(group)
        except Exception as exc:
            logger.error(
                f"Failed to sync BotAdmins group for {user.username!r}: {exc}"
            )
```

Note: `broadcast/auth.py` is the `CustomLDAPBackend` referenced in `settings.py` as `"broadcast.auth.CustomLDAPBackend"`. No tests are written for it here — LDAP auth is tested via integration with a real LDAP server; unit-testing it would require mocking the entire `django-auth-ldap` stack, which CAWash also defers.

- [ ] **Step 2: Commit**

```bash
git add webui/broadcast/auth.py
git commit -m "feat(webui): add CustomLDAPBackend with BotAdmins group sync"
```

---

### Task 7: Services — `channel_service` and `postbot_client`

**Files:**
- Create: `webui/broadcast/services/__init__.py`
- Create: `webui/broadcast/services/channel_service.py`
- Create: `webui/broadcast/services/postbot_client.py`
- Test in: `webui/tests/test_services.py`

- [ ] **Step 1: Write the failing service tests**

Create `webui/tests/test_services.py`:

```python
"""Tests for postbot_client and channel_service."""
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import TestCase, override_settings


@override_settings(
    POSTBOT_API_URL="http://postbot:8000",
    POSTBOT_API_SECRET="test-secret",
)
class PostbotClientTest(TestCase):
    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sent": 2, "failed": 0, "errors": []}
        mock_post.return_value = mock_resp

        from broadcast.services.postbot_client import send_broadcast

        result = send_broadcast("Hello world", ["id1", "id2"], sender="alice")

        self.assertEqual(result["sent"], 2)
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["message"], "Hello world")
        self.assertEqual(call_kwargs["json"]["channel_ids"], ["id1", "id2"])
        self.assertEqual(call_kwargs["json"]["sender"], "alice")
        self.assertIn("Bearer test-secret", call_kwargs["headers"]["Authorization"])

    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_connection_error_raises(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("unreachable")

        from broadcast.services.postbot_client import send_broadcast

        with self.assertRaises(requests.ConnectionError):
            send_broadcast("Hello", ["id1"])

    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_http_error_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        from broadcast.services.postbot_client import send_broadcast

        with self.assertRaises(requests.HTTPError):
            send_broadcast("Hello", ["id1"])


@override_settings(
    POSTBOT_API_URL="http://postbot:8000",
    POSTBOT_API_SECRET="test-secret",
)
class ChannelServiceTest(TestCase):
    def setUp(self):
        # Reset module-level cache between tests.
        import broadcast.services.channel_service as cs
        cs._cache = {}
        cs._cache_time = 0.0

    @patch("broadcast.services.channel_service.requests.get")
    def test_get_channels_fetches_and_caches(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "groups": {"G": [{"id": "id1", "display_name": "D", "channel_name": "d"}]},
            "private_groups": {},
            "individual_channels": [],
        }
        mock_get.return_value = mock_resp

        from broadcast.services.channel_service import get_channels

        result1 = get_channels()
        result2 = get_channels()  # Should use cache

        self.assertIn("G", result1["groups"])
        self.assertEqual(mock_get.call_count, 1)  # fetched only once

    @patch("broadcast.services.channel_service.requests.get")
    def test_get_channels_returns_stale_cache_on_error(self, mock_get):
        import broadcast.services.channel_service as cs

        # Pre-populate cache.
        cs._cache = {"groups": {"Old": []}, "private_groups": {}, "individual_channels": []}
        cs._cache_time = 0.0  # expired

        mock_get.side_effect = requests.ConnectionError("unreachable")

        from broadcast.services.channel_service import get_channels

        result = get_channels()
        self.assertIn("Old", result["groups"])  # stale cache returned
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd webui && uv run --group dev pytest tests/test_services.py -v
```

Expected: `ModuleNotFoundError` (services don't exist yet).

- [ ] **Step 3: Create `webui/broadcast/services/__init__.py`** (empty)

- [ ] **Step 4: Create `webui/broadcast/services/postbot_client.py`**

```python
"""HTTP client for the postbot broadcast API."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_broadcast(
    message: str,
    channel_ids: list[str],
    sender: str = "Web Interface",
) -> dict:
    """POST /api/broadcast on postbot. Returns {"sent", "failed", "errors"}.

    Raises requests.ConnectionError if postbot is unreachable.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.post(
        f"{settings.POSTBOT_API_URL}/api/broadcast",
        json={"message": message, "channel_ids": channel_ids, "sender": sender},
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 5: Create `webui/broadcast/services/channel_service.py`**

```python
"""Fetches and caches channel data from postbot's /api/channels endpoint."""
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds
_cache: dict = {}
_cache_time: float = 0.0


def get_channels() -> dict:
    """Return channel data from postbot. Caches for 5 minutes.

    On fetch failure, returns the last known good cache (may be empty dict
    on first call if postbot is unreachable).
    """
    global _cache, _cache_time
    now = time.monotonic()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache
    try:
        resp = requests.get(
            f"{settings.POSTBOT_API_URL}/api/channels",
            headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
            timeout=5,
        )
        resp.raise_for_status()
        _cache = resp.json()
        _cache_time = now
    except Exception as exc:
        logger.error(f"Failed to fetch channels from postbot API: {exc}")
    return _cache
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd webui && uv run --group dev pytest tests/test_services.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add webui/broadcast/services/ webui/tests/test_services.py
git commit -m "feat(webui): add channel_service and postbot_client services"
```

---

### Task 8: Broadcast URL config and view stubs

**Files:**
- Create: `webui/broadcast/urls.py`
- Create: `webui/broadcast/views/__init__.py`
- Create: `webui/broadcast/views/compose.py`
- Create: `webui/broadcast/views/confirm.py`
- Create: `webui/broadcast/views/result.py`

- [ ] **Step 1: Create `webui/broadcast/urls.py`**

```python
from django.urls import path

from broadcast.views import compose, confirm, result

app_name = "broadcast"

urlpatterns = [
    path("", compose.compose, name="compose"),
    path("confirm/", confirm.confirm, name="confirm"),
    path("result/", result.result, name="result"),
]
```

- [ ] **Step 2: Create `webui/broadcast/views/__init__.py`** (empty)

- [ ] **Step 3: Write failing view tests**

Create `webui/tests/test_views.py`:

```python
"""Django test-client tests for broadcast views."""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

MOCK_CHANNELS = {
    "groups": {
        "Group A": [
            {"id": "id1", "display_name": "Channel One", "channel_name": "channel-one"}
        ],
    },
    "private_groups": {},
    "individual_channels": [
        {"id": "id1", "display_name": "Channel One", "channel_name": "channel-one"},
        {"id": "id2", "display_name": "Channel Two", "channel_name": "channel-two"},
    ],
}


class ComposeViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_get_renders_channel_groups(self, _):
        resp = self.client.get(reverse("broadcast:compose"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Group A")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_valid_redirects_to_confirm(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello world", "groups": ["Group A"]},
        )
        self.assertRedirects(resp, reverse("broadcast:confirm"))

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_stores_selections_in_session(self, _):
        self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello", "groups": ["Group A"]},
        )
        session = self.client.session
        self.assertEqual(session["broadcast_message"], "Hello")
        self.assertEqual(session["broadcast_groups"], ["Group A"])

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_empty_message_shows_error(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"groups": ["Group A"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Message cannot be empty")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_no_channel_selection_shows_error(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Select at least one")

    def test_get_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("broadcast:compose"))
        self.assertRedirects(resp, "/login/?next=/broadcast/")


class ConfirmViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")
        session = self.client.session
        session["broadcast_message"] = "Hello world"
        session["broadcast_groups"] = ["Group A"]
        session["broadcast_individual"] = []
        session.save()

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    def test_get_shows_message_and_channels(self, _):
        resp = self.client.get(reverse("broadcast:confirm"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hello world")
        self.assertContains(resp, "Channel One")

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    @patch(
        "broadcast.views.confirm.send_broadcast",
        return_value={"sent": 1, "failed": 0, "errors": []},
    )
    def test_post_send_calls_postbot_and_redirects(self, mock_send, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "send"})
        self.assertRedirects(resp, reverse("broadcast:result"))
        mock_send.assert_called_once_with("Hello world", ["id1"], sender="testuser")

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    def test_post_back_redirects_to_compose(self, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "back"})
        self.assertRedirects(resp, reverse("broadcast:compose"))

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    @patch(
        "broadcast.views.confirm.send_broadcast",
        side_effect=__import__("requests").ConnectionError("unreachable"),
    )
    def test_post_send_postbot_unreachable_shows_error(self, mock_send, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "send"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "unreachable")

    def test_get_without_session_redirects_to_compose(self):
        session = self.client.session
        del session["broadcast_message"]
        session.save()
        resp = self.client.get(reverse("broadcast:confirm"))
        self.assertRedirects(resp, reverse("broadcast:compose"))


class ResultViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")
        session = self.client.session
        session["broadcast_result"] = {"sent": 3, "failed": 0, "errors": []}
        session.save()

    def test_get_shows_sent_count(self):
        resp = self.client.get(reverse("broadcast:result"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "3")

    def test_get_clears_result_from_session(self):
        self.client.get(reverse("broadcast:result"))
        self.assertNotIn("broadcast_result", self.client.session)

    def test_get_without_session_redirects_to_compose(self):
        session = self.client.session
        del session["broadcast_result"]
        session.save()
        resp = self.client.get(reverse("broadcast:result"))
        self.assertRedirects(resp, reverse("broadcast:compose"))
```

- [ ] **Step 4: Run tests to confirm they fail**

```bash
cd webui && uv run --group dev pytest tests/test_views.py -v
```

Expected: `ImportError` (view modules don't exist yet).

- [ ] **Step 5: Create `webui/broadcast/views/compose.py`**

```python
"""Compose broadcast view — step 1 of 3."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from broadcast.services.channel_service import get_channels

logger = logging.getLogger(__name__)


@login_required
def compose(request):
    if request.method == "POST":
        message = request.POST.get("message", "").strip()
        selected_groups = request.POST.getlist("groups")
        selected_individual = request.POST.getlist("individual_channels")

        if not message:
            messages.error(request, "Message cannot be empty.")
        elif not selected_groups and not selected_individual:
            messages.error(request, "Select at least one channel or group.")
        else:
            request.session["broadcast_message"] = message
            request.session["broadcast_groups"] = selected_groups
            request.session["broadcast_individual"] = selected_individual
            return redirect("broadcast:confirm")

    try:
        channels_data = get_channels()
    except Exception as exc:
        logger.error(f"Failed to load channels: {exc}")
        messages.warning(request, "Could not load channels — postbot may be unavailable.")
        channels_data = {}

    return render(request, "broadcast/compose.html", {"channels_data": channels_data})
```

- [ ] **Step 6: Create `webui/broadcast/views/confirm.py`**

```python
"""Confirm broadcast view — step 2 of 3."""
import logging

import requests as http_requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from broadcast.services.channel_service import get_channels
from broadcast.services.postbot_client import send_broadcast

logger = logging.getLogger(__name__)


def _resolve_channel_ids(
    selected_groups: list[str],
    selected_individual: list[str],
    channels_data: dict,
) -> tuple[list[str], list[str]]:
    """Return (deduplicated channel_ids, human-readable names) from session selections."""
    channel_ids: set[str] = set()
    resolved_names: list[str] = []

    all_groups = {
        **channels_data.get("groups", {}),
        **channels_data.get("private_groups", {}),
    }
    for group_name in selected_groups:
        for ch in all_groups.get(group_name, []):
            if ch["id"] not in channel_ids:
                channel_ids.add(ch["id"])
                resolved_names.append(f"{ch['display_name']} (group: {group_name})")

    by_id = {c["id"]: c for c in channels_data.get("individual_channels", [])}
    for ch_id in selected_individual:
        if ch_id not in channel_ids and ch_id in by_id:
            channel_ids.add(ch_id)
            resolved_names.append(by_id[ch_id]["display_name"])

    return list(channel_ids), resolved_names


@login_required
def confirm(request):
    message = request.session.get("broadcast_message")
    if not message:
        return redirect("broadcast:compose")

    selected_groups = request.session.get("broadcast_groups", [])
    selected_individual = request.session.get("broadcast_individual", [])
    channels_data = get_channels()
    channel_ids, resolved_names = _resolve_channel_ids(
        selected_groups, selected_individual, channels_data
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "back":
            return redirect("broadcast:compose")
        if action == "send":
            try:
                result = send_broadcast(
                    message, channel_ids, sender=request.user.username
                )
                for key in ("broadcast_message", "broadcast_groups", "broadcast_individual"):
                    request.session.pop(key, None)
                request.session["broadcast_result"] = result
                return redirect("broadcast:result")
            except http_requests.ConnectionError:
                messages.error(
                    request, "postbot is unreachable. Please try again later."
                )
            except http_requests.HTTPError as exc:
                messages.error(request, f"Broadcast failed: {exc}")

    return render(
        request,
        "broadcast/confirm.html",
        {"message": message, "resolved_names": resolved_names, "channel_ids": channel_ids},
    )
```

- [ ] **Step 7: Create `webui/broadcast/views/result.py`**

```python
"""Result view — step 3 of 3."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def result(request):
    result_data = request.session.pop("broadcast_result", None)
    if result_data is None:
        return redirect("broadcast:compose")
    return render(request, "broadcast/result.html", {"result": result_data})
```

- [ ] **Step 8: Run tests to confirm they fail (templates missing)**

```bash
cd webui && uv run --group dev pytest tests/test_views.py -v
```

Expected: `TemplateDoesNotExist` errors — templates not created yet.

- [ ] **Step 9: Commit views before adding templates**

```bash
git add webui/broadcast/urls.py webui/broadcast/views/ webui/tests/test_views.py
git commit -m "feat(webui): add compose, confirm, result views with tests"
```

---

### Task 9: Templates

**Files:**
- Create: `webui/broadcast/templates/base.html`
- Create: `webui/broadcast/templates/registration/login.html`
- Create: `webui/broadcast/templates/broadcast/compose.html`
- Create: `webui/broadcast/templates/broadcast/confirm.html`
- Create: `webui/broadcast/templates/broadcast/result.html`

Note: Django's `APP_DIRS=True` means templates are looked up at `broadcast/templates/`. The `registration/login.html` path is the default expected by Django's `LoginView`.

- [ ] **Step 1: Create `webui/broadcast/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Broadcast{% endblock %}</title>
</head>
<body>
<nav>
    {% if user.is_authenticated %}
        Logged in as <strong>{{ user.username }}</strong>
        &nbsp;|&nbsp;
        <a href="{% url 'logout' %}">Logout</a>
    {% endif %}
</nav>
<hr>
{% if messages %}
    {% for msg in messages %}
        <div class="messages {{ msg.tags }}"><strong>{{ msg }}</strong></div>
    {% endfor %}
{% endif %}
{% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create `webui/broadcast/templates/registration/login.html`**

```html
{% extends "base.html" %}
{% block title %}Login{% endblock %}
{% block content %}
<h1>Login</h1>
<form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Login</button>
</form>
{% endblock %}
```

- [ ] **Step 3: Create `webui/broadcast/templates/broadcast/compose.html`**

```html
{% extends "base.html" %}
{% block title %}Compose Broadcast{% endblock %}
{% block content %}
<h1>Compose Broadcast</h1>
<form method="post">
    {% csrf_token %}

    <h2>Message</h2>
    <textarea name="message" rows="8" cols="80" required>{{ request.session.broadcast_message|default:'' }}</textarea>

    <h2>Groups</h2>
    {% for group_name, channels in channels_data.groups.items %}
        <label>
            <input type="checkbox" name="groups" value="{{ group_name }}">
            <strong>{{ group_name }}</strong> ({{ channels|length }} channels)
        </label><br>
    {% empty %}
        <em>No groups available.</em>
    {% endfor %}

    {% if channels_data.private_groups %}
    <h3>Private Groups</h3>
    {% for group_name, channels in channels_data.private_groups.items %}
        <label>
            <input type="checkbox" name="groups" value="{{ group_name }}">
            <strong>{{ group_name }}</strong> ({{ channels|length }} channels)
        </label><br>
    {% endfor %}
    {% endif %}

    <details>
        <summary>Individual Channels</summary>
        {% for ch in channels_data.individual_channels %}
            <label>
                <input type="checkbox" name="individual_channels" value="{{ ch.id }}">
                {{ ch.display_name }}
                {% if ch.display_name != ch.channel_name %}
                    <small>({{ ch.channel_name }})</small>
                {% endif %}
            </label><br>
        {% empty %}
            <em>No individual channels available.</em>
        {% endfor %}
    </details>

    <br>
    <button type="submit">Preview &amp; Confirm</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Create `webui/broadcast/templates/broadcast/confirm.html`**

```html
{% extends "base.html" %}
{% block title %}Confirm Broadcast{% endblock %}
{% block content %}
<h1>Confirm Broadcast</h1>

<h2>Message</h2>
<pre style="border:1px solid #ccc; padding:1em;">{{ message }}</pre>

<h2>Target Channels ({{ resolved_names|length }})</h2>
<ul>
    {% for name in resolved_names %}
        <li>{{ name }}</li>
    {% empty %}
        <li><em>No channels selected.</em></li>
    {% endfor %}
</ul>

<form method="post">
    {% csrf_token %}
    <button type="submit" name="action" value="send">Send Broadcast</button>
    &nbsp;
    <button type="submit" name="action" value="back">Go Back</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Create `webui/broadcast/templates/broadcast/result.html`**

```html
{% extends "base.html" %}
{% block title %}Broadcast Result{% endblock %}
{% block content %}
<h1>Broadcast Result</h1>

{% if result.failed == 0 %}
    <p>✅ Sent successfully to {{ result.sent }} channel(s).</p>
{% elif result.sent == 0 %}
    <p>❌ Broadcast failed — could not send to any channel.</p>
    <ul>
        {% for err in result.errors %}<li>{{ err }}</li>{% endfor %}
    </ul>
{% else %}
    <p>⚠️ Partially sent: {{ result.sent }} succeeded, {{ result.failed }} failed.</p>
    <ul>
        {% for err in result.errors %}<li>{{ err }}</li>{% endfor %}
    </ul>
{% endif %}

<p><a href="{% url 'broadcast:compose' %}">Send Another Broadcast</a></p>
{% endblock %}
```

- [ ] **Step 6: Run the full webui test suite**

```bash
cd webui && uv run --group dev pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add webui/broadcast/templates/
git commit -m "feat(webui): add HTML templates for login, compose, confirm, result"
```

---

## Part 3: Deployment

---

### Task 10: Dockerfiles and docker-compose

**Files:**
- Create: `webui/Dockerfile`
- Create: `docker-compose.yaml`

Note: The existing root `Dockerfile` builds postbot. It needs no changes — the new `api/` module is inside `postbot/` and is included automatically when the entire repo is copied into the image.

- [ ] **Step 1: Create `webui/Dockerfile`**

```dockerfile
FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-group dev

COPY . .

RUN python manage.py collectstatic --noinput --settings=webui.settings

EXPOSE 8080

CMD ["uv", "run", "gunicorn", "webui.wsgi:application", \
     "--bind", "0.0.0.0:8080", "--workers", "2"]
```

- [ ] **Step 2: Create `docker-compose.yaml` at the repo root**

```yaml
services:
  postbot:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - MATTERMOST_URL
      - BOT_TOKEN
      - TEAM_NAME
      - WEBUI_API_SECRET
    volumes:
      - ./channels.toml:/app/postbot/channels.toml:ro
    networks:
      - internal
    restart: unless-stopped

  webui:
    build:
      context: ./webui
      dockerfile: Dockerfile
    environment:
      - DJANGO_SECRET_KEY
      - LDAP_SERVER_URI
      - LDAP_BIND_DN
      - LDAP_BIND_PASSWORD
      - LDAP_USER_SEARCH_BASE
      - LDAP_ADMIN_GROUP_DN
      - POSTBOT_API_URL=http://postbot:8000
      - POSTBOT_API_SECRET=${WEBUI_API_SECRET}
    ports:
      - "8080:8080"
    networks:
      - internal
    depends_on:
      - postbot
    restart: unless-stopped

networks:
  internal:
    driver: bridge
```

Note: `POSTBOT_API_SECRET` in webui is set to the same value as `WEBUI_API_SECRET` in postbot — they must match. Both read from the same `.env` file via `${WEBUI_API_SECRET}`.

- [ ] **Step 3: Run the full test suites for both components**

```bash
cd postbot && uv run --extra dev pytest -v
cd ../webui && uv run --group dev pytest -v
```

Expected: all tests pass in both suites.

- [ ] **Step 4: Commit**

```bash
git add webui/Dockerfile docker-compose.yaml
git commit -m "feat: add docker-compose and webui Dockerfile for containerized deployment"
```

---

## Self-Review Checklist

- [x] **Spec Section 1 (Architecture):** Covered by Tasks 1–4 (FastAPI in postbot) and Tasks 5–9 (Django webui sub-project) and Task 10 (docker-compose).
- [x] **Spec Section 2 (Auth):** Task 6 (CustomLDAPBackend), `settings.py` AUTHENTICATION_BACKENDS in Task 5.
- [x] **Spec Section 3 (Broadcast flow):** Tasks 8–9 (compose → confirm → result views and templates).
- [x] **Spec Section 4 (postbot API):** Tasks 1–4.
- [x] **Spec Section 5 (Project structure):** Tasks 5–9 create the exact file layout from the spec.
- [x] **Spec Section 6 (Deployment):** Task 10.
- [x] **Spec Section 7 (Error handling & testing):** Connection errors handled in confirm view; test suites in Tasks 2, 3, 7, 8.
- [x] **Spec Section 8 (Admin dashboard placeholder):** `broadcast/admin_dashboard/` created as placeholder in Task 5.
- [x] **Spec Note (whitelist irrelevant to webui):** postbot API does not check whitelist; broadcast endpoint sends to any channel ID provided by the authenticated webui user.
- [x] **channels.toml vs channels.json:** Plan uses `channels.toml` (matching actual bot config) in docker-compose volume mount.
- [x] **Type consistency:** `GroupEntry` used in tests matches `bot.py` import; `send_broadcast` signature (`message, channel_ids, sender`) consistent across `postbot_client.py`, `confirm.py`, and tests.
