"""HTTP client for the postbot admin API."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _call(method: str, path: str, **kwargs) -> dict:
    resp = requests.request(
        method,
        f"{settings.POSTBOT_API_URL}{path}",
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
        **kwargs,
    )
    resp.raise_for_status()
    return resp.json()


def get_history(page: int = 1, per_page: int = 20) -> dict:
    return _call("GET", "/api/history", params={"page": page, "per_page": per_page})


def get_config() -> dict:
    return _call("GET", "/api/config")


def put_config(config: dict) -> dict:
    return _call("PUT", "/api/config", json=config)


def get_channels() -> dict:
    return _call("GET", "/api/channels")


def get_tasks() -> dict:
    return _call("GET", "/api/tasks")


def run_task(name: str) -> dict:
    return _call("POST", f"/api/tasks/{name}/run")


def set_task_schedule(name: str, cron: str | None) -> dict:
    return _call("PUT", f"/api/tasks/{name}/schedule", json={"cron": cron})
