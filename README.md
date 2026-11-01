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

- Keycloak (OIDC) login; local Django accounts remain available through `/admin/`
- Members of a configurable group are granted the `BotAdmin` permission, re-checked
  every 15 minutes
- Three-step broadcast flow: compose → confirm → result
- Communicates with postbot over an internal network using a shared API secret
- Served by Gunicorn on port 8080

---

## Deployment (Docker Compose)

### Prerequisites

- Docker, or Podman with podman-compose
- A running Mattermost instance with a bot account and its access token
- A Keycloak client for the web UI (see [Keycloak setup](#keycloak-setup))

### 1. Create a `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the four values marked `CHANGE_ME`. All other settings have working defaults and inline comments.

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

# Create a local superuser (emergency access through /admin/)
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

### Keycloak setup

In the `collegium` realm, create an OpenID Connect client `postbot`:

1. Client authentication **on**, Standard flow only.
2. Valid redirect URIs `https://<webui-host>/oidc/callback/`, Valid post logout
   redirect URIs `https://<webui-host>/logged-out/`, Web origins `https://<webui-host>`.
3. **Credentials** tab: copy the secret into `OIDC_RP_CLIENT_SECRET`.
4. **Client scopes → postbot-dedicated → Add mapper → By configuration → Group Membership**:
   Token Claim Name `groups`, Full group path off, Add to userinfo on.

Every user who can log in to this client can send broadcasts. To restrict that, require
a role with a Keycloak authentication flow on the client.

### 5. Grant broadcast permission to users

Members of `LDAP_ADMIN_GROUP_DN` are automatically given the `BotAdmin`
group permission on login. The group is matched by its `cn` against the Keycloak
`groups` claim.

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

Both postbot and webui read from the same `.env` file in the repo root.

**First-time setup**

```bash
cp .env.example .env   # fill in URL, TOKEN, TEAM_NAME — secrets are already wired up

# Create the webui database and a local admin account (run once)
cd webui
mkdir -p data
DJANGO_SETTINGS_MODULE=webui.settings DEBUG=true uv run python manage.py migrate
DJANGO_SETTINGS_MODULE=webui.settings DEBUG=true uv run python manage.py createsuperuser
cd ..
```

**Terminal 1 — postbot**

```bash
uv run postbot/main.py
```

> **Standalone mode** (without webui): `cd postbot && uv run main.py` instead.
> postbot resolves `.env` relative to the working directory, so the launch
> path determines which config file is used.

**Terminal 2 — webui**

```bash
cd webui && DJANGO_SETTINGS_MODULE=webui.settings DEBUG=true uv run python manage.py runserver 8080
```

Open http://localhost:8080/admin/login/ and log in with the superuser you created, then go to http://localhost:8080/broadcast/.

`DEBUG=true` is passed explicitly (not in `.env`) so production deployments cannot accidentally enable debug mode. No Keycloak is required for this: `/admin/` uses Django's local `ModelBackend`.

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
| `KEYCLOAK_REALM_URL` | no | `https://id.ca-hd.de/realms/collegium` | Keycloak realm URL |
| `OIDC_RP_CLIENT_ID` | no | `postbot` | Keycloak client ID |
| `OIDC_RP_CLIENT_SECRET` | yes | — | Keycloak client secret |
| `LDAP_ADMIN_GROUP_DN` | no | — | Group DN whose members get `BotAdmin` (matched by `cn`) |
