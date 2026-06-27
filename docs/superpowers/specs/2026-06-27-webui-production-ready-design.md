# Webui Production Hardening — Design

**Date:** 2026-06-27
**Status:** Approved

## Overview

Harden the Django/Gunicorn webui server for production deployment. The webui sits behind nginx (TLS status currently unconfirmed). Four targeted changes are made in-place — no new apps, no settings split.

## Section 1: Django Security Settings

Add the following to `webui/webui/settings.py`, using the same env-var pattern already established there.

### Proxy trust

```python
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

Always enabled — the webui always runs behind nginx.

### HTTPS toggles (shared `HTTPS_ENABLED` env var)

```python
_https = os.environ.get("HTTPS_ENABLED", "false").lower() == "true"
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "false").lower() == "true"
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https
```

`HTTPS_ENABLED=true` enables secure cookies for both session and CSRF in one toggle.
`SECURE_SSL_REDIRECT` is a separate toggle to avoid redirect loops when nginx terminates TLS.

### CSRF trusted origins

```python
_csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",")]
```

Required when Django is behind a reverse proxy — Django 4.x checks the `Origin` header against this list for non-safe methods.

### HSTS

```python
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
```

Disabled by default (`0`). Operator sets to `31536000` once TLS is confirmed stable.

### Referrer policy

```python
SECURE_REFERRER_POLICY = "same-origin"
```

Hardcoded — no env override needed.

## Section 2: Gunicorn Configuration

New file: `webui/gunicorn.conf.py`

```python
import os

bind = "0.0.0.0:8080"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
accesslog = "-"   # stdout
errorlog = "-"    # stderr
worker_tmp_dir = "/dev/shm"  # RAM-backed heartbeat files for containers
```

**Dockerfile CMD** updated from inline flags to:

```
uv run gunicorn webui.wsgi:application --config gunicorn.conf.py
```

The `--bind` and `--workers` flags are removed from the CMD since they are now in the config file.

## Section 3: Django Logging

Add a `LOGGING` dict to `settings.py`:

```python
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

- `django` at WARNING: framework errors, security warnings, misconfigurations
- `django.request` at ERROR: 500s only — 4xx are expected noise at this scale
- `propagate: False` on `django.request` prevents double-logging

## Section 4: Health Check Endpoint

Add a `GET /health/` route directly in `webui/webui/urls.py`. No new app, no new file.

```python
from django.http import JsonResponse

def health(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    ...
    path("health/", health),
]
```

- Returns `{"status": "ok"}` with HTTP 200
- No authentication required — nginx/monitoring probes must reach it unauthenticated
- No database query — a failed DB does not cause the health check to fail (webui is mostly stateless; session storage failure would surface through 500s)

## Environment Variables Summary

| Variable | Default | Effect |
|---|---|---|
| `HTTPS_ENABLED` | `false` | Enables `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` |
| `SECURE_SSL_REDIRECT` | `false` | Enables Django HTTP→HTTPS redirect (leave false behind nginx) |
| `CSRF_TRUSTED_ORIGINS` | `""` | Comma-separated trusted origins, e.g. `https://myhost.example.com` |
| `SECURE_HSTS_SECONDS` | `0` | HSTS max-age in seconds; `0` = disabled |
| `GUNICORN_WORKERS` | `2` | Number of Gunicorn worker processes |
| `GUNICORN_TIMEOUT` | `30` | Worker timeout in seconds |
| `GUNICORN_LOG_LEVEL` | `info` | Gunicorn log level |

## Files Changed

- `webui/webui/settings.py` — add security settings + logging config
- `webui/gunicorn.conf.py` — new Gunicorn config file
- `webui/Dockerfile` — update CMD to use `--config gunicorn.conf.py`
- `webui/webui/urls.py` — add `/health/` route