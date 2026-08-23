"""POST /api/broadcast — send a message to a list of Mattermost channels."""
import base64
import binascii
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import verify_api_secret
from api.context import get_bot
from bot import format_broadcast_message
import database as db_module

logger = logging.getLogger(__name__)
router = APIRouter()


class AttachmentPayload(BaseModel):
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"


class BroadcastRequest(BaseModel):
    message: str
    channel_ids: list[str] = Field(..., min_length=1)
    sender: str = "Web Interface"
    attachments: list[AttachmentPayload] = Field(default_factory=list)


class BroadcastResponse(BaseModel):
    sent: int
    failed: int
    errors: list[str]


@router.post("/api/broadcast", dependencies=[Depends(verify_api_secret)])
def post_broadcast(body: BroadcastRequest) -> BroadcastResponse:
    """Send `body.message` to each channel in `body.channel_ids`."""
    bot = get_bot()
    broadcast_text = format_broadcast_message(body.sender, body.message)
    sent = 0
    failed = 0
    errors: list[str] = []
    decoded_attachments: list[tuple[str, bytes, str]] = []
    for attachment in body.attachments:
        try:
            decoded_attachments.append((
                attachment.filename,
                base64.b64decode(attachment.content_base64),
                attachment.content_type,
            ))
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid attachment payload for {attachment.filename}") from exc

    all_uploaded_ids: list[str] = []
    for channel_id in body.channel_ids:
        channel_file_ids: list[str] = []
        for filename, content, content_type in decoded_attachments:
            try:
                upload = bot.driver.files.upload_file(
                    channel_id=channel_id,
                    files={"files": (filename, content, content_type)},
                )
                channel_file_ids.append(upload["file_infos"][0]["id"])
            except Exception as exc:
                logger.error(
                    f"API broadcast: failed to upload attachment {filename!r} "
                    f"to channel {channel_id!r}: {exc}"
                )
        all_uploaded_ids.extend(channel_file_ids)
        try:
            bot.driver.posts.create_post(
                {
                    "channel_id": channel_id,
                    "message": broadcast_text,
                    "file_ids": channel_file_ids,
                }
            )
            sent += 1
            logger.info(f"API broadcast: posted to channel {channel_id!r}")
        except Exception as exc:
            failed += 1
            errors.append(f"{channel_id}: {exc}")
            logger.error(
                f"API broadcast: failed to post to channel {channel_id!r}: {exc}"
            )

    ch_cache = bot.cache.get("channels")
    target_names = []
    for cid in body.channel_ids:
        if ch_cache and cid in ch_cache["by_id"]:
            target_names.append(ch_cache["by_id"][cid]["display_name"])
        else:
            target_names.append(cid)
    db_module.log_broadcast(
        sender_name=body.sender,
        message_content=body.message,
        target_channels=target_names,
        file_ids=all_uploaded_ids,
    )

    return BroadcastResponse(sent=sent, failed=failed, errors=errors)
