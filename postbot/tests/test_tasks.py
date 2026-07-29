"""Tests for task plugins: kuendigung_reminder and instandhaltung variants."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

TASKS_DIR = Path(__file__).parent.parent / "tasks"
INTEGRATION = os.getenv("INTEGRATION_TESTS")

_ALTBAU_URL = "https://cacloud.ca-hd.de/index.php/s/mb3rsJLTRnoPDJD/download"
_NEUBAU_URL = "https://cacloud.ca-hd.de/index.php/s/pYwBSHgcMDTPqbW/download"


def _ensure_lib():
    """Pre-load _instandhaltung_lib into sys.modules (mirrors task_runner behaviour)."""
    if "_instandhaltung_lib" not in sys.modules:
        lib_path = TASKS_DIR / "_instandhaltung_lib.py"
        spec = importlib.util.spec_from_file_location("_instandhaltung_lib", lib_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_instandhaltung_lib"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["_instandhaltung_lib"]


def _load(name: str):
    _ensure_lib()
    spec = importlib.util.spec_from_file_location(name, TASKS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_xlsx(rows: list[list]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for i, row in enumerate(rows, start=4):
        for j, val in enumerate(row):
            ws.cell(row=i, column=j + 1, value=val)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── kuendigung_reminder ───────────────────────────────────────────────────────

class TestKuendigungReminder:
    def setup_method(self):
        self.kr = _load("kuendigung_reminder")

    def test_quarters_cover_all_four(self):
        assert set(self.kr._QUARTERS.keys()) == {1, 2, 3, 4}

    def test_quarter_date_format(self):
        import re
        for move_out, deadline in self.kr._QUARTERS.values():
            assert re.match(r"\d{2}\.\d{2}$", move_out), f"bad move_out: {move_out!r}"
            assert re.match(r"\d{2}\.\d{2}$", deadline), f"bad deadline: {deadline!r}"

    def test_q2_dates_match_spec(self):
        assert self.kr._QUARTERS[2] == ("30.06", "05.05")

    def test_run_posts_to_every_channel(self):
        driver = MagicMock()
        asyncio.run(self.kr.run(driver))
        assert driver.posts.create_post.call_count == len(self.kr.CHANNELS)

    def test_run_message_contains_email_and_heading(self):
        driver = MagicMock()
        asyncio.run(self.kr.run(driver))
        msg = driver.posts.create_post.call_args_list[0][0][0]["message"]
        assert "mietverwaltung@collegiumacademicum.de" in msg
        assert "Kündigungsfrist" in msg

    def test_run_message_contains_current_year(self):
        import datetime
        driver = MagicMock()
        asyncio.run(self.kr.run(driver))
        msg = driver.posts.create_post.call_args_list[0][0][0]["message"]
        assert str(datetime.date.today().year) in msg


# ── _instandhaltung_lib ───────────────────────────────────────────────────────

class TestInstandhaltungLib:
    def setup_method(self):
        self.lib = _ensure_lib()

    def test_parse_excel_returns_all_rows(self):
        content = _make_xlsx([
            ["WG1", "ch1", "Heading1", "Desc1", "https://cloud.example.com/s/abc"],
            ["WG2", "ch2", "Heading2", "Desc2", "https://cloud.example.com/s/xyz/"],
        ])
        tasks = self.lib.parse_excel(content)
        assert len(tasks) == 2

    def test_parse_excel_row_fields(self):
        content = _make_xlsx([
            ["WG1", "ch1", "Heading1", "Desc1", "https://cloud.example.com/s/abc"],
        ])
        task = self.lib.parse_excel(content)[0]
        assert task == {
            "wg_name": "WG1",
            "channel_id": "ch1",
            "heading": "Heading1",
            "description": "Desc1",
            "docx_url": "https://cloud.example.com/s/abc/download",
        }

    def test_parse_excel_strips_trailing_slash_before_download(self):
        content = _make_xlsx([["WG", "ch", "H", "D", "https://cloud.example.com/s/xyz/"]])
        task = self.lib.parse_excel(content)[0]
        assert task["docx_url"] == "https://cloud.example.com/s/xyz/download"

    def test_parse_excel_skips_rows_without_channel_id(self):
        content = _make_xlsx([
            ["WG1", "ch1", "H", "D", "https://url"],
            ["WG2", None, "H", "D", "https://url"],
        ])
        assert len(self.lib.parse_excel(content)) == 1

    def test_channel_ids_from_excel(self):
        content = _make_xlsx([
            ["WG1", "ch1", "H", "D", "https://url"],
            ["WG2", "ch2", "H", "D", "https://url"],
        ])
        assert self.lib.channel_ids_from_excel(content) == ["ch1", "ch2"]

    def test_channel_ids_skips_empty(self):
        content = _make_xlsx([
            ["WG1", "ch1", "H", "D", "https://url"],
            ["WG2", None, "H", "D", "https://url"],
        ])
        assert self.lib.channel_ids_from_excel(content) == ["ch1"]


# ── Nextcloud integration ─────────────────────────────────────────────────────

def _assert_excel_accessible_and_valid(url: str) -> None:
    import requests
    resp = requests.get(url, timeout=15)
    assert resp.status_code == 200, f"HTTP {resp.status_code} fetching {url}"
    lib = _ensure_lib()
    tasks = lib.parse_excel(resp.content)
    assert len(tasks) > 0, "Excel has no data rows (expected data from row 4)"
    for task in tasks:
        assert task["wg_name"], f"wg_name empty in row: {task}"
        assert task["channel_id"], f"channel_id empty in row: {task}"
        assert task["heading"], f"heading empty in row: {task}"
        assert task["description"], f"description empty in row: {task}"
        assert task["docx_url"].startswith("http"), f"docx_url not a URL: {task['docx_url']}"


@pytest.mark.skipif(not INTEGRATION, reason="Set INTEGRATION_TESTS=1 to run")
def test_altbau_nextcloud_file_accessible_and_valid():
    _assert_excel_accessible_and_valid(_ALTBAU_URL)


@pytest.mark.skipif(not INTEGRATION, reason="Set INTEGRATION_TESTS=1 to run")
def test_neubau_nextcloud_file_accessible_and_valid():
    _assert_excel_accessible_and_valid(_NEUBAU_URL)