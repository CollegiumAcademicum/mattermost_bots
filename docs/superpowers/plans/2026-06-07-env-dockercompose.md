# Streamlined `.env.example` and `docker-compose.yaml` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `.env.example` template, fix the missing `ALLOWED_HOSTS` passthrough in docker-compose, and add named volumes for SQLite DB and log persistence so first-time deploy is `cp .env.example .env` → fill 4 values → `docker compose up -d`.

**Architecture:** Pure config file changes — no application code touched. Three files change: new `.env.example` at repo root, updated `docker-compose.yaml`, updated `README.md` to reference the new file.

**Tech Stack:** Docker Compose, shell

---

### Task 1: Create `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create the file**

```dotenv
# Copy this file to .env and fill in the four CHANGE_ME values.
# All other settings have working defaults.
#
#   cp .env.example .env

# ── postbot (required) ──────────────────────────────────────────────────────
URL=mattermost.yourdomain.com        # hostname only — no https://
TOKEN=CHANGE_ME                      # bot account access token
TEAM_NAME=CHANGE_ME                  # Mattermost team slug (lowercase)
WEBUI_API_SECRET=CHANGE_ME           # shared secret between postbot and webui (any long random string)

# ── postbot (optional — shown with defaults) ─────────────────────────────────
SESSION_TTL_SECONDS=300
SESSION_CLEANUP_INTERVAL_SECONDS=60
CHANNEL_CACHE_TTL_SECONDS=3600
LOG_LEVEL=INFO                       # file log level (DEBUG|INFO|WARNING|ERROR)
CONSOLE_LOG_LEVEL=WARNING            # stdout log level
LOG_FILE=logs/bot.log
DB_PATH=db/broadcast_log.db
BOT_LOG_CHANNEL_ID=                  # channel ID for broadcast audit posts — empty = disabled

# ── webui (required) ────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=CHANGE_ME          # long random string — keep secret, never commit
ALLOWED_HOSTS=yourdomain.com,localhost

# ── webui (optional LDAP) ───────────────────────────────────────────────────
# Remove the leading # to enable LDAP authentication.
# Leave these commented out to use local Django accounts only.
#
# LDAP_SERVER_URI=ldap://ldap.yourdomain.com
# LDAP_BIND_DN=cn=readonly,dc=example,dc=com
# LDAP_BIND_PASSWORD=CHANGE_ME
# LDAP_USER_SEARCH_BASE=ou=users,dc=example,dc=com
# LDAP_ADMIN_GROUP_DN=cn=bot-admins,ou=groups,dc=example,dc=com
```

- [ ] **Step 2: Verify file is gitignored-exempt**

Run: `git check-ignore -v .env.example`
Expected: no output (the file is NOT gitignored — it should be committed).

Run: `git check-ignore -v .env`
Expected: `.gitignore:... .env` (the actual secrets file IS gitignored).

If `.env.example` is caught by a wildcard `.env*` rule in `.gitignore`, add an exception:
```
!.env.example
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .gitignore   # include .gitignore only if you added the exception
git commit -m "chore: add .env.example with annotated defaults"
```

---

### Task 2: Fix `docker-compose.yaml`

**Files:**
- Modify: `docker-compose.yaml`

Current state for reference:
```yaml
services:
  postbot:
    environment:
      - URL
      - TOKEN
      - TEAM_NAME
      - WEBUI_API_SECRET
      - SESSION_TTL_SECONDS
      - SESSION_CLEANUP_INTERVAL_SECONDS
      - CHANNEL_CACHE_TTL_SECONDS
      - LOG_LEVEL
      - CONSOLE_LOG_LEVEL
      - LOG_FILE
      - BOT_LOG_CHANNEL_ID
    volumes:
      - ./channels.toml:/app/postbot/channels.toml:ro
    ...

  webui:
    environment:
      - DJANGO_SECRET_KEY
      - LDAP_SERVER_URI
      - LDAP_BIND_DN
      - LDAP_BIND_PASSWORD
      - LDAP_USER_SEARCH_BASE
      - LDAP_ADMIN_GROUP_DN
      - POSTBOT_API_URL=http://postbot:8000
      - POSTBOT_API_SECRET=${WEBUI_API_SECRET}
    ...

networks:
  internal:
    driver: bridge
```

- [ ] **Step 1: Add `ALLOWED_HOSTS` to webui environment and add volumes**

The postbot WORKDIR is `/app`. The DB defaults to `broadcast_log.db` (→ `/app/broadcast_log.db`) and logs to `logs/bot.log` (→ `/app/logs/bot.log`). We mount named volumes at `/app/db` and `/app/logs`, and override `DB_PATH` to point into the volume. `DB_PATH` is a valid env var — the config loader (`postbot/config.py`) lowercases all keys before Pydantic validation, so `DB_PATH` → `db_path`.

Replace the entire `docker-compose.yaml` with:

```yaml
services:
  postbot:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - URL
      - TOKEN
      - TEAM_NAME
      - WEBUI_API_SECRET
      - SESSION_TTL_SECONDS
      - SESSION_CLEANUP_INTERVAL_SECONDS
      - CHANNEL_CACHE_TTL_SECONDS
      - LOG_LEVEL
      - CONSOLE_LOG_LEVEL
      - LOG_FILE
      - BOT_LOG_CHANNEL_ID
      - DB_PATH
    volumes:
      - ./channels.toml:/app/postbot/channels.toml:ro
      - postbot_db:/app/db
      - postbot_logs:/app/logs
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

volumes:
  postbot_db:
  postbot_logs:
```

Also add `DB_PATH=db/broadcast_log.db` and `LOG_FILE=logs/bot.log` to the optional postbot section of `.env.example` (Task 1 content) so the defaults match the volume mounts.

- [ ] **Step 2: Verify compose config parses cleanly**

Run: `docker compose config`
Expected: YAML dump with no errors, `postbot_db` and `postbot_logs` volumes appear, `ALLOWED_HOSTS` appears under webui environment.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yaml
git commit -m "fix(compose): add ALLOWED_HOSTS to webui, persist DB and logs via named volumes"
```

---

### Task 3: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace inline template with cp instruction**

Find the block in README.md that starts with:
```
### 1. Create a `.env` file

Copy the template below and fill in every value marked `CHANGE_ME`:

```dotenv
...
```
```

Replace it with:

```markdown
### 1. Create a `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the four values marked `CHANGE_ME`. All other settings have working defaults and inline comments.
```

- [ ] **Step 2: Verify README renders correctly**

Run: `cat README.md | grep -A5 "Create a"`
Expected: shows the `cp .env.example .env` instruction, no old template block.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: replace inline .env template with cp .env.example reference"
```

---

## Self-Review Checklist (executor: run before marking done)

- [ ] `.env.example` covers all 4 required vars marked CHANGE_ME
- [ ] `.env.example` covers all optional postbot and webui vars with defaults
- [ ] LDAP vars are commented out with examples
- [ ] `docker compose config` passes with no errors
- [ ] `ALLOWED_HOSTS` appears in webui environment in compose output
- [ ] `postbot_db` and `postbot_logs` volumes appear in compose output
- [ ] README no longer contains the old inline dotenv template block
