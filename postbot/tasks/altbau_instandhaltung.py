"""Altbau maintenance task poster — downloads Excel, posts tasks with PDF attachments."""

from __future__ import annotations

DESCRIPTION = "Der Instandhaltungsverteiler für den Altbau"
FILE_URL = "https://cacloud.ca-hd.de/index.php/s/mb3rsJLTRnoPDJD/download"
OVERVIEW_CHANNEL_ID = "was8uq7qbbb65c4hprysm7m1be"


async def run(driver, args: str = "") -> None:
    from _instandhaltung_lib import run_instandhaltung
    await run_instandhaltung(driver, FILE_URL, OVERVIEW_CHANNEL_ID)