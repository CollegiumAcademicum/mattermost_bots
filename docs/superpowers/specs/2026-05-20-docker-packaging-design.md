# Docker Packaging Design for postbot

**Date:** 2026-05-20

## Summary

Package `postbot` into a container image that correctly handles its local path dependency on `mmbot_framework` within the uv workspace.

## Problem

The existing `postbot/Containerfile` has two issues that make it non-functional:

1. **Wrong Python version** — uses `python:3.12.13-slim` but `postbot/pyproject.toml` requires `>=3.14`
2. **Missing local dependency** — `postbot` depends on `mmbot_framework` via a local path (`../mmbot_framework`). The old Containerfile only copies `postbot/` files, so `uv sync` fails to resolve that dependency.

## Design

### Build Context

The Docker build context is the **repo root** (`/mattermost_bots/`). This is the natural fit for a uv workspace where both `postbot/` and `mmbot_framework/` must be present during dependency resolution.

### Containerfile Location

Move from `postbot/Containerfile` → repo root `Containerfile`. This aligns the file with the required build context.

### Build Steps

```
python:3.14-slim
  └── pip install uv
  └── WORKDIR /app
  └── COPY . .          (repo root: postbot/ + mmbot_framework/ + pyproject.toml)
  └── RUN uv sync       (resolves mmbot_framework local path dep via workspace)
  └── CMD uv run python postbot/main.py
```

### .dockerignore

Exclude at repo root to keep image lean and avoid copying sensitive/unnecessary files:

```
.venv/
**/__pycache__/
**/*.db
**/logs/
.git/
```

### Usage

```bash
# Build
docker build -t postbot .

# Run (pass env file with MATTERMOST_URL, BOT_TOKEN, TEAM_NAME, etc.)
docker run --env-file postbot/.env postbot
```

## Changes

- **Delete** `postbot/Containerfile`
- **Create** `Containerfile` at repo root
- **Create** `.dockerignore` at repo root

## Out of Scope

- Multi-stage builds (uv and build tools remain in the runtime image; acceptable for this use case)
- CI/CD pipeline integration
- Image registry publishing
