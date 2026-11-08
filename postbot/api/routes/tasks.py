"""GET /api/tasks, POST /api/tasks/{name}/run, PUT /api/tasks/{name}/schedule."""
import asyncio

import toml
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import task_runner as task_runner_module
from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


@router.get("/api/tasks", dependencies=[Depends(verify_api_secret)])
def get_tasks() -> dict:
    """Return all discovered tasks with their schedule and last-run time."""
    bot = get_bot()
    registry = bot._task_registry
    tasks = []
    for entry in registry.all_tasks():
        tasks.append({
            "name": entry.name,
            "description": entry.description,
            "last_run": entry.last_run.isoformat() if entry.last_run else None,
            "schedule": registry.schedule.get(entry.name),
        })
    return {"tasks": tasks}


@router.post("/api/tasks/{name}/run", dependencies=[Depends(verify_api_secret)])
async def run_task(name: str) -> dict:
    """Manually trigger a task. Fire-and-forget — returns immediately."""
    bot = get_bot()
    registry = bot._task_registry
    entry = registry.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Task {name!r} not found.")
    asyncio.create_task(
        task_runner_module._fire_task(
            entry,
            bot.driver,
            bot._post,
            bot.config.bot_log_channel_id,
        )
    )
    return {"ok": True}


class SchedulePayload(BaseModel):
    cron: str | None


@router.put("/api/tasks/{name}/schedule", dependencies=[Depends(verify_api_secret)])
def set_task_schedule(name: str, payload: SchedulePayload) -> dict:
    """Set or remove a task's cron schedule, persisting to scheduler.toml."""
    bot = get_bot()
    registry = bot._task_registry
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Task {name!r} not found.")

    if payload.cron is not None:
        if not all(croniter.is_valid(e.strip()) for e in payload.cron.split(";")):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid cron expression: {payload.cron!r}",
            )
        registry.schedule[name] = payload.cron
    else:
        registry.schedule.pop(name, None)

    with open(bot.config.scheduler_toml_path, "w", encoding="utf-8") as fh:
        toml.dump({"tasks": registry.schedule}, fh)

    return {"ok": True}
