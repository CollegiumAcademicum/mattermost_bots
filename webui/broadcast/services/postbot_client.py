"""HTTP client for the postbot broadcast API."""
from broadcast.admin_dashboard.services import admin_client


def send_broadcast(
    message: str,
    channel_ids: list[str],
    sender: str = "Web Interface",
) -> dict:
    """POST /api/broadcast on postbot. Returns {"sent", "failed", "errors"}.

    Raises requests.ConnectionError if postbot is unreachable.
    Raises requests.HTTPError on non-2xx response.
    """
    return admin_client._call(
        "POST",
        "/api/broadcast",
        json={"message": message, "channel_ids": channel_ids, "sender": sender},
    )
