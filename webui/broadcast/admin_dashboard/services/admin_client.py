"""HTTP client for the postbot admin API."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def get_history(page: int = 1, per_page: int = 20) -> dict:
    """Fetch paginated broadcast history from postbot.

    Returns dict with keys: total, page, per_page, results.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.get(
        f"{settings.POSTBOT_API_URL}/api/history",
        params={"page": page, "per_page": per_page},
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_config() -> dict:
    """Fetch channel config from postbot.

    Returns dict with keys: groups, private_groups, whitelist.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.get(
        f"{settings.POSTBOT_API_URL}/api/config",
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def put_config(config: dict) -> dict:
    """Write channel config to postbot.

    Returns {"ok": True} on success.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.put(
        f"{settings.POSTBOT_API_URL}/api/config",
        json=config,
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
