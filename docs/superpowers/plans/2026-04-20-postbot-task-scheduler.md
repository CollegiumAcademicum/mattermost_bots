# Postbot Task Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general-purpose scheduled-task system to postbot so that cron-driven tasks (like the old maintenance bots) can be written as Python plugin files, triggered manually via DM, and scheduled via `scheduler.toml`.

**Architecture:** A new `task_runner.py` module handles plugin discovery (importlib), schedule loading (TOML + croniter), and a background async loop. `PostBot` gains a `TaskRegistry`, two new DM commands (`!tasks`, `!run`), and overrides `_async_main` to start the scheduler alongside existing background tasks.

**Tech Stack:** Python 3.14, asyncio, croniter>=2.0, toml (already present), pytest (existing), mattermostdriver (already present)

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `postbot/task_runner.py` | TaskEntry, TaskRegistry, load_tasks(), load_schedule(), is_due(), _fire_task(), scheduler_loop() |
| Create | `postbot/tasks/` | Task plugin directory (one `.py` per task) |
| Create | `postbot/tasks/example_task.py` | Reference implementation showing the plugin interface |
| Create | `postbot/scheduler.toml` | Cron schedule config |
| Create | `postbot/tests/test_task_runner.py` | Tests for task_runner.py |
| Modify | `postbot/pyproject.toml` | Add croniter>=2.0 dependency |
| Modify | `postbot/config.py` | Add tasks_dir and scheduler_toml_path fields to PostBotConfig |
| Modify | `postbot/bot.py` | Add task registry, !tasks and !run handlers, on_start loading, _async_main override |

---

## Task 1: Add `croniter` dependency and new config fields

**Files:**
- Modify: `postbot/pyproject.toml`
- Modify: `postbot/config.py`
- Create: `postbot/tests/test_task_runner.py` (config tests only for now)

- [ ] **Step 1: Write the failing config tests**

Create `postbot/tests/test_task_runner.py`:

```python
from pathlib import Path

from config import PostBotConfig


def _base_env() -> dict:
    """Minimal valid PostBotConfig kwargs."""
    return {
        "url": "chat.example.com",
        "token": "testtoken",
        "team_name": "testteam",
    }


def test_tasks_dir_default():
    config = PostBotConfig(**_base_env())
    assert config.tasks_dir == Path("tasks")


def test_tasks_dir_custom():
    config = PostBotConfig(**_base_env(), tasks_dir=Path("/custom/tasks"))
    assert config.tasks_dir == Path("/custom/tasks")


def test_scheduler_toml_path_default():
    config = PostBotConfig(**_base_env())
    assert config.scheduler_toml_path == Path("scheduler.toml")


def test_scheduler_toml_path_custom():
    config = PostBotConfig(**_base_env(), scheduler_toml_path=Path("/custom/scheduler.toml"))
    assert config.scheduler_toml_path == Path("/custom/scheduler.toml")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: `ImportError` or `ValidationError` — `tasks_dir` and `scheduler_toml_path` don't exist yet.

- [ ] **Step 3: Add `croniter` to `pyproject.toml`**

In `postbot/pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "anyio>=4.13.0",
    "croniter>=2.0",
    "dotenv>=0.9.9",
    ...
]
```

- [ ] **Step 4: Add the two new fields to `PostBotConfig`**

In `postbot/config.py`, add after the existing `channel_cache_ttl_seconds` field:

```python
    tasks_dir: Path = Path("tasks")
    scheduler_toml_path: Path = Path("scheduler.toml")
```

- [ ] **Step 5: Install the new dependency**

```bash
cd postbot && uv sync
```

Expected: `croniter` appears in the lock file and installs without errors.

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: 4 tests pass.

- [ ] **Step 7: Commit**

```bash
cd postbot && git add pyproject.toml uv.lock config.py tests/test_task_runner.py
git commit -m "feat: add croniter dep and task scheduler config fields"
```

---

## Task 2: `task_runner.py` — data structures and loaders

**Files:**
- Create: `postbot/task_runner.py`
- Modify: `postbot/tests/test_task_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `postbot/tests/test_task_runner.py`:

```python
import asyncio
from datetime import datetime, timezone

import pytest

import task_runner
from task_runner import TaskEntry, TaskRegistry, load_tasks, load_schedule


# ── TaskEntry ────────────────────────────────────────────────────────────────

def test_task_entry_defaults():
    async def run(driver): pass
    entry = TaskEntry(name="foo", run=run)
    assert entry.description == "—"
    assert entry.last_run is None


# ── TaskRegistry ─────────────────────────────────────────────────────────────

def test_registry_get_known():
    async def run(driver): pass
    entry = TaskEntry(name="foo", run=run)
    registry = TaskRegistry({"foo": entry}, {})
    assert registry.get("foo") is entry


def test_registry_get_unknown():
    registry = TaskRegistry({}, {})
    assert registry.get("missing") is None


def test_registry_all_tasks():
    async def run(driver): pass
    a = TaskEntry(name="a", run=run)
    b = TaskEntry(name="b", run=run)
    registry = TaskRegistry({"a": a, "b": b}, {})
    names = {e.name for e in registry.all_tasks()}
    assert names == {"a", "b"}


# ── load_tasks ────────────────────────────────────────────────────────────────

def test_load_tasks_valid(tmp_path):
    (tmp_path / "my_task.py").write_text(
        'DESCRIPTION = "A test task"\n\nasync def run(driver):\n    pass\n'
    )
    tasks = load_tasks(tmp_path)
    assert "my_task" in tasks
    assert tasks["my_task"].description == "A test task"
    assert callable(tasks["my_task"].run)


def test_load_tasks_no_description(tmp_path):
    (tmp_path / "bare.py").write_text("async def run(driver):\n    pass\n")
    tasks = load_tasks(tmp_path)
    assert "bare" in tasks
    assert tasks["bare"].description == "—"


def test_load_tasks_skips_missing_run(tmp_path):
    (tmp_path / "bad.py").write_text('DESCRIPTION = "no run"\n')
    tasks = load_tasks(tmp_path)
    assert "bad" not in tasks


def test_load_tasks_skips_dunder_files(tmp_path):
    (tmp_path / "__init__.py").write_text("async def run(driver): pass\n")
    tasks = load_tasks(tmp_path)
    assert "__init__" not in tasks


def test_load_tasks_skips_bad_import(tmp_path):
    (tmp_path / "broken.py").write_text("raise ValueError('oops')\n")
    tasks = load_tasks(tmp_path)
    assert "broken" not in tasks


def test_load_tasks_missing_dir():
    tasks = load_tasks(Path("/nonexistent/tasks/dir"))
    assert tasks == {}


def test_load_tasks_empty_dir(tmp_path):
    tasks = load_tasks(tmp_path)
    assert tasks == {}


# ── load_schedule ─────────────────────────────────────────────────────────────

def test_load_schedule_valid(tmp_path):
    (tmp_path / "scheduler.toml").write_text(
        '[tasks]\nweekly = "0 7 * * 1"\nmonthly = "0 8 1 * *"\n'
    )
    schedule = load_schedule(tmp_path / "scheduler.toml")
    assert schedule == {"weekly": "0 7 * * 1", "monthly": "0 8 1 * *"}


def test_load_schedule_missing_file(tmp_path):
    schedule = load_schedule(tmp_path / "nonexistent.toml")
    assert schedule == {}


def test_load_schedule_empty_tasks_section(tmp_path):
    (tmp_path / "scheduler.toml").write_text("[tasks]\n")
    schedule = load_schedule(tmp_path / "scheduler.toml")
    assert schedule == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'task_runner'`

- [ ] **Step 3: Create `postbot/task_runner.py` with the data structures and loaders**

Create `postbot/task_runner.py`:

```python
"""Task runner — plugin discovery, schedule loading, and background scheduler."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import toml
from croniter import croniter

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class TaskEntry:
    """A discovered task plugin."""

    name: str
    run: Callable  # async def run(driver) -> None
    description: str = "—"
    last_run: datetime | None = None


class TaskRegistry:
    """Holds all discovered tasks and their cron schedules."""

    def __init__(
        self,
        tasks: dict[str, TaskEntry],
        schedule: dict[str, str],
    ) -> None:
        self.tasks = tasks
        self.schedule = schedule  # task name → cron expression

    def get(self, name: str) -> TaskEntry | None:
        return self.tasks.get(name)

    def all_tasks(self) -> list[TaskEntry]:
        return list(self.tasks.values())


# ── Loaders ───────────────────────────────────────────────────────────────────


def load_tasks(tasks_dir: Path) -> dict[str, TaskEntry]:
    """Import all .py files in *tasks_dir* and return a name → TaskEntry dict.

    Files that fail to import or lack a callable ``run`` are skipped with a
    warning.  Dunder files (``__init__.py``, etc.) are always skipped.
    Returns an empty dict if the directory does not exist.
    """
    if not tasks_dir.exists():
        logger.warning(
            f"Tasks directory {str(tasks_dir)!r} does not exist; no tasks loaded."
        )
        return {}

    tasks: dict[str, TaskEntry] = {}
    for path in sorted(tasks_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"tasks.{name}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning(f"Failed to import task {name!r}: {exc}")
            continue
        if not hasattr(module, "run") or not callable(module.run):
            logger.warning(f"Task {name!r} has no callable 'run'; skipping.")
            continue
        description = getattr(module, "DESCRIPTION", "—")
        tasks[name] = TaskEntry(name=name, run=module.run, description=description)
        logger.info(f"Loaded task {name!r}.")
    return tasks


def load_schedule(path: Path) -> dict[str, str]:
    """Read *path* (a TOML file) and return a task-name → cron-expression dict.

    Returns an empty dict if the file does not exist.
    """
    if not path.exists():
        logger.info(
            f"No scheduler config at {str(path)!r}; no tasks will be scheduled."
        )
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = toml.load(fh)
    return dict(data.get("tasks", {}))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd postbot && git add task_runner.py tests/test_task_runner.py
git commit -m "feat: add task_runner data structures and loaders"
```

---

## Task 3: `task_runner.py` — scheduling logic

**Files:**
- Modify: `postbot/task_runner.py`
- Modify: `postbot/tests/test_task_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `postbot/tests/test_task_runner.py`:

```python
from task_runner import is_due, _fire_task


# ── is_due ────────────────────────────────────────────────────────────────────

def test_is_due_fires_when_due():
    # Every minute; last ran 61s ago — should fire.
    cron = "* * * * *"
    now = datetime(2026, 4, 20, 8, 1, 0, tzinfo=timezone.utc)
    last = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)
    assert is_due(cron, last, now) is True


def test_is_due_skips_when_not_yet_due():
    # Hourly; last ran at 08:00, now is 08:30 — should NOT fire.
    cron = "0 * * * *"
    now = datetime(2026, 4, 20, 8, 30, 0, tzinfo=timezone.utc)
    last = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)
    assert is_due(cron, last, now) is False


def test_is_due_fires_when_never_run():
    # Every minute; never run — should fire (uses 60s look-back window).
    cron = "* * * * *"
    now = datetime(2026, 4, 20, 8, 1, 0, tzinfo=timezone.utc)
    assert is_due(cron, None, now) is True


def test_is_due_skips_rare_schedule_when_never_run():
    # Annually; never run, now is not the scheduled time — should NOT fire.
    cron = "0 0 1 1 *"  # 1st Jan 00:00
    now = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)
    assert is_due(cron, None, now) is False


# ── _fire_task ────────────────────────────────────────────────────────────────

def test_fire_task_sets_last_run():
    async def run(driver): pass
    entry = TaskEntry(name="t", run=run)
    before = datetime.now(timezone.utc)
    asyncio.run(_fire_task(entry, object(), lambda c, m: None, ""))
    assert entry.last_run is not None
    assert entry.last_run >= before


def test_fire_task_posts_on_error():
    async def run(driver): raise RuntimeError("boom")
    entry = TaskEntry(name="t", run=run)
    posted: list[tuple[str, str]] = []
    asyncio.run(_fire_task(entry, object(), lambda c, m: posted.append((c, m)), "log-ch"))
    assert len(posted) == 1
    assert "log-ch" == posted[0][0]
    assert "boom" in posted[0][1]


def test_fire_task_no_post_without_log_channel():
    async def run(driver): raise RuntimeError("boom")
    entry = TaskEntry(name="t", run=run)
    posted: list = []
    asyncio.run(_fire_task(entry, object(), lambda c, m: posted.append(m), ""))
    assert posted == []


def test_fire_task_does_not_update_last_run_on_error():
    async def run(driver): raise RuntimeError("boom")
    entry = TaskEntry(name="t", run=run)
    asyncio.run(_fire_task(entry, object(), lambda c, m: None, ""))
    assert entry.last_run is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd postbot && uv run pytest tests/test_task_runner.py::test_is_due_fires_when_due tests/test_task_runner.py::test_fire_task_sets_last_run -v
```

Expected: `ImportError` — `is_due` and `_fire_task` not yet defined.

- [ ] **Step 3: Add `is_due`, `_fire_task`, and `scheduler_loop` to `task_runner.py`**

Append to `postbot/task_runner.py` (after the `load_schedule` function):

```python
# ── Scheduling ────────────────────────────────────────────────────────────────


def is_due(cron_expr: str, last_run: datetime | None, now: datetime) -> bool:
    """Return True if *cron_expr* fires between *last_run* and *now*.

    If *last_run* is None (task never ran), uses a 60-second look-back window
    so the task fires on the first scheduler tick that matches the schedule.
    """
    start = last_run if last_run is not None else now - timedelta(seconds=60)
    cron = croniter(cron_expr, start)
    next_run = cron.get_next(datetime)
    return next_run <= now


async def _fire_task(
    entry: TaskEntry,
    driver,
    post_fn: Callable[[str, str], None],
    log_channel_id: str,
) -> None:
    """Run *entry.run(driver)*, update *entry.last_run*, and report errors.

    On success: updates ``entry.last_run`` to now.
    On exception: logs the error and, if *log_channel_id* is non-empty, posts
    an error notice via *post_fn*.  ``last_run`` is NOT updated on failure.
    """
    try:
        await entry.run(driver)
        entry.last_run = datetime.now(timezone.utc)
        logger.info(f"Task {entry.name!r} completed.")
    except Exception as exc:
        logger.error(f"Task {entry.name!r} failed: {exc}")
        if log_channel_id:
            post_fn(
                log_channel_id,
                f"⚠️ Scheduled task `{entry.name}` failed: {exc}",
            )


async def scheduler_loop(
    registry: TaskRegistry,
    driver,
    post_fn: Callable[[str, str], None],
    log_channel_id: str,
) -> None:
    """Background loop: wake every 60 s, fire any tasks that are due.

    Each due task runs as its own ``asyncio.Task`` so a slow task does not
    delay the next scheduler tick.
    """
    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc)
        for name, entry in list(registry.tasks.items()):
            cron_expr = registry.schedule.get(name)
            if cron_expr is None:
                continue
            if is_due(cron_expr, entry.last_run, now):
                asyncio.create_task(
                    _fire_task(entry, driver, post_fn, log_channel_id)
                )
                logger.debug(f"Scheduled task {name!r} dispatched.")
```

- [ ] **Step 4: Run all task_runner tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd postbot && git add task_runner.py tests/test_task_runner.py
git commit -m "feat: add is_due, _fire_task, and scheduler_loop to task_runner"
```

---

## Task 4: Wire `task_runner` into `PostBot`

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/test_task_runner.py`

- [ ] **Step 1: Write the failing tests for the new DM commands**

Append to `postbot/tests/test_task_runner.py`:

```python
import asyncio
import json
from unittest.mock import MagicMock, patch

from mmbot_framework import ParsedMessage

from bot import PostBot
from config import PostBotConfig


def _make_config(**kwargs) -> PostBotConfig:
    base = {
        "url": "chat.example.com",
        "token": "tok",
        "team_name": "team",
    }
    base.update(kwargs)
    return PostBotConfig(**base)


def _make_msg(text: str, channel_id: str = "dm-ch") -> ParsedMessage:
    raw = json.dumps({
        "event": "posted",
        "data": {
            "channel_type": "D",
            "post": json.dumps({
                "user_id": "u1",
                "channel_id": channel_id,
                "message": text,
                "file_ids": [],
            }),
            "sender_name": "@tester",
        },
    })
    return ParsedMessage.from_raw(raw)


def _bot_with_registry(tasks: dict, schedule: dict) -> PostBot:
    """Return a PostBot with a mocked driver and a pre-loaded task registry."""
    config = _make_config()
    with patch("bot.DriverFactory") as mock_factory:
        mock_factory.create.return_value = MagicMock()
        bot = PostBot(config)
    bot._task_registry = task_runner.TaskRegistry(tasks, schedule)
    return bot


def test_handle_tasks_lists_all_tasks():
    async def run(driver): pass
    entry = TaskEntry(name="weekly", run=run, description="Weekly plan")
    bot = _bot_with_registry({"weekly": entry}, {"weekly": "0 7 * * 1"})
    msg = _make_msg("!tasks")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    asyncio.run(bot._handle_tasks(msg))

    assert len(posted) == 1
    assert "weekly" in posted[0]
    assert "Weekly plan" in posted[0]
    assert "0 7 * * 1" in posted[0]


def test_handle_tasks_shows_manual_only_when_unscheduled():
    async def run(driver): pass
    entry = TaskEntry(name="manual", run=run)
    bot = _bot_with_registry({"manual": entry}, {})
    msg = _make_msg("!tasks")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    asyncio.run(bot._handle_tasks(msg))

    assert "manual only" in posted[0]


def test_handle_run_unknown_task():
    bot = _bot_with_registry({}, {})
    msg = _make_msg("!run nonexistent")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    asyncio.run(bot._handle_run(msg))

    assert any("Unknown task" in p for p in posted)


def test_handle_run_no_task_name():
    bot = _bot_with_registry({}, {})
    msg = _make_msg("!run ")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    asyncio.run(bot._handle_run(msg))

    assert any("Usage" in p for p in posted)


def test_handle_run_successful_task():
    ran: list[str] = []
    async def run(driver): ran.append("ran")
    entry = TaskEntry(name="ok_task", run=run)
    bot = _bot_with_registry({"ok_task": entry}, {})
    msg = _make_msg("!run ok_task")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    async def _run():
        await bot._handle_run(msg)
        await asyncio.sleep(0)  # let the fire-and-forget task complete

    asyncio.run(_run())

    assert ran == ["ran"]
    assert any("⏳" in p for p in posted)
    assert any("✅" in p for p in posted)


def test_handle_run_failing_task_reports_error():
    async def run(driver): raise ValueError("exploded")
    entry = TaskEntry(name="bad_task", run=run)
    bot = _bot_with_registry({"bad_task": entry}, {})
    msg = _make_msg("!run bad_task")
    posted: list[str] = []
    bot._post = lambda ch, text: posted.append(text)

    async def _run():
        await bot._handle_run(msg)
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert any("❌" in p for p in posted)
    assert any("exploded" in p for p in posted)
```

- [ ] **Step 2: Run to confirm the tests fail**

```bash
cd postbot && uv run pytest tests/test_task_runner.py::test_handle_tasks_lists_all_tasks -v
```

Expected: `AttributeError` — `PostBot` has no `_task_registry` attribute yet.

- [ ] **Step 3: Add the task registry attribute and command registrations to `PostBot.__init__`**

In `postbot/bot.py`, add `import task_runner` and `from datetime import datetime, timezone` near the top imports, then in `PostBot.__init__` after the existing command registrations:

```python
        # Task scheduler registry (populated in on_start).
        self._task_registry: task_runner.TaskRegistry | None = None

        self._dispatcher.register("!tasks", self._handle_tasks)
        self._dispatcher.register("!run", self._handle_run)
```

- [ ] **Step 4: Add task loading to `PostBot.on_start`**

In `postbot/bot.py`, at the end of `PostBot.on_start()` (after `logger.info("Channel cache pre-warmed.")`):

```python
        tasks = task_runner.load_tasks(self.config.tasks_dir)
        schedule = task_runner.load_schedule(self.config.scheduler_toml_path)
        self._task_registry = task_runner.TaskRegistry(tasks, schedule)
        logger.info(
            f"Task scheduler ready: {len(tasks)} task(s) loaded, "
            f"{len(schedule)} scheduled."
        )
```

- [ ] **Step 5: Add `_handle_tasks` to `PostBot`**

In `postbot/bot.py`, add after the `_handle_add_alias` method:

```python
    async def _handle_tasks(self, msg: ParsedMessage) -> None:
        """List all discovered tasks with their schedule and last-run time.

        Triggered by: ``!tasks``
        """
        if self._task_registry is None:
            self._post(msg.channel_id, "⚠️ Task registry not yet loaded.")
            return
        lines = [
            "| Task | Description | Schedule | Last run |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for entry in sorted(self._task_registry.all_tasks(), key=lambda e: e.name):
            cron_expr = self._task_registry.schedule.get(entry.name, "")
            schedule_str = cron_expr if cron_expr else "— (manual only)"
            last_run_str = (
                entry.last_run.strftime("%Y-%m-%d %H:%M UTC")
                if entry.last_run
                else "never"
            )
            lines.append(
                f"| `{entry.name}` | {entry.description} "
                f"| {schedule_str} | {last_run_str} |"
            )
        self._post(msg.channel_id, "\n".join(lines))

    async def _handle_run(self, msg: ParsedMessage) -> None:
        """Immediately run a named task in the background.

        Triggered by: ``!run <task_name>``

        Replies with ⏳ immediately, then ✅ or ❌ when the task finishes.
        """
        if self._task_registry is None:
            self._post(msg.channel_id, "⚠️ Task registry not yet loaded.")
            return
        task_name = msg.text[len("!run"):].strip()
        if not task_name:
            self._post(
                msg.channel_id,
                "Usage: `!run <task_name>`. Use `!tasks` to see available tasks.",
            )
            return
        entry = self._task_registry.get(task_name)
        if entry is None:
            self._post(
                msg.channel_id,
                f"❌ Unknown task: `{task_name}`. Use `!tasks` to see available tasks.",
            )
            return

        self._post(msg.channel_id, f"⏳ Running `{task_name}`...")
        channel_id = msg.channel_id
        name = task_name

        async def _run_and_report() -> None:
            try:
                await entry.run(self.driver)
                entry.last_run = datetime.now(timezone.utc)
                self._post(channel_id, f"✅ `{name}` completed.")
            except Exception as exc:
                logger.error(f"Task {name!r} failed during !run: {exc}")
                self._post(channel_id, f"❌ `{name}` failed: {exc}")

        asyncio.create_task(_run_and_report())
```

- [ ] **Step 6: Run the new tests to confirm they pass**

```bash
cd postbot && uv run pytest tests/test_task_runner.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
cd postbot && git add bot.py tests/test_task_runner.py
git commit -m "feat: add !tasks and !run commands and task registry to PostBot"
```

---

## Task 5: Override `_async_main` to start the scheduler loop

**Files:**
- Modify: `postbot/bot.py`

No new tests are needed here — the scheduler loop itself is tested via `_fire_task` and `is_due`. This step wires everything together.

- [ ] **Step 1: Add `_async_main` override to `PostBot`**

In `postbot/bot.py`, add the following method to `PostBot` (after `_handle_run`). This replicates the base-class `_async_main` with one addition: a third background `asyncio.Task` for the scheduler.

```python
    async def _async_main(self) -> None:
        """Start background tasks (session cleanup, cache refresh, scheduler) and open WebSocket.

        Overrides :meth:`~mmbot_framework.BaseBot._async_main` to add the task
        scheduler as a third background task alongside the inherited cleanup and
        cache-refresh loops.
        """
        await self.on_start()
        cleanup_task = asyncio.create_task(self._session_cleanup_loop())
        cache_task = asyncio.create_task(self._cache_refresh_loop())
        scheduler_task = asyncio.create_task(
            task_runner.scheduler_loop(
                self._task_registry,
                self.driver,
                self._post,
                self.config.bot_log_channel_id,
            )
        )

        async def _raw_ws_handler(raw_msg: str | dict) -> None:
            raw_str = raw_msg if isinstance(raw_msg, str) else json.dumps(raw_msg)
            msg = ParsedMessage.from_raw(raw_str)
            if msg is not None:
                await self._pipeline.run(msg, self._dispatch)

        from mattermostdriver.websocket import Websocket  # noqa: PLC0415

        self.driver.websocket = Websocket(self.driver.options, self.driver.client.token)

        try:
            logger.info("Opening WebSocket. Press Ctrl+C to stop.")
            await self.driver.websocket.connect(_raw_ws_handler)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Interrupted. Shutting down.")
        finally:
            logger.debug("Cancelling background tasks.")
            cleanup_task.cancel()
            cache_task.cancel()
            scheduler_task.cancel()
            for task in (cleanup_task, cache_task, scheduler_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```bash
cd postbot && uv run pytest tests/ -v
```

Expected: all tests pass (the old `test_main.py` still skips itself cleanly).

- [ ] **Step 3: Commit**

```bash
cd postbot && git add bot.py
git commit -m "feat: override _async_main to run task scheduler as background task"
```

---

## Task 6: Create `tasks/` directory, `scheduler.toml`, and example task

**Files:**
- Create: `postbot/tasks/example_task.py`
- Create: `postbot/scheduler.toml`

- [ ] **Step 1: Create the `tasks/` directory with an example task**

Create `postbot/tasks/example_task.py`:

```python
"""Example task — prints a greeting to the bot log channel.

Copy this file and rename it to create a new task.
The filename (without .py) becomes the task's name as shown in !tasks.

Required:
    async def run(driver) -> None   — called by the scheduler and !run

Optional:
    DESCRIPTION: str                — shown in !tasks output
"""

DESCRIPTION = "Example task: posts a test message to the bot log channel"


async def run(driver) -> None:
    """Post a test message.

    Replace this body with your actual task logic.
    ``driver`` is an authenticated mattermostdriver.Driver instance.

    Example — post to a channel by ID:
        driver.posts.create_post({
            "channel_id": "your_channel_id_here",
            "message": "Hello from the task scheduler!",
        })
    """
    # This example task does nothing — remove or replace this line.
    pass
```

- [ ] **Step 2: Create `scheduler.toml`**

Create `postbot/scheduler.toml`:

```toml
# Task scheduler configuration.
# Each entry maps a task name (filename without .py) to a cron expression.
# Tasks not listed here can still be triggered manually via !run.
#
# Cron format: minute hour day-of-month month day-of-week
# Examples:
#   "0 7 * * 1"   — every Monday at 07:00
#   "0 8 1 * *"   — 1st of every month at 08:00
#   "0 6 5 8 *"   — 5th August at 06:00

[tasks]
# example_task = "0 9 * * 1"   # uncomment to schedule the example task
```

- [ ] **Step 3: Add `tasks/` and `scheduler.toml` to git, confirm `!tasks` and `!run` work**

```bash
cd postbot && git add tasks/example_task.py scheduler.toml
git commit -m "feat: add tasks/ directory, scheduler.toml, and example task plugin"
```

- [ ] **Step 4: Smoke-test locally**

```bash
cd postbot && uv run main.py
```

Then DM the bot:
- `!tasks` — should show `example_task` with no schedule and last run `never`
- `!run example_task` — should reply ⏳ then ✅

---

## Self-review

**Spec coverage:**
- Task plugin interface (`async def run(driver)`, `DESCRIPTION`) ✓ Task 2 + 6
- `scheduler.toml` with cron syntax ✓ Task 2 + 6
- `load_tasks`, `load_schedule` ✓ Task 2
- `is_due`, `_fire_task`, `scheduler_loop` ✓ Task 3
- `!tasks` command ✓ Task 4
- `!run` command (immediate reply + background task + success/failure report) ✓ Task 4
- Error handling: bad imports skipped at startup ✓ Task 2; runtime errors reported via DM/log channel ✓ Task 3+4; failing task doesn't crash bot ✓ Task 3
- `croniter>=2.0` dependency ✓ Task 1
- `tasks_dir` and `scheduler_toml_path` config fields ✓ Task 1
- Scheduler as third background `asyncio.Task`, cancelled on shutdown ✓ Task 5

**Placeholder scan:** No TBDs. All code steps show complete implementations.

**Type consistency:**
- `TaskEntry` defined in Task 2, used consistently in Tasks 3 and 4
- `TaskRegistry(tasks, schedule)` — same constructor signature across all tasks
- `_fire_task(entry, driver, post_fn, log_channel_id)` — same signature in Task 3 definition and Task 4 (via `_run_and_report` inline, not calling `_fire_task` directly — intentional, since `!run` posts to the DM channel rather than the log channel)
- `scheduler_loop(registry, driver, post_fn, log_channel_id)` — matches Task 5 call site
- `bot._post` used as `post_fn` — signature is `(channel_id: str, text: str) -> None` ✓
