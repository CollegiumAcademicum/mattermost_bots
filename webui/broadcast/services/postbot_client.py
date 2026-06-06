"""HTTP client for the postbot broadcast API."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_broadcast(
    message: str,
    channel_ids: list[str],
    sender: str = "Web Interface",
) -> dict:
    """POST /api/broadcast on postbot. Returns {"sent", "failed", "errors"}.

    Raises requests.ConnectionError if postbot is unreachable.
    Raises requests.HTTPError on non-2xx response.
    """
    resp = requests.post(
        f"{settings.POSTBOT_API_URL}/api/broadcast",
        json={"message": message, "channel_ids": channel_ids, "sender": sender},
        headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
