# Podman-compose Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the project so all runtime state, config, and secrets live in host-accessible bind-mounted directories, enabling podman-compose deployments where image updates never lose data.

**Architecture:** A single `data/` tree with per-service subdirs (`data/postbot/`, `data/webui/`, `data/certs/`) replaces named Docker volumes. The root `.env` is bind-mounted read-only into the postbot container, fixing a silent misconfiguration where the existing `environment:` passthrough block was ignored by postbot's file-based config loader.

**Tech Stack:** podman-compose, Docker Compose v3, Django, Python dotenv

---

## Files modified

| File | Change |
|------|--------|
| `data/.gitkeep` | Delete — replaced by `data/postbot/.gitkeep` |
| `data/postbot/.gitkeep` | Create |
| `data/webui/.gitkeep` | Create |
| `data/certs/.gitkeep` | Create |
| `.gitignore` | Update `data/` ignore patterns |
| `.dockerignore` | Add `.env` |
| `.env.example` | Add container path overrides section |
| `docker-compose.yaml` | Remove dead env block; update all volumes; add `.env` and certs mounts |
| `webui/webui/settings.py:69` | Rename `db.sqlite3` → `webui.sqlite3` |
| `data/broadcast_log.db` | Move → `data/postbot/broadcast_log.db` |
| `data/logs/` | Move → `data/postbot/logs/` |

---

### Task 1: Scaffold new directory structure

**Files:**
- Create: `data/postbot/.gitkeep`
- Create: `data/webui/.gitkeep`
- Create: `data/certs/.gitkeep`
- Delete: `data/.gitkeep`

- [ ] **Step 1: Create the new subdirectories and gitkeep files**

```bash
mkdir -p data/postbot data/webui data/certs
touch data/postbot/.gitkeep data/webui/.gitkeep data/certs/.gitkeep
```

- [ ] **Step 2: Stage the new files and remove the old gitkeep**

```bash
git add data/postbot/.gitkeep data/webui/.gitkeep data/certs/.gitkeep
git rm data/.gitkeep
```

Expected: `git status` shows `new file: data/postbot/.gitkeep`, `new file: data/webui/.gitkeep`, `new file: data/certs/.gitkeep`, `deleted: data/.gitkeep`.

---

### Task 2: Update .gitignore

**Files:**
- Modify: `.gitignore`

The current patterns `data/*.db` and `data/*.toml` matched flat files in `data/`. After the restructure, runtime files live in subdirs — update to match.

- [ ] **Step 1: Replace the postbot runtime data section**

In `.gitignore`, find and replace:

```
# Postbot runtime data
data/*.db
data/*.toml
```

with:

```
# Runtime data (bind-mounted dirs)
data/postbot/*.db
data/postbot/*.toml
data/webui/*.sqlite3
data/certs/
data/*/logs/
```

- [ ] **Step 2: Verify .gitignore works**

```bash
git check-ignore -v data/postbot/broadcast_log.db data/webui/webui.sqlite3 data/postbot/channels.toml
```

Expected: all three lines are printed (each is ignored).

---

### Task 3: Update .dockerignore

**Files:**
- Modify: `.dockerignore`

The `.env` file must never be baked into the image — it is only ever mounted at runtime.

- [ ] **Step 1: Add .env to .dockerignore**

Append to `.dockerignore`:

```
.env
```

The file should now read:

```
.venv/
**/__pycache__/
**/*.db
**/logs/
.git/
.env
```

---

### Task 4: Update .env.example

**Files:**
- Modify: `.env.example`

postbot reads config exclusively from the `.env` file — env vars injected by docker-compose are ignored. The container paths must be in `.env` itself.

- [ ] **Step 1: Update DB_PATH and LOG_FILE defaults and add container paths section**

Find the postbot optional section:

```
LOG_FILE=logs/bot.log
DB_PATH=db/broadcast_log.db
```

Replace with:

```
LOG_FILE=logs/bot.log                    # local dev; see container paths section below
DB_PATH=broadcast_log.db                 # local dev; see container paths section below
```

Then append a new section at the end of the file:

```ini

# ── podman-compose container paths ──────────────────────────────────────────
# Uncomment these when deploying via podman-compose.
# They override the local-dev defaults above.
#
# CHANNELS_TOML_PATH=/app/data/channels.toml
# DB_PATH=/app/data/broadcast_log.db
# SCHEDULER_TOML_PATH=/app/data/scheduler.toml
# LOG_FILE=/app/data/logs/bot.log
#
# LDAP_CA_CERT_PATH=/app/certs/ca.pem   # uncomment if using a custom CA cert
```

---

### Task 5: Rename Django database file

**Files:**
- Modify: `webui/webui/settings.py:69`

- [ ] **Step 1: Rename db.sqlite3 to webui.sqlite3 in settings**

In `webui/webui/settings.py`, find line 69:

```python
        "NAME": BASE_DIR / "data" / "db.sqlite3",
```

Replace with:

```python
        "NAME": BASE_DIR / "data" / "webui.sqlite3",
```

- [ ] **Step 2: Verify no other references to db.sqlite3 remain in webui**

```bash
grep -r "db.sqlite3" webui/
```

Expected: no output (the only reference was settings.py).

---

### Task 6: Update docker-compose.yaml

**Files:**
- Modify: `docker-compose.yaml`

Key changes:
- postbot: remove dead `environment:` block; add `.env` bind mount; update data volume path
- webui: update data volume path; add certs mount; add `LDAP_CA_CERT_PATH` passthrough
- Remove top-level `volumes:` block (no named volumes remain)

- [ ] **Step 1: Rewrite docker-compose.yaml**

Replace the entire file with:

```yaml
services:
  postbot:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./.env:/app/.env:ro
      - ./data/postbot:/app/data
    networks:
      - internal
    restart: unless-stopped

  webui:
    build:
      context: ./webui
      dockerfile: Dockerfile
    environment:
      - DJANGO_SECRET_KEY
      - ALLOWED_HOSTS
      - LDAP_SERVER_URI
      - LDAP_BIND_DN
      - LDAP_BIND_PASSWORD
      - LDAP_USER_SEARCH_BASE
      - LDAP_ADMIN_GROUP_DN
      - LDAP_CA_CERT_PATH
      - POSTBOT_API_URL=http://postbot:8000
      - POSTBOT_API_SECRET=${WEBUI_API_SECRET}
    ports:
      - "8080:8080"
    networks:
      - internal
    depends_on:
      - postbot
    volumes:
      - ./data/webui:/app/data
      - ./data/certs:/app/certs:ro
    restart: unless-stopped

networks:
  internal:
    driver: bridge
```

- [ ] **Step 2: Validate compose syntax**

```bash
podman-compose config
```

Expected: the merged config is printed without errors. If `podman-compose` is not installed, use `docker compose config` — the syntax is identical.

---

### Task 7: Migrate existing data files

**Files:**
- Move: `data/broadcast_log.db` → `data/postbot/broadcast_log.db`
- Move: `data/logs/` → `data/postbot/logs/`

- [ ] **Step 1: Move broadcast_log.db**

```bash
mv data/broadcast_log.db data/postbot/broadcast_log.db
```

- [ ] **Step 2: Move logs directory**

```bash
mv data/logs data/postbot/logs
```

- [ ] **Step 3: Verify data/postbot/ contents**

```bash
ls data/postbot/
```

Expected: `broadcast_log.db  logs  .gitkeep`

Note: `data/tasks/` is unrelated to this spec (task plugin code, not state data) — leave it in place.

---

### Task 8: Commit

- [ ] **Step 1: Stage all changes**

```bash
git add \
  data/postbot/.gitkeep \
  data/webui/.gitkeep \
  data/certs/.gitkeep \
  .gitignore \
  .dockerignore \
  .env.example \
  webui/webui/settings.py \
  docker-compose.yaml
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: podman-compose deployment with bind-mounted data dirs

- Restructure data/ into per-service subdirs (postbot/, webui/, certs/)
- Mount .env read-only into postbot (fixes silent broken env passthrough)
- Replace named volumes postbot_logs and webui_data with bind mounts
- Add certs/ mount for LDAP CA cert
- Rename Django db db.sqlite3 -> webui.sqlite3
- Add container path overrides section to .env.example
- Add .env to .dockerignore"
```
