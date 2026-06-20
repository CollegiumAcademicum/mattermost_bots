# Admin Dashboard — Design Spec

**Date:** 2026-06-21

## Overview

Implement the `admin_dashboard` Django app (currently a placeholder) with two features:

1. **Broadcast history** — paginated list of sent broadcasts, sourced from postbot's SQLite log via API
2. **Channel group management** — full CRUD for all three sections of `channels.toml` (`groups`, `private_groups`, `whitelist`), read and written via postbot API

Access is restricted to members of the `BotAdmins` Django group. webui and postbot remain fully isolated containers — no shared volumes, no direct file or DB access from webui.

---

## 1. Architecture

```
webui (Django)                        postbot (FastAPI)
────────────────────────────────      ────────────────────────────────
AdminDashboard views
  ├── history view    ────────────▶  GET  /api/history?page=N&per_page=20
  └── config views    ────────────▶  GET  /api/config
                      ────────────▶  PUT  /api/config
                      ────────────▶  GET  /api/channels   (existing)
```

- All requests carry `Authorization: Bearer <secret>` (existing auth mechanism, `POSTBOT_API_SECRET`)
- webui never mounts or reads `channels.toml` or `broadcast_log.db` directly
- Both services remain independently deployable containers

---

## 2. New postbot API endpoints

### `GET /api/history`

Query params:
- `page` — integer, default `1`
- `per_page` — integer, default `20`, max `100`

Response:
```json
{
  "total": 142,
  "page": 1,
  "per_page": 20,
  "results": [
    {
      "id": 142,
      "timestamp": "2026-06-20T14:32:00",
      "sender_name": "philipp",
      "message_content": "Hallo zusammen...",
      "target_channels": ["Briefkasten EG Links", "..."],
      "file_ids": []
    }
  ]
}
```

Implementation: queries `broadcasts` table with `ORDER BY id DESC LIMIT ? OFFSET ?`. `total` is a `COUNT(*)` query on the same table.

### `GET /api/config`

Returns `channels.toml` parsed as JSON. Top-level keys: `groups`, `private_groups`, `whitelist`.

- `groups` and `private_groups`: `{ "Group Name": { "channels": ["id1", ...], "aliases": ["alias", ...] } }`
- `whitelist`: `{ "entry_name": { "id": "mm_user_id", "aliases": [] } }`

### `PUT /api/config`

Body: same shape as `GET /api/config` response. Postbot:
1. Validates the payload structure
2. Writes atomically (write to `.tmp` file, then `rename()`)
3. Reloads its in-memory channel cache

Response on success: `{"ok": true}`
Response on validation error: HTTP 422 with error detail.

### New files in `postbot/api/routes/`

```
postbot/api/routes/
├── broadcast.py      (existing)
├── channels.py       (existing)
├── history.py        # GET /api/history
└── config.py         # GET + PUT /api/config
```

`postbot/database.py` gets a new `get_history(page, per_page)` function returning `(total, results)`.

---

## 3. admin_dashboard Django app

### File structure

```
webui/broadcast/admin_dashboard/
├── __init__.py          (exists)
├── apps.py              (exists)
├── views/
│   ├── __init__.py
│   ├── history.py       # paginated broadcast log
│   └── config.py        # channel group CRUD (GET = show, POST = save)
├── services/
│   ├── __init__.py
│   └── admin_client.py  # HTTP calls to /api/history and /api/config
├── templates/admin_dashboard/
│   ├── history.html     # table + pagination controls
│   └── config.html      # tabs: Groups / Private Groups / Whitelist
└── urls.py
```

### URL routes (mounted at `/admin-dashboard/`)

| URL | View | Method |
|-----|------|--------|
| `/admin-dashboard/history/` | `history.py` | GET |
| `/admin-dashboard/config/` | `config.py` | GET, POST |

Added to `webui/urls.py`:
```python
path("admin-dashboard/", include("broadcast.admin_dashboard.urls")),
```

### Access control

A `@require_bot_admin` decorator (defined in `admin_dashboard/views/__init__.py`) checks:
```python
request.user.is_authenticated and request.user.groups.filter(name="BotAdmins").exists()
```
Returns HTTP 403 if not satisfied. Applied to all admin_dashboard views.

### History view

- Reads `page` from query params (default 1)
- Calls `admin_client.get_history(page, per_page=20)`
- Passes `total`, `page`, `per_page`, `results` to `history.html`
- Template renders a table: timestamp | sender | channels | message preview (truncated to 80 chars)
- Pagination controls: previous / next links, current page / total pages

### Config view

**GET:** Calls `admin_client.get_config()` and `admin_client.get_channels()` (existing `/api/channels`) in parallel. Passes config + channel display-name map to `config.html`.

**POST:** Receives form data, reconstructs the config dict, calls `admin_client.put_config(config)`. On success: redirect back to config view with a success flash. On API error: re-render with error message.

**Config editor UX:**
- Three tabs: **Groups** / **Private Groups** / **Whitelist**
- Each group listed with its name and member channels (shown as display names, resolved via `/api/channels` response)
- Add group: name input + channel multi-select (display names, values are channel IDs)
- Delete group: delete button per row, confirmed via standard POST
- Rename group: inline edit field
- Whitelist entries: name + raw Mattermost user ID + aliases (no display-name resolution — user IDs are entered manually)

---

## 4. Testing

### postbot (pytest)

**`tests/test_api_history.py`**
- Paginated results returned in correct order
- Empty DB returns `{"total": 0, "results": []}`
- `page` and `per_page` params respected
- `per_page` capped at 100
- Missing/wrong auth token → 401

**`tests/test_api_config.py`**
- GET returns correctly parsed toml structure
- PUT writes file and reloads cache
- PUT with invalid body → 422
- Missing/wrong auth token → 401

**`postbot/database.py`** gets unit tests for `get_history()` in `tests/test_database.py`.

### webui (Django test client)

**History view:**
- Mocked `admin_client.get_history()` returns fixture; table rows and pagination render correctly
- Non-BotAdmin user → 403
- Unauthenticated user → redirect to login

**Config view:**
- GET: mocked `get_config()` + `get_channels()` render all three tabs
- POST: `put_config()` called with correct payload, redirects on success
- POST: API error displayed without crash
- Non-BotAdmin → 403

**`admin_client.py`:**
- Unit-tested with `unittest.mock` patching `httpx` (same pattern as `postbot_client.py`)
- Covers `get_history`, `get_config`, `put_config` happy paths and HTTP error cases

---

## 5. Out of scope

- Mobile-responsive config editor beyond Bulma defaults
- Audit log of config changes
- Broadcast history filtering/search
- Managing local Django user accounts (deferred to future)
