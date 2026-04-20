# Postbot Task Scheduler — Design Spec

**Date:** 2026-04-20
**Status:** Approved

## Overview

Add a general-purpose scheduled task system to the existing `postbot`. Tasks are Python plugin files that can be triggered on a cron schedule or manually via a DM command. This replaces the old standalone cron scripts (`bot.py`, `bot_monthly.py`, etc.) with a unified, maintainable system living inside the already-running bot process.

## Goals

- Tasks can be triggered manually via DM (`!run <task_name>`)
- Tasks run automatically on a cron schedule defined in a config file
- Adding a new task requires only writing one Python file — no bot registration code
- Schedule changes go through `scheduler.toml`, not Python code
- A failing task is logged but does not crash the bot

## Non-goals

- Editing schedules via DM command
- Cancelling a running task mid-execution
- Task dependencies or ordering

---

## Architecture

### Task plugin interface

Each task is a `.py` file in `postbot/tasks/`. The filename (without `.py`) is the task's canonical name. A task file must define:

```python
# tasks/weekly_maintenance.py

DESCRIPTION = "Posts the weekly maintenance plan to WG Briefkästen"  # optional

async def run(driver) -> None:
    """driver is the already-authenticated mattermostdriver.Driver."""
    ...
```

- `driver` is passed in by the runner — tasks do not authenticate themselves
- `DESCRIPTION` is optional; shown in `!tasks` output if present, otherwise `"—"`
- Tasks may import any library they need (pandas, pyncclient, etc.)
- Tasks are expected to be short-lived (seconds to a few minutes)

### Schedule configuration (`scheduler.toml`)

```toml
[tasks]
weekly_maintenance  = "0 7 * * 1"   # Every Monday at 07:00
monthly_maintenance = "0 8 1 * *"   # 1st of every month at 08:00
engagement_check    = "0 6 5 8 *"   # 5th August at 06:00
```

- Standard 5-field cron syntax, parsed by `croniter`
- Tasks not listed here are still runnable via `!run` (manual-only)
- File is read at bot startup; schedule changes require a bot restart
- Schedule changes are made by editing the file directly (git-tracked, natural audit trail)

### New files

| File | Purpose |
|---|---|
| `postbot/tasks/` | Directory for task plugin files (one `.py` per task) |
| `postbot/scheduler.toml` | Cron schedule config |
| `postbot/task_runner.py` | Task discovery, registry, scheduler loop logic |

### Changes to existing files

**`config.py` (`PostBotConfig`)** — two new optional fields:
```python
tasks_dir: Path = Path("tasks")
scheduler_toml_path: Path = Path("scheduler.toml")
```

**`bot.py` (`PostBot`):**
- `on_start()`: call `task_runner.load_tasks(config.tasks_dir)` and `task_runner.load_schedule(config.scheduler_toml_path)`; register `!tasks` and `!run` commands
- `_async_main()`: start the scheduler loop as a third `asyncio.Task` alongside the existing session-cleanup and cache-refresh loops
- Add `_handle_tasks()` and `_handle_run()` command handlers

**`pyproject.toml`:** add `croniter` dependency

---

## `task_runner.py` responsibilities

- **`load_tasks(tasks_dir)`** — walks `tasks/`, imports each `.py` file via `importlib`, extracts `run` and optional `DESCRIPTION`. Returns a `dict[str, TaskEntry]`.
- **`load_schedule(path)`** — reads `scheduler.toml`, returns `dict[str, str]` (task name → cron expression). Missing file is treated as empty (no scheduled tasks).
- **`TaskRegistry`** — holds the loaded tasks and schedules; tracks `last_run: dict[str, datetime]` per task.
- **`scheduler_loop(registry, driver)`** — async loop, wakes every 60 seconds, checks each scheduled task using `croniter` to determine if it is due (i.e. its next scheduled time falls within the last 60 seconds), fires due tasks.

---

## DM commands

### `!tasks`

Lists all discovered tasks.

```
| Task | Description | Schedule | Last run |
| :--- | :--- | :--- | :--- |
| weekly_maintenance | Posts the weekly... | 0 7 * * 1 (Mon 07:00) | 2026-04-14 07:00 UTC |
| engagement_check | — | — (manual only) | never |
```

### `!run <task_name>`

Immediately executes the named task.

1. Bot replies: `⏳ Running weekly_maintenance...`
2. Task runs in a background `asyncio.Task`
3. On completion: `✅ weekly_maintenance completed.`
4. On exception: `❌ weekly_maintenance failed: <error message>`

If the task name is not found: `❌ Unknown task: <name>. Use !tasks to see available tasks.`

---

## Error handling

- Task discovery errors (bad import, missing `run`) are logged at startup and the task is skipped — the bot still starts
- Runtime task exceptions are caught, logged, and reported back to the DM channel that triggered the run (for `!run`) or to the bot log channel (for scheduled runs, if `bot_log_channel_id` is configured)
- A task timing out or running long does not block the scheduler loop (each task runs as its own `asyncio.Task`)

---

## Dependency

Add to `postbot/pyproject.toml`:
```toml
"croniter>=2.0"
```
