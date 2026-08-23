"""HTTP client for the postbot broadcast API."""
import base64
from pathlib import Path

from broadcast.admin_dashboard.services import admin_client


def send_broadcast(
    message: str,
    channel_ids: list[str],
    sender: str = "Web Interface",
    attachments: list[dict] | None = None,
) -> dict:
    """POST /api/broadcast on postbot. Returns {"sent", "failed", "errors"}.

    Raises requests.ConnectionError if postbot is unreachable.
    Raises requests.HTTPError on non-2xx response.
    """
    payload = {"message": message, "channel_ids": channel_ids, "sender": sender}
    if attachments:
        payload["attachments"] = [
            {
                "filename": attachment["name"],
                "content_type": attachment.get("content_type", "application/octet-stream"),
                "content_base64": base64.b64encode(
                    Path(attachment["path"]).read_bytes()
                ).decode("utf-8"),
            }
            for attachment in attachments
            if attachment.get("path") and attachment.get("name")
        ]

    return admin_client._call(
        "POST",
        "/api/broadcast",
        json=payload,
    )
