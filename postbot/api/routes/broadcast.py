"""POST /api/broadcast — send a message to a list of Mattermost channels."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import verify_api_secret
from api.context import get_bot

logger = logging.getLogger(__name__)
router = APIRouter()


class BroadcastRequest(BaseModel):
    message: str
    channel_ids: list[str] = Field(..., min_length=1)
    sender: str = "Web Interface"


class BroadcastResponse(BaseModel):
    sent: int
    failed: int
    errors: list[str]


@router.post("/api/broadcast", dependencies=[Depends(verify_api_secret)])
def post_broadcast(body: BroadcastRequest) -> BroadcastResponse:
    """Send `body.message` to each channel in `body.channel_ids`."""
    bot = get_bot()
    broadcast_text = (
        f"📢 **Message from {body.sender}**\n\n\n"
        f"{body.message}"
        f"\n\n\n\n*--- END of Message ---*\n"
    )
    sent = 0
    failed = 0
    errors: list[str] = []

    for channel_id in body.channel_ids:
        try:
            bot.driver.posts.create_post(
                {"channel_id": channel_id, "message": broadcast_text}
            )
            sent += 1
            logger.info(f"API broadcast: posted to channel {channel_id!r}")
        except Exception as exc:
            failed += 1
            errors.append(f"{channel_id}: {exc}")
            logger.error(
                f"API broadcast: failed to post to channel {channel_id!r}: {exc}"
            )

    return BroadcastResponse(sent=sent, failed=failed, errors=errors)
