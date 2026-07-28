"""Sends a short reminder to all Cluster channels about their maintenance task."""

from __future__ import annotations

import io

import openpyxl
import requests

DESCRIPTION = "Erinnerung an Instandhaltungsaufgaben in alle Cluster-Kanäle"

_FILE_URLS = [
    "https://cacloud.ca-hd.de/index.php/s/mb3rsJLTRnoPDJD/download",  # Altbau
    "https://cacloud.ca-hd.de/index.php/s/pYwBSHgcMDTPqbW/download",  # Neubau
]

MESSAGE = "Denkt bitte daran, eure Instandhaltungsaufgabe diesen Monat zu erledigen!"


def _channel_ids(content: bytes) -> list[str]:
    ws = openpyxl.load_workbook(io.BytesIO(content)).active
    return [row[1] for row in ws.iter_rows(min_row=4, values_only=True) if row[1]]


async def run(driver, args: str = "") -> None:
    seen: set[str] = set()
    for url in _FILE_URLS:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        for channel_id in _channel_ids(resp.content):
            if channel_id not in seen:
                seen.add(channel_id)
                driver.posts.create_post({"channel_id": channel_id, "message": MESSAGE})