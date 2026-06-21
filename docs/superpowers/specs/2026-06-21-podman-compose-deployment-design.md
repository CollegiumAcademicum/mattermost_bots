# Design: Podman-compose deployment with bind-mounted data directories

**Date:** 2026-06-21
**Status:** Approved

## Goal

Deploy postbot and webui as two podman-compose containers where all runtime state, config files, and secrets live in host-accessible bind-mounted directories. Updating the container image never loses history or config; all persistent files are editable directly on the host.

## Host directory layout

```
./
├── .env                        ← postbot config (mounted read-only into postbot)
├── data/
│   ├── postbot/                ← bind-mounted to postbot at /app/data
│   │   ├── channels.toml       ← seeded from postbot/channels.toml on first run
│   │   ├── scheduler.toml      ← seeded from postbot/scheduler.toml on first run
│   │   ├── broadcast_log.db    ← auto-created by bot
│   │   └── logs/               ← postbot log files (via LOG_FILE in .env)
│   ├── webui/                  ← bind-mounted to webui at /app/data
│   │   └── webui.sqlite3       ← Django db, auto-created on first run
│   └── certs/                  ← bind-mounted to webui at /app/certs (read-only)
│       └── ca.pem              ← LDAP CA cert (optional)
```

### Gitignore additions

- `data/postbot/*.db` — SQLite broadcast log
- `data/webui/*.sqlite3` — Django db
- `data/certs/*.pem` — CA certs should not be committed

### Gitkeep files

- `data/postbot/.gitkeep` (replaces existing `data/.gitkeep`)
- `data/webui/.gitkeep`
- `data/certs/.gitkeep`

These ensure the directories exist on a fresh clone, preventing Podman from auto-creating them as root (which would break rootless operation).

---

## docker-compose.yaml

### postbot service

**Before:** `environment:` block passes `URL`, `TOKEN`, `TEAM_NAME`, etc. as env vars plus explicit path overrides (`CHANNELS_TOML_PATH`, `DB_PATH`, `SCHEDULER_TOML_PATH`).

**Problem:** `PostBotConfig.load()` reads config exclusively from the `.env` file via `dotenv_values()` — it never reads `os.environ`. The entire `environment:` block is dead code.

**After:**
- Remove the `environment:` block entirely.
- Add `./.env:/app/.env:ro` to the volumes list — postbot reads its config from this file.
- Replace `./data:/app/data` with `./data/postbot:/app/data`.
- Replace named volume `postbot_logs:/app/logs` with no separate logs mount — logs go to `/app/data/logs/` via `LOG_FILE` in `.env` (see `.env.example` section below).

### webui service

**Changes:**
- Replace named volume `webui_data:/app/data` with `./data/webui:/app/data`.
- Add `./data/certs:/app/certs:ro`.
- Add `LDAP_CA_CERT_PATH=/app/certs/ca.pem` to the `environment:` block.

The `environment:` passthrough block for webui is correct and stays — webui reads from `os.environ` after a best-effort `load_dotenv()`.

### Top-level `volumes:` block

Remove `postbot_logs` and `webui_data` — both replaced by bind mounts. If no other named volumes remain, remove the block entirely.

---

## .env.example additions

The following container-specific path overrides must be present in `.env` for postbot to find its data files. Add them to `.env.example` in the postbot section:

```ini
# Container data paths — required when running via podman-compose
CHANNELS_TOML_PATH=/app/data/channels.toml
DB_PATH=/app/data/broadcast_log.db
SCHEDULER_TOML_PATH=/app/data/scheduler.toml
LOG_FILE=/app/data/logs/bot.log
```

For local development (running outside a container), these values are not needed — the defaults in `PostBotConfig` point to the correct local paths.

---

## .dockerignore

Add `.env` so the secrets file is never baked into the image layer. It is only ever mounted at runtime.

```
.env
```

---

## webui/settings.py

Rename the Django database file from `db.sqlite3` to `webui.sqlite3` (line 69):

```python
# Before
"NAME": BASE_DIR / "data" / "db.sqlite3",

# After
"NAME": BASE_DIR / "data" / "webui.sqlite3",
```

---

## Self-seeding (no change required)

The existing `_seed_data_files()` mechanism in `bot.py` already seeds `channels.toml` and `scheduler.toml` from the bundled templates if they don't exist at the configured paths. This works unchanged with the new mount target `./data/postbot`.

---

## First-run checklist

On a clean clone, `podman-compose up` should:

1. Find `data/postbot/`, `data/webui/`, `data/certs/` already present (via `.gitkeep`).
2. postbot seeds `data/postbot/channels.toml` and `data/postbot/scheduler.toml` from bundled templates.
3. Django creates `data/webui/webui.sqlite3` on first request.
4. `data/postbot/broadcast_log.db` is created on the first broadcast.
5. `data/postbot/logs/bot.log` is created when postbot starts logging.
6. All files are readable and editable from the host.

---

## Out of scope

- Changes to `PostBotConfig.load()` to read from `os.environ` — this would be a larger refactor and is a separate concern.
- Local development workflow — unchanged; `uv run postbot/main.py` continues to use local paths.
- Reverse proxy / TLS termination in front of webui.
