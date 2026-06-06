# Web UI Design — Mattermost Broadcast Interface

**Date:** 2026-06-06

## Overview

A Django web interface (`webui`) that allows authenticated users to compose and broadcast messages to Mattermost channels. Users select target channels (by group or individually), confirm before sending, and the webui delegates the actual Mattermost API calls to `postbot` via a secured internal HTTP API.

---

## 1. Architecture

```
┌──────────────────────────────┐  HTTP (internal) ┌─────────────────────────────┐
│  webui (Django)              │ ──────────────▶ │  postbot                    │
│  - LDAP login                │  POST /api/      │  - WebSocket loop (MM)      │
│  - channel picker            │  broadcast       │  - FastAPI HTTP server      │
│  - confirmation step         │  (secret header) │  - sends to Mattermost      │
│  - admin dashboard (later)   │                  │                             │
└──────────────────────────────┘                  └─────────────────────────────┘
         │ docker-compose service                           │ docker-compose service
         │ (gunicorn)                                       │ (uvicorn + asyncio WS)
```

- `webui` and `postbot` run as **separate containers** so either can be updated independently
- Both containers mount `channels.json` read-only from the host
- postbot's FastAPI port is only reachable within the internal Docker network — never exposed publicly
- `webui` is exposed on port `8080` and sits behind a reverse proxy (e.g. Caddy) in production

**uv workspace membership:** `webui/` is added as a new workspace member alongside `postbot/` and `mmbot_framework/`.

**Shared config via env vars:**

| Service | Var | Purpose |
|---------|-----|---------|
| postbot | `WEBUI_API_SECRET` | validates incoming requests from webui |
| webui | `POSTBOT_API_URL` | e.g. `http://postbot:8000` |
| webui | `POSTBOT_API_SECRET` | sent as `Authorization: Bearer <secret>` |

---

## 2. Authentication & Authorization

**Backends** (Django tries in order):
1. `broadcast.auth.CustomLDAPBackend` — primary; same pattern as CAWash (`django-auth-ldap`)
2. `django.contrib.auth.backends.ModelBackend` — fallback; works even when LDAP is reachable, as long as the username is not an LDAP username

```python
AUTHENTICATION_BACKENDS = [
    "broadcast.auth.CustomLDAPBackend",
    "django.contrib.auth.backends.ModelBackend",
]
```

**LDAP group mapping:** The LDAP group (e.g. `cn=mm_admins,...`) is mapped to a Django group called `BotAdmins` on every login via `CustomLDAPBackend.authenticate()`.

**Access control:**
- All authenticated users (LDAP or local) can access the broadcast interface
- Only members of `BotAdmins` can access the admin dashboard (enforced via decorator)

**Local accounts:** Created by admins via Django's `/admin/` panel. No self-registration. Can be assigned to `BotAdmins` manually if needed.

**Required env vars in `webui`:**
```
LDAP_SERVER_URI
LDAP_BIND_DN
LDAP_BIND_PASSWORD
LDAP_USER_SEARCH_BASE
LDAP_ADMIN_GROUP_DN
DJANGO_SECRET_KEY
```

---

## 3. Broadcast Flow

### Step 1 — Compose (`/broadcast/`)
- Textarea for message body
- Channel picker with two sections:
  - **Groups** — checkboxes for each named group from `channels.json`
  - **Individual channels** — collapsible section, checkboxes per channel
- Channels displayed as: `Display Name` (if display name differs from channel name, show channel name in parentheses)
- At least one selection required to proceed
- "Preview & Confirm" → POST to confirmation view; selections stored in session

### Step 2 — Confirm (`/broadcast/confirm/`)
- Shows full message text
- Shows resolved list of target channels (groups expanded to member channel names)
- "Send" button → calls `POST /api/broadcast` on postbot
- "Go back" → returns to compose with selections preserved

### Step 3 — Result (`/broadcast/result/`)
- Success: flash message "Sent to X channels"
- Partial failure: warning flash "Sent to X channels, failed for Y" with error detail
- Full failure (postbot unreachable): error flash, no silent failures

---

## 4. postbot HTTP API

A new `api/` module added to `postbot`. FastAPI app runs in the same `asyncio` event loop as the WebSocket loop via `uvicorn`.

### Endpoints

```
GET /api/channels
```
Returns all channels from `channels.json` with resolved Mattermost display names and channel names. Channel names are fetched from the Mattermost API at startup and cached in memory with a short TTL.

Response shape:
```json
{
  "groups": {
    "ALLE Cluster Briefkästen": [
      {"id": "wjkw...", "display_name": "Briefkasten EG Links", "channel_name": "briefkasten-eg-links"},
      ...
    ]
  },
  "private_groups": {
    "all-dev": [...]
  },
  "individual_channels": [
    {"id": "...", "display_name": "...", "channel_name": "..."}
  ]
}
```

```
POST /api/broadcast
```
Body:
```json
{"message": "...", "channel_ids": ["id1", "id2"]}
```
Response:
```json
{"sent": 5, "failed": 0, "errors": []}
```

### Security
- Both endpoints require `Authorization: Bearer <secret>` header
- Secret loaded from `WEBUI_API_SECRET` env var
- Missing or wrong secret → `401 Unauthorized`
- FastAPI listens only on the internal Docker network interface

### New files in `postbot/`
```
postbot/api/
├── __init__.py
├── app.py              # FastAPI app, mounts routes
├── auth.py             # Bearer token dependency
├── channel_cache.py    # startup cache of MM channel names (with TTL)
└── routes/
    ├── broadcast.py    # POST /api/broadcast
    └── channels.py     # GET /api/channels
```

---

## 5. Project Structure

```
mattermost_bots/
├── pyproject.toml              # workspace root — add webui as member
├── docker-compose.yaml         # orchestrates webui + postbot
├── channels.json               # mounted read-only into both containers
├── postbot/
│   ├── api/                    # new FastAPI module (see Section 4)
│   └── main.py                 # start uvicorn alongside asyncio WS loop
└── webui/
    ├── pyproject.toml
    ├── manage.py
    ├── webui/
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    └── broadcast/              # Django app
        ├── auth.py             # CustomLDAPBackend
        ├── views/
        │   ├── compose.py
        │   ├── confirm.py
        │   └── result.py
        ├── services/
        │   ├── postbot_client.py   # HTTP calls to postbot API
        │   └── channel_service.py  # fetches + caches /api/channels
        ├── templates/
        │   ├── base.html
        │   ├── login.html
        │   ├── compose.html
        │   ├── confirm.html
        │   └── result.html
        ├── urls.py
        └── admin_dashboard/    # placeholder app for later
```

---

## 6. Deployment

```yaml
services:
  postbot:
    build: ./postbot
    environment:
      - MATTERMOST_URL
      - BOT_TOKEN
      - TEAM_NAME
      - WEBUI_API_SECRET
    volumes:
      - ./channels.json:/app/channels.json:ro
    networks:
      - internal

  webui:
    build: ./webui
    environment:
      - LDAP_SERVER_URI
      - LDAP_BIND_DN
      - LDAP_BIND_PASSWORD
      - LDAP_USER_SEARCH_BASE
      - LDAP_ADMIN_GROUP_DN
      - POSTBOT_API_URL=http://postbot:8000
      - POSTBOT_API_SECRET
      - DJANGO_SECRET_KEY
    volumes:
      - ./channels.json:/app/channels.json:ro
    ports:
      - "8080:8080"
    networks:
      - internal
    depends_on:
      - postbot

networks:
  internal:
    driver: bridge
```

- postbot's port `8000` is **not** exposed to the host
- `webui` on port `8080` sits behind a reverse proxy in production (same pattern as CAWash with Caddy)
- Secrets passed via env vars only, never baked into images

---

## 7. Error Handling & Testing

**Error handling:**
- postbot API unreachable → webui shows error flash, logs exception; no silent failures
- Partial broadcast failure → postbot returns `{"sent": X, "failed": Y, "errors": [...]}`, webui shows warning with count
- LDAP unavailable at login → Django falls through to `ModelBackend`; if no local account exists, shows generic "login failed"
- Invalid/expired session → redirect to login

**Testing:**
- `postbot` API: pytest tests per endpoint with mocked MM driver; auth middleware tested with missing/wrong/correct tokens
- `webui`: Django test client tests for compose → confirm → result flow; postbot client mocked via `unittest.mock`; LDAP auth tested with a mock backend (same pattern as CAWash)

---

## 8. Admin Dashboard (Future)

The `admin_dashboard/` Django app is scaffolded as a placeholder. Access restricted to `BotAdmins` group. Planned settings include:
- Managing `channels.json` groupings via UI
- Viewing broadcast history (from postbot's SQLite DB)
- Managing local user accounts

No implementation in this phase.

---

## Notes

**`whitelist` in `channels.json`:** The existing `whitelist` field contains Mattermost user IDs that are permitted to trigger broadcasts via the chat bot. This is irrelevant to the web UI — access control is handled entirely by Django session auth (LDAP or local account). The postbot API does not re-check the whitelist for requests from `webui`.
