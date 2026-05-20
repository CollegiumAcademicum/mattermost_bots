# GitHub Actions Docker Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub Actions workflow that builds and pushes the postbot container image to `philippbtz/mattermost_bots` on DockerHub on every push to `main` (tagged `latest`) and every `v*` tag push (tagged with the version).

**Architecture:** A single workflow file using `docker/metadata-action` to compute tags from the Git event, `docker/login-action` to authenticate to DockerHub, and `docker/build-push-action` to build from the repo-root `Containerfile` and push. No jobs run in parallel — one `build-and-push` job handles both trigger types via conditional tag logic built into `metadata-action`.

**Tech Stack:** GitHub Actions, `docker/metadata-action@v5`, `docker/login-action@v3`, `docker/build-push-action@v6`, `actions/checkout@v4`

---

### Task 1: Create the GitHub Actions workflow file

**Files:**
- Create: `.github/workflows/docker.yml`

- [ ] **Step 1: Create the workflows directory and file**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write the workflow file**

Create `.github/workflows/docker.yml` with this exact content:

```yaml
name: Build and push Docker image

on:
  push:
    branches:
      - main
    tags:
      - "v*"

jobs:
  build-and-push:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Log in to DockerHub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Extract metadata for Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: philippbtz/mattermost_bots
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}

      - name: Build and push image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Containerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 3: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docker.yml'))" && echo "YAML valid"
```

Expected output: `YAML valid`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/docker.yml
git commit -m "ci: add GitHub Actions workflow to build and push Docker image to DockerHub"
```

---

### Task 2: Configure DockerHub secrets in GitHub

This task is manual — it cannot be automated without GitHub CLI or the GitHub web UI.

- [ ] **Step 1: Generate a DockerHub access token**

  1. Go to [hub.docker.com](https://hub.docker.com) → your avatar → **Account Settings** → **Security** → **New Access Token**
  2. Name it (e.g. `github-actions-mattermost_bots`), set permissions to **Read, Write, Delete**
  3. Copy the token — it is shown only once

- [ ] **Step 2: Add secrets to the GitHub repository**

  1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
  2. Add `DOCKERHUB_USERNAME` with value `philippbtz`
  3. Add `DOCKERHUB_TOKEN` with the token copied above

- [ ] **Step 3: Verify secrets are listed**

  In GitHub repo → Settings → Secrets and variables → Actions, confirm both `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` appear under Repository secrets.

---

### Task 3: Verify the workflow runs end-to-end

- [ ] **Step 1: Push to `main` and check Actions tab**

```bash
git push origin main
```

Go to your GitHub repo → **Actions** tab. The `Build and push Docker image` workflow should appear and complete successfully.

- [ ] **Step 2: Verify `latest` tag on DockerHub**

  Go to [hub.docker.com/r/philippbtz/mattermost_bots/tags](https://hub.docker.com/r/philippbtz/mattermost_bots/tags) and confirm the `latest` tag is present with a recent push time.

- [ ] **Step 3: Push a version tag and verify**

```bash
git tag v0.1.0
git push origin v0.1.0
```

Go to GitHub Actions tab — a second run should appear. After it completes, verify `0.1.0` appears as a tag on DockerHub.
