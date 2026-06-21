# Design: Streamlined `.env.example` and `docker-compose.yaml`

**Date:** 2026-06-07
**Status:** Approved

## Problem

- No `.env.example` exists — the setup template lives only as a README copy-paste block, making first-time deploy error-prone.
- `docker-compose.yaml` is missing `ALLOWED_HOSTS` in the webui environment passthrough.
- The SQLite broadcast log (`broadcast_log.db`) and log files have no Docker volume — they are lost on container rebuild.

## Goal

`cp .env.example .env` → fill in 4 required values → `docker compose up -d`.

## Changes

### 1. Add `.env.example` (repo root)

New file with four sections:

- **postbot (required):** `URL`, `TOKEN`, `TEAM_NAME`, `WEBUI_API_SECRET` — all marked `CHANGE_ME`
- **postbot (optional):** session/cache/log settings with working defaults
- **webui (required):** `DJANGO_SECRET_KEY` (marked `CHANGE_ME`), `ALLOWED_HOSTS` with example value
- **webui (optional LDAP):** all LDAP vars commented out with example values

The file is committed to version control. The actual `.env` (with real credentials) remains gitignored.

### 2. Fix `docker-compose.yaml`

- Add `- ALLOWED_HOSTS` to the webui `environment` block (it was in `.env` but never passed to the container).
- Add named volumes for postbot data persistence:
  - `postbot_db` → `/app/broadcast_log.db`
  - `postbot_logs` → `/app/logs`
- Declare both volumes in the top-level `volumes:` section.

### 3. Update README

Replace the inline `.env` copy-paste template block with a one-liner:
`cp .env.example .env` — then refer readers to the file for inline comments.

## Out of Scope

- `postbot/.env` (local dev file) — kept as-is, separate concern.
- Any changes to application code or Dockerfiles.
- `channels.toml` setup (already documented in README).
