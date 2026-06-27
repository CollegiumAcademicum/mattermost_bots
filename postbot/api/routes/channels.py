"""GET /api/channels — returns all channel groups with resolved MM names."""
from fastapi import APIRouter, Depends

from api.auth import verify_api_secret
from api.context import get_bot

router = APIRouter()


def _resolve(channel_ids: list[str], by_id: dict) -> list[dict]:
    result = []
    for cid in channel_ids:
        info = by_id.get(cid, {})
        result.append({
            "id": cid,
            "display_name": info.get("display_name", cid),
            "channel_name": info.get("name", cid),
        })
    return result


@router.get("/api/channels", dependencies=[Depends(verify_api_secret)])
def get_channels() -> dict:
    """Return all channel groups with Mattermost display and system names."""
    bot = get_bot()
    ch_cache = bot.cache.get("channels") or {}
    by_id: dict = ch_cache.get("by_id", {})

    groups = {
        name: _resolve(entry.channels, by_id)
        for name, entry in bot._visible_groups.items()
    }
    private_groups = {
        name: _resolve(entry.channels, by_id)
        for name, entry in bot._private_groups.items()
    }

    # All channels the bot has access to, sorted by display name.
    individual = _resolve(list(by_id.keys()), by_id)
    individual.sort(key=lambda c: c["display_name"])

    return {
        "groups": groups,
        "private_groups": private_groups,
        "individual_channels": individual,
    }
