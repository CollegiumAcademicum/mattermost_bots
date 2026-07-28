"""Neubau maintenance task poster — downloads Excel, posts tasks with PDF attachments."""

from __future__ import annotations

DESCRIPTION = "Der Instandhaltungsverteiler für den Neubau"
FILE_URL = "https://cacloud.ca-hd.de/index.php/s/pYwBSHgcMDTPqbW/download"
OVERVIEW_CHANNEL_ID = "fqx1i11oc78d7dui9if8bo184y"


async def run(driver, args: str = "") -> None:
    from _instandhaltung_lib import run_instandhaltung
    await run_instandhaltung(driver, FILE_URL, OVERVIEW_CHANNEL_ID)