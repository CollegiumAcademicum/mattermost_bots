"""Fetches and caches channel data from postbot's /api/channels endpoint."""
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds
_cache: dict = {}
_cache_time: float = 0.0


def get_channels() -> dict:
    """Return channel data from postbot. Caches for 5 minutes.

    On fetch failure, returns the last known good cache (may be empty dict
    on first call if postbot is unreachable).
    """
    global _cache, _cache_time
    now = time.monotonic()
    if _cache and now - _cache_time < _CACHE_TTL:
        return _cache
    try:
        resp = requests.get(
            f"{settings.POSTBOT_API_URL}/api/channels",
            headers={"Authorization": f"Bearer {settings.POSTBOT_API_SECRET}"},
            timeout=5,
        )
        resp.raise_for_status()
        _cache = resp.json()
        _cache_time = now
    except (requests.ConnectionError, requests.Timeout) as exc:
        if not _cache:
            raise  # no stale data to fall back on — let the view handle it
        logger.warning(f"postbot unreachable, serving stale channel cache: {exc}")
    except Exception as exc:
        logger.error(f"Failed to fetch channels from postbot API: {exc}")
    return _cache
