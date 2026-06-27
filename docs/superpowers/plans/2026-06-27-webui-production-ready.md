# Webui Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the webui Django/Gunicorn server with security settings, configurable Gunicorn workers, stdout logging, and a health check endpoint.

**Architecture:** All changes are in-place — no new Django apps, no settings split. Security settings follow the existing env-var pattern in `settings.py`. Gunicorn config is extracted to a dedicated `gunicorn.conf.py`. The health check is a one-function view added directly to the root URL conf.

**Tech Stack:** Django 4.2+, Gunicorn 22+, WhiteNoise, Python 3.14, uv

## Global Constraints

- Python >= 3.14
- All new env vars default to safe/disabled values
- Tests run with: `cd webui && uv run --group dev pytest -v`
- Test settings module: `webui.settings_test` (set in `pyproject.toml` — pytest uses this, not `webui.settings`)
- No new Django apps

---

### Task 1: Gunicorn configuration file + Dockerfile update

**Files:**
- Create: `webui/gunicorn.conf.py`
- Modify: `webui/Dockerfile` (CMD line only)

**Interfaces:**
- Consumes: nothing
- Produces: `gunicorn.conf.py` — reads `GUNICORN_WORKERS` (default `"2"`), `GUNICORN_TIMEOUT` (default `"30"`), `GUNICORN_LOG_LEVEL` (default `"info"`) from `os.environ` at Gunicorn startup

- [ ] **Step 1: Create `webui/gunicorn.conf.py`**

```python
import os

bind = "0.0.0.0:8080"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
accesslog = "-"
errorlog = "-"
worker_tmp_dir = "/dev/shm"
```

- [ ] **Step 2: Verify it is valid Python**

```bash
cd webui && python gunicorn.conf.py
```

Expected: exits 0 with no output.

- [ ] **Step 3: Update `webui/Dockerfile` CMD**

Current line:
```
CMD ["sh", "-c", "uv run python manage.py migrate --settings=webui.settings && uv run python manage.py collectstatic --noinput --settings=webui.settings && uv run python manage.py createsuperuser --noinput --settings=webui.settings || true && uv run gunicorn webui.wsgi:application --bind 0.0.0.0:8080 --workers 2"]
```

Replace with:
```
CMD ["sh", "-c", "uv run python manage.py migrate --settings=webui.settings && uv run python manage.py collectstatic --noinput --settings=webui.settings && uv run python manage.py createsuperuser --noinput --settings=webui.settings || true && uv run gunicorn webui.wsgi:application --config gunicorn.conf.py"]
```

- [ ] **Step 4: Commit**

```bash
git add webui/gunicorn.conf.py webui/Dockerfile
git commit -m "feat(webui): extract gunicorn config with env-var workers and stdout logging"
```

---

### Task 2: Django security settings + logging

**Files:**
- Modify: `webui/webui/settings.py`
- Create: `webui/tests/test_settings.py`

**Interfaces:**
- Consumes: nothing
- Produces: new settings in `webui/webui/settings.py`:
  - `USE_X_FORWARDED_HOST = True` (always)
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (always)
  - `SECURE_SSL_REDIRECT` — bool from `SECURE_SSL_REDIRECT` env var (default `False`)
  - `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` — bool from `HTTPS_ENABLED` env var (default `False`)
  - `CSRF_TRUSTED_ORIGINS` — list of strings from `CSRF_TRUSTED_ORIGINS` env var (default `[]`)
  - `SECURE_HSTS_SECONDS` — int from `SECURE_HSTS_SECONDS` env var (default `0`)
  - `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` — `True` when `SECURE_HSTS_SECONDS > 0`
  - `SECURE_REFERRER_POLICY = "same-origin"` (always)
  - `LOGGING` — dict with console handler, django at WARNING, django.request at ERROR

- [ ] **Step 1: Write failing tests**

Create `webui/tests/test_settings.py`:

```python
"""Tests for env-var-driven security settings in webui/settings.py.

These tests reload webui.settings directly (bypassing Django's settings proxy
and settings_test.py) to verify that env vars produce the correct module-level
values. dotenv.load_dotenv is patched out so the local .env file doesn't
interfere.
"""
import importlib
import os
import sys
from unittest.mock import patch


def _load(env: dict) -> object:
    """Reload webui.settings with the given env vars patched in."""
    mod_name = "webui.settings"
    sys.modules.pop(mod_name, None)
    base_env = {
        "DJANGO_SECRET_KEY": "a" * 50,
        "DEBUG": "false",
    }
    base_env.update(env)
    with patch.dict(os.environ, base_env, clear=False), patch("dotenv.load_dotenv"):
        return importlib.import_module(mod_name)


def test_proxy_ssl_header_always_set():
    m = _load({})
    assert m.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_use_x_forwarded_host_always_true():
    m = _load({})
    assert m.USE_X_FORWARDED_HOST is True


def test_secure_ssl_redirect_default_false():
    m = _load({})
    assert m.SECURE_SSL_REDIRECT is False


def test_secure_ssl_redirect_can_be_enabled():
    m = _load({"SECURE_SSL_REDIRECT": "true"})
    assert m.SECURE_SSL_REDIRECT is True


def test_https_disabled_by_default():
    m = _load({})
    assert m.SESSION_COOKIE_SECURE is False
    assert m.CSRF_COOKIE_SECURE is False


def test_https_enabled_sets_secure_cookies():
    m = _load({"HTTPS_ENABLED": "true"})
    assert m.SESSION_COOKIE_SECURE is True
    assert m.CSRF_COOKIE_SECURE is True


def test_csrf_trusted_origins_empty_by_default():
    m = _load({})
    assert m.CSRF_TRUSTED_ORIGINS == []


def test_csrf_trusted_origins_parsed_from_env():
    m = _load({"CSRF_TRUSTED_ORIGINS": "https://a.example.com,https://b.example.com"})
    assert m.CSRF_TRUSTED_ORIGINS == ["https://a.example.com", "https://b.example.com"]


def test_hsts_disabled_by_default():
    m = _load({})
    assert m.SECURE_HSTS_SECONDS == 0
    assert m.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
    assert m.SECURE_HSTS_PRELOAD is False


def test_hsts_set_from_env():
    m = _load({"SECURE_HSTS_SECONDS": "31536000"})
    assert m.SECURE_HSTS_SECONDS == 31536000
    assert m.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert m.SECURE_HSTS_PRELOAD is True


def test_referrer_policy_is_same_origin():
    m = _load({})
    assert m.SECURE_REFERRER_POLICY == "same-origin"


def test_logging_has_console_handler():
    m = _load({})
    assert "console" in m.LOGGING["handlers"]
    assert m.LOGGING["handlers"]["console"]["class"] == "logging.StreamHandler"


def test_logging_django_logger_at_warning():
    m = _load({})
    assert m.LOGGING["loggers"]["django"]["level"] == "WARNING"
    assert "console" in m.LOGGING["loggers"]["django"]["handlers"]


def test_logging_request_logger_at_error_no_propagate():
    m = _load({})
    req = m.LOGGING["loggers"]["django.request"]
    assert req["level"] == "ERROR"
    assert req["propagate"] is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd webui && uv run --group dev pytest tests/test_settings.py -v
```

Expected: all 14 tests FAIL with `AttributeError` (settings don't have these attributes yet).

- [ ] **Step 3: Add security settings and logging to `webui/webui/settings.py`**

Append the following block at the end of `webui/webui/settings.py` (after the `POSTBOT_API_SECRET` line):

```python

# --- Production security settings ---
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "false").lower() == "true"

_https = os.environ.get("HTTPS_ENABLED", "false").lower() == "true"
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https

_csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

SECURE_REFERRER_POLICY = "same-origin"

# --- Logging: stdout only ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd webui && uv run --group dev pytest tests/test_settings.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd webui && uv run --group dev pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/webui/settings.py webui/tests/test_settings.py
git commit -m "feat(webui): add security headers, HTTPS toggles, and stdout logging config"
```

---

### Task 3: Health check endpoint

**Files:**
- Modify: `webui/webui/urls.py`
- Modify: `webui/tests/test_views.py`

**Interfaces:**
- Consumes: nothing
- Produces: `GET /health/` → HTTP 200, JSON body `{"status": "ok"}`, no authentication required

- [ ] **Step 1: Add failing tests to `webui/tests/test_views.py`**

Append to the bottom of `webui/tests/test_views.py`:

```python
class HealthCheckTest(TestCase):
    def test_health_returns_200_and_ok(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_health_requires_no_authentication(self):
        unauthenticated = Client()
        resp = unauthenticated.get("/health/")
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd webui && uv run --group dev pytest tests/test_views.py::HealthCheckTest -v
```

Expected: both tests FAIL with 404.

- [ ] **Step 3: Add health view to `webui/webui/urls.py`**

Replace the entire file with:

```python
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView

from broadcast.views.login import LDAPAwareLoginView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", RedirectView.as_view(url="/broadcast/", permanent=False)),
    path("admin/", admin.site.urls),
    path(
        "login/",
        LDAPAwareLoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("broadcast/", include("broadcast.urls")),
    path("admin-dashboard/", include("broadcast.admin_dashboard.urls")),
    path("health/", health),
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd webui && uv run --group dev pytest tests/test_views.py::HealthCheckTest -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd webui && uv run --group dev pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/webui/urls.py webui/tests/test_views.py
git commit -m "feat(webui): add unauthenticated /health/ endpoint"
```