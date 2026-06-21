"""GET /api/config and PUT /api/config — channel configuration management."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import verify_api_secret
from api.context import get_bot
from bot import GroupEntry, WhitelistEntry

router = APIRouter()


class GroupPayload(BaseModel):
    channels: list[str] = []
    aliases: list[str] = []


class WhitelistPayload(BaseModel):
    id: str
    aliases: list[str] = []


class ConfigPayload(BaseModel):
    groups: dict[str, GroupPayload] = {}
    private_groups: dict[str, GroupPayload] = {}
    whitelist: dict[str, WhitelistPayload] = {}


@router.get("/api/config", dependencies=[Depends(verify_api_secret)])
def get_config() -> dict:
    """Return the current channel configuration (groups and whitelist)."""
    bot = get_bot()
    return {
        "groups": {
            name: {"channels": entry.channels, "aliases": entry.aliases}
            for name, entry in bot._visible_groups.items()
        },
        "private_groups": {
            name: {"channels": entry.channels, "aliases": entry.aliases}
            for name, entry in bot._private_groups.items()
        },
        "whitelist": {
            name: {"id": entry.id, "aliases": entry.aliases}
            for name, entry in bot._whitelist.items()
        },
    }


@router.put("/api/config", dependencies=[Depends(verify_api_secret)])
def put_config(payload: ConfigPayload) -> dict:
    """Replace the channel configuration and persist it to channels.toml."""
    bot = get_bot()
    bot._visible_groups = {
        name: GroupEntry(channels=g.channels, aliases=g.aliases)
        for name, g in payload.groups.items()
    }
    bot._private_groups = {
        name: GroupEntry(channels=g.channels, aliases=g.aliases)
        for name, g in payload.private_groups.items()
    }
    bot._whitelist = {
        name: WhitelistEntry(id=w.id, label=name, aliases=w.aliases)
        for name, w in payload.whitelist.items()
    }
    bot._save_channel_data()
    bot._build_alias_map()
    return {"ok": True}
