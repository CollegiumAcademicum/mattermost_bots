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
