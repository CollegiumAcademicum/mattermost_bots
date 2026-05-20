# GitHub Actions Docker Publish Design

**Date:** 2026-05-20

## Summary

Automate building and pushing the `postbot` container image to DockerHub via GitHub Actions, triggered on pushes to `main` and version tag pushes.

## Trigger

The workflow fires on two events:

- **Push to `main`** → tags image as `philippbtz/mattermost_bots:latest`
- **Push of a tag matching `v*`** (e.g. `v1.0.0`) → tags image as `philippbtz/mattermost_bots:1.0.0`

## Workflow

**File:** `.github/workflows/docker.yml`

Single job `build-and-push` with the following steps:

1. **`actions/checkout@v4`** — check out the full repo (build context is repo root)
2. **`docker/login-action`** — authenticate to DockerHub using repository secrets
3. **`docker/metadata-action`** — compute image tags based on the trigger event (branch → `latest`, semver tag → version string)
4. **`docker/build-push-action`** — build from `Containerfile` at repo root, push with computed tags

## Secrets

Two secrets must be configured in GitHub repo settings (Settings → Secrets and variables → Actions):

| Secret name          | Value                              |
|----------------------|------------------------------------|
| `DOCKERHUB_USERNAME` | `philippbtz`                       |
| `DOCKERHUB_TOKEN`    | DockerHub access token (not password) |

A DockerHub access token can be created at: Account Settings → Security → Access Tokens.

## Image

**Repository:** `philippbtz/mattermost_bots`

| Trigger             | Tag produced                     |
|---------------------|----------------------------------|
| Push to `main`      | `latest`                         |
| Push tag `v1.2.3`   | `1.2.3`                          |

## Out of Scope

- Running tests before building
- Multi-arch builds
- Build layer caching
