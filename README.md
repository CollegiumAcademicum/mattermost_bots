# mattermost-bots

A monorepo containing a Mattermost broadcast bot and supporting infrastructure.

## Repository layout

```
mattermost_bots/
  mmbot_framework/   # Shared Python library for building Mattermost bots
  postbot/           # Broadcast relay bot (uses mmbot_framework)
  webui/             # Django web interface for triggering broadcasts
  Dockerfile         # Builds the postbot container
  docker-compose.yaml
  publish.sh         # Helper to build and push images to a registry
```

---

## Components

### mmbot_framework

A reusable Python library that handles the WebSocket lifecycle, session management,
middleware chains, and command routing. Bot projects depend on it and add only
their own business logic.

Full documentation: [mmbot_framework/README.md](mmbot_framework/README.md)

### postbot

A broadcast relay bot ("mailman bot") that accepts messages and relays them to
configured Mattermost channel groups. Users interact via direct message or through
the web UI.

- Two-step broadcast wizard (target selection → confirmation → send)
- Channel group management (`channels.toml`)
- Cron-scheduled task plugins (`scheduler.toml`)
- SQLite broadcast audit log
- **HTTP API** (`/api/channels`, `/api/broadcast`) used by the web UI

Full documentation: [postbot/README.md](postbot/README.md)

### webui

A Django web application that lets authorized users trigger broadcasts through a
browser instead of via direct message to the bot.

- LDAP authentication (falls back to local Django accounts when `python-ldap` is
  unavailable)
- Members of a configurable LDAP group are granted the `BotAdmin` permission
- Three-step broadcast flow: compose → confirm → result
- Communicates with postbot over an internal network using a shared API secret
- Served by Gunicorn on port 8080

---

## Deployment (Docker Compose)

### Prerequisites

- Docker (or Podman with `docker-compose` compatibility)
- A running Mattermost instance with a bot account and its access token
- An LDAP server (optional; local Django accounts work without it)

### 1. Create a `.env` file

Copy the template below and fill in every value marked `CHANGE_ME`:

```dotenv
# ── postbot ────────────────────────────────────────────────────────────────
URL=mattermost.yourdomain.com             # hostname only, no https://
TOKEN=CHANGE_ME                            # bot account access token
TEAM_NAME=your-team-slug                   # Mattermost team slug

# Shared secret between postbot and webui (any long random string)
WEBUI_API_SECRET=CHANGE_ME

# Optional postbot overrides (shown with defaults)
SESSION_TTL_SECONDS=300
CHANNEL_CACHE_TTL_SECONDS=3600
LOG_LEVEL=INFO
CONSOLE_LOG_LEVEL=WARNING
BOT_LOG_CHANNEL_ID=                        # leave empty to disable audit posts

# ── webui ──────────────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=CHANGE_ME                # long random string, keep secret
ALLOWED_HOSTS=yourdomain.com,localhost     # comma-separated hostnames

# LDAP (remove or leave empty to use local Django accounts only)
LDAP_SERVER_URI=ldap://ldap.yourdomain.com
LDAP_BIND_DN=cn=readonly,dc=example,dc=com
LDAP_BIND_PASSWORD=CHANGE_ME
LDAP_USER_SEARCH_BASE=ou=users,dc=example,dc=com
LDAP_ADMIN_GROUP_DN=cn=bot-admins,ou=groups,dc=example,dc=com
```

> **Security note:** Never commit `.env` to version control. It is listed in
> `.dockerignore` and `.gitignore`.

### 2. Prepare `channels.toml`

The postbot container mounts `channels.toml` from the host at runtime so you
can edit channel groups without rebuilding the image.

Create `channels.toml` in the repo root (next to `docker-compose.yaml`):

```toml
whitelist = []

[groups]
"Everyone" = ["<channel-id-1>", "<channel-id-2>"]

[private_groups]
"Staff" = ["<channel-id-3>"]
```

Use the `!id <channel name>` bot command to look up channel IDs.

### 3. Create the Django database and admin account

Run the one-time setup before the first start:

```bash
# Apply migrations
docker compose run --rm webui uv run python manage.py migrate

# Create a local superuser (skip if using LDAP exclusively)
docker compose run --rm webui uv run python manage.py createsuperuser
```

### 4. Start the stack

```bash
docker compose up -d
```

This starts two containers on an internal bridge network:

| Container | Exposes       | Purpose                           |
|-----------|---------------|-----------------------------------|
| `postbot` | (internal)    | Bot WebSocket + HTTP API on :8000 |
| `webui`   | `0.0.0.0:8080`| Django broadcast UI               |

The webui reaches postbot at `http://postbot:8000` (internal DNS). Only the
webui port is exposed to the host.

### 5. Grant broadcast permission to LDAP users

LDAP members of `LDAP_ADMIN_GROUP_DN` are automatically given the `BotAdmin`
group permission on login.

To grant an existing local Django user access:

```bash
docker compose exec webui uv run python manage.py shell -c "
from django.contrib.auth.models import User, Group
u = User.objects.get(username='alice')
g = Group.objects.get(name='BotAdmins')
u.groups.add(g)
"
```

### 6. Reverse proxy (recommended for production)

Put a reverse proxy (nginx, Caddy, Traefik…) in front of port 8080 to handle
TLS termination and set `ALLOWED_HOSTS` to your public hostname.

### Useful commands

```bash
# View logs
docker compose logs -f postbot
docker compose logs -f webui

# Restart a single service after a config change
docker compose restart postbot

# Stop everything
docker compose down

# Rebuild after a code change
docker compose build
docker compose up -d
```

---

## Building and pushing images manually

`publish.sh` builds both images and pushes them to a registry:

```bash
./publish.sh
```

Edit the registry/tag variables at the top of `publish.sh` to match your setup.

---

## Development

### Running tests

```bash
# mmbot_framework
cd mmbot_framework
uv sync --extra dev
uv run --extra dev pytest -v

# postbot
cd postbot
uv sync
uv run pytest -v

# webui
cd webui
uv sync --extra dev
uv run --extra dev pytest -v
```

### Running locally without Docker

```bash
# postbot
cd postbot
cp .env.example .env   # fill in values
uv run main.py

# webui (in a separate terminal)
cd webui
uv run python manage.py migrate
uv run python manage.py runserver 8080
```

Set `POSTBOT_API_URL=http://localhost:8000` and `POSTBOT_API_SECRET` in the
webui environment to match the running postbot instance.

---

## Environment variable reference

### postbot

| Variable | Required | Default | Description |
|---|---|---|---|
| `URL` | yes | — | Mattermost hostname (no scheme) |
| `TOKEN` | yes | — | Bot account access token |
| `TEAM_NAME` | yes | — | Team slug |
| `WEBUI_API_SECRET` | yes | — | Shared secret for `/api/*` endpoints |
| `SESSION_TTL_SECONDS` | no | `300` | Broadcast wizard session timeout |
| `CHANNEL_CACHE_TTL_SECONDS` | no | `3600` | Channel cache lifetime |
| `LOG_LEVEL` | no | `INFO` | File log level |
| `CONSOLE_LOG_LEVEL` | no | `WARNING` | Console log level |
| `BOT_LOG_CHANNEL_ID` | no | `""` | Mattermost channel for audit posts |
| `CHANNELS_TOML_PATH` | no | `channels.toml` | Path to channel group config |
| `DB_PATH` | no | `broadcast_log.db` | SQLite broadcast log path |
| `TASKS_DIR` | no | `tasks` | Task plugin directory |
| `SCHEDULER_TOML_PATH` | no | `scheduler.toml` | Cron schedule config |

### webui

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | yes (prod) | insecure default | Django secret key |
| `ALLOWED_HOSTS` | no | `localhost,127.0.0.1` | Comma-separated allowed hostnames |
| `DEBUG` | no | `false` | Enable Django debug mode |
| `POSTBOT_API_URL` | no | `http://localhost:8000` | postbot base URL |
| `POSTBOT_API_SECRET` | yes | — | Shared secret (matches `WEBUI_API_SECRET`) |
| `LDAP_SERVER_URI` | no | — | LDAP server URI |
| `LDAP_BIND_DN` | no | — | LDAP bind DN |
| `LDAP_BIND_PASSWORD` | no | — | LDAP bind password |
| `LDAP_USER_SEARCH_BASE` | no | — | LDAP user search base DN |
| `LDAP_ADMIN_GROUP_DN` | no | — | LDAP group DN whose members get `BotAdmin` |
