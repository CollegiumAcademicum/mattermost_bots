---
name: Postbot data directory
description: Consolidate postbot state files into a host-accessible ./data/ bind mount with self-seeding on first run
type: project
---

# Postbot data directory

## Goal

Move all postbot runtime state files into a single `./data/` directory that is bind-mounted into the container. Files are seeded automatically from bundled templates on first run so the user never has to create them manually.

## Files in scope

| File | Current location | New path (host) | New path (container) |
|------|-----------------|-----------------|----------------------|
| `channels.toml` | `postbot/channels.toml` (also mount template) | `data/channels.toml` | `/app/data/channels.toml` |
| `scheduler.toml` | `postbot/scheduler.toml` (also mount template) | `data/scheduler.toml` | `/app/data/scheduler.toml` |
| `broadcast_log.db` | named volume `postbot_db` | `data/broadcast_log.db` | `/app/data/broadcast_log.db` |

`channels.json` is a legacy file that is no longer read by the bot. It is left in place and not migrated.

## Self-seeding mechanism

At bot startup (in `bot.py`, before `_load_channels_toml()` is called), a new `_seed_data_files()` method runs:

1. Ensure the parent directory of each config path exists (`Path.mkdir(parents=True, exist_ok=True)`).
2. For `channels_toml_path`: if the file does not exist, copy from the bundled template at `Path(__file__).parent / "channels.toml"`.
3. For `scheduler_toml_path`: if the file does not exist, copy from the bundled template at `Path(__file__).parent / "scheduler.toml"`.
4. The DB is already auto-created by `initialize_database()` — no change needed there.

The bundled templates (`postbot/channels.toml`, `postbot/scheduler.toml`) remain in the repo as both the canonical defaults and the source for in-image seeding.

## docker-compose.yaml changes

- Replace `./postbot/channels.toml:/app/channels.toml:ro` with `./data:/app/data` (read-write bind mount).
- Remove named volume `postbot_db` from both the `postbot` service and the top-level `volumes` block.
- Add env vars to `postbot` service:
  - `CHANNELS_TOML_PATH=/app/data/channels.toml`
  - `DB_PATH=/app/data/broadcast_log.db`
  - `SCHEDULER_TOML_PATH=/app/data/scheduler.toml`

## Repo scaffolding

- Add `data/.gitkeep` so `./data/` exists on clone (prevents Docker creating the directory as root on Linux).
- Add `data/*.db` to root `.gitignore` to keep the SQLite database out of version control.
- `postbot/channels.toml` and `postbot/scheduler.toml` stay in place — they serve as bundled templates inside the Docker image.

## What does NOT change

- `postbot/config.py` — default paths are left as-is; the docker-compose env vars override them for containerised deployment.
- Local development workflow — running `uv run main.py` outside Docker continues to use the local paths unchanged.

## Testing

After the change, `docker compose up` on a clean checkout should:
1. Start with an empty `./data/` directory.
2. Seed `data/channels.toml` and `data/scheduler.toml` from the bundled templates.
3. Create `data/broadcast_log.db` on first broadcast.
4. All three files visible and editable from the host.
