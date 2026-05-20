# Docker Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `postbot/Containerfile` with a working one at the repo root that correctly resolves the `mmbot_framework` local dependency via the uv workspace.

**Architecture:** Build context is the repo root so both `postbot/` and `mmbot_framework/` are available. `uv sync` at the workspace root resolves the local path dependency naturally. A `.dockerignore` keeps the image lean.

**Tech Stack:** Python 3.14-slim, uv, Docker/Podman

---

### Task 1: Create `.dockerignore` at repo root

**Files:**
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `/mattermost_bots/.dockerignore` with this content:

```
.venv/
**/__pycache__/
**/*.db
**/logs/
.git/
```

- [ ] **Step 2: Verify the file**

Run:
```bash
cat .dockerignore
```
Expected output:
```
.venv/
**/__pycache__/
**/*.db
**/logs/
.git/
```

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for container builds"
```

---

### Task 2: Replace Containerfile

**Files:**
- Delete: `postbot/Containerfile`
- Create: `Containerfile` (repo root)

- [ ] **Step 1: Delete the old Containerfile**

```bash
git rm postbot/Containerfile
```

- [ ] **Step 2: Create new Containerfile at repo root**

Create `/mattermost_bots/Containerfile` with this content:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY . .

RUN uv sync

CMD ["uv", "run", "python", "postbot/main.py"]
```

- [ ] **Step 3: Verify syntax is valid**

Run (requires Docker or Podman installed):
```bash
docker build --no-cache -t postbot . 2>&1 | tail -5
```
Expected: build completes with a line like `Successfully built <hash>` or `COMMIT postbot`.

If neither Docker nor Podman is available, skip to Step 4.

- [ ] **Step 4: Commit**

```bash
git add Containerfile
git commit -m "feat: move Containerfile to repo root, fix Python version and mmbot_framework dep"
```
