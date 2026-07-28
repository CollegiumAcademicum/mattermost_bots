"""Neubau maintenance task poster — downloads Excel, posts tasks with PDF attachments."""

from __future__ import annotations

import io
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import openpyxl
import requests


DESCRIPTION = "Der Instandhaltungsverteiler für den Neubau"
FILE_URL = "https://cacloud.ca-hd.de/index.php/s/pYwBSHgcMDTPqbW/download"
OVERVIEW_CHANNEL_ID = "fqx1i11oc78d7dui9if8bo184y"

_EPOCH = date(2023, 2, 17)

def _abs_month(d: date) -> int:
    return (d.year - _EPOCH.year) * 12 + (d.month - _EPOCH.month)


def _parse_excel(content: bytes) -> list[dict]:
    ws = openpyxl.load_workbook(io.BytesIO(content)).active
    return [
        {
            "wg_name": row[0],
            "channel_id": row[1],
            "heading": row[2],
            "description": row[3],
            "docx_url": str(row[4]).rstrip("/") + "/download",
        }
        for row in ws.iter_rows(min_row=4, values_only=True)
        if row[1]
    ]


def _to_pdf(docx_url: str, tmpdir: str) -> Path:
    resp = requests.get(docx_url, timeout=30)
    resp.raise_for_status()
    docx = Path(tmpdir) / "Aufgabenkarte.docx"
    docx.write_bytes(resp.content)
    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, str(docx)],
        check=True,
        capture_output=True,
    )
    return Path(tmpdir) / "Aufgabenkarte.pdf"


async def run(driver, args: str = "") -> None:
    resp = requests.get(FILE_URL, timeout=10)
    resp.raise_for_status()

    _MONTHS = ("Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember")
    today = date.today()
    this_month = _MONTHS[today.month - 1]

    tasks = _parse_excel(resp.content)
    n = len(tasks)
    offset = _abs_month(today) % n
    channel_ids = [t["channel_id"] for t in tasks]
    channel_ids = channel_ids[offset:] + channel_ids[:offset]

    rows = "\n".join(
        f"| {tasks[(i + offset) % n]['wg_name']} | {task['heading']} | {task['description']} |"
        for i, task in enumerate(tasks)
    )
    table = "| WG | Aufgabe | Beschreibung |\n|---|---|---|\n" + rows
    driver.posts.create_post({"channel_id": OVERVIEW_CHANNEL_ID, "message": table})

    for task, channel_id in zip(tasks, channel_ids):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = _to_pdf(task["docx_url"], tmpdir)
            with open(pdf, "rb") as f:
                upload = driver.files.upload_file(
                    channel_id=channel_id,
                    files={"files": (pdf.name, f, "application/pdf")},
                )
            file_id = upload["file_infos"][0]["id"]
            driver.posts.create_post({
                "channel_id": channel_id,
                "message": f"##### Eure Instandhaltungsaufgabe im {this_month}:\n### {task['heading']}\n{task['description']}",
                "file_ids": [file_id],
            })