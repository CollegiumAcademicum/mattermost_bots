"""Sends a short reminder to all Cluster channels about their maintenance task."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DESCRIPTION = "Erinnerung an Instandhaltungsaufgaben in alle Cluster-Kanäle"

_FILE_URLS = [
    "https://cacloud.ca-hd.de/index.php/s/mb3rsJLTRnoPDJD/download",  # Altbau
    "https://cacloud.ca-hd.de/index.php/s/pYwBSHgcMDTPqbW/download",  # Neubau
]

MESSAGE = "Denkt bitte daran, eure Instandhaltungsaufgabe diesen Monat zu erledigen!"


async def run(driver, args: str = "") -> None:
    import requests
    from _instandhaltung_lib import channel_ids_from_excel
    seen: set[str] = set()
    for url in _FILE_URLS:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            channel_ids = channel_ids_from_excel(resp.content)
        except Exception as exc:
            logger.error("Failed to load Excel from %s: %s", url, exc)
            continue
        for channel_id in channel_ids:
            if channel_id in seen:
                continue
            seen.add(channel_id)
            try:
                driver.posts.create_post({"channel_id": channel_id, "message": MESSAGE})
            except Exception as exc:
                logger.error("Failed to post reminder to channel %s: %s", channel_id, exc)