# Design: Migrate old bots into postbot task system

**Date:** 2026-04-28
**Status:** Approved

## Overview

Migrate the six standalone cron scripts in `old/` into the postbot task plugin system. Each old bot becomes a task file under `postbot/tasks/`. Shared utilities (Nextcloud fetching, PDF generation, text cleaning) are extracted into a new `postbot/lib/` module. The postbot's authenticated `driver` replaces the old username/password login.

## Background

The old bots are standalone Python scripts run via crontab on a separate server:

| Script | Schedule | What it does |
|---|---|---|
| `bot.py` | Mon 07:00 | Weekly maintenance tasks (Neubau) → WG `wg-briefkasten-<floor><num>` channels with PDF attachment |
| `bot_monthly.py` | 1st 08:00 | Monthly maintenance tasks (Neubau) → `WIR:Cluster <X>` channels with PDF attachment |
| `bot_altbau.py` | 1st 08:00 | Monthly maintenance tasks (Altbau) → per-unit channels (IDs from Nextcloud spreadsheet) with PDF attachment |
| `bot_nachweise.py` | ~12 specific dates/year | Tenancy reminder messages → all `wg-briefkasten-*` channels |
| `weberbot.py` | Daily 15:00 | General scheduler: reads Excel from Nextcloud, posts if today matches a date column |
| `engagementbot.py` | Daily 06:00 | Engagement check → hardcoded list of channels, only on 8 specific dates per year |

Common problems with the old approach:
- Username/password authentication hardcoded in every script
- `clean_the_string()` copy-pasted into every file
- No error handling — any failure aborts the entire script silently
- No test suite
- `bot_nachweise.py` requires a separate crontab entry per message variant

## Approach

**Option A (chosen):** Shared library module + daily date-check tasks.

Create `postbot/lib/` with shared utilities. Each bot becomes one task file. Multi-message bots (`nachweise`, `engagement`) become single daily tasks with an internal `(day, month) → message` table that exits silently if today doesn't match — consistent with the pattern already used by `engagementbot.py`.

This approach requires no changes to the task runner or scheduler format.

## Directory & file structure

```
postbot/
├── lib/
│   ├── __init__.py
│   ├── text_utils.py          # clean_text()
│   ├── nextcloud.py           # fetch_file()
│   └── pdf.py                 # docx_to_pdf()
├── tasks/
│   ├── example_task.py        (existing, unchanged)
│   ├── maintenance_weekly.py  # replaces bot.py
│   ├── maintenance_monthly.py # replaces bot_monthly.py
│   ├── maintenance_altbau.py  # replaces bot_altbau.py
│   ├── nachweise.py           # replaces bot_nachweise.py
│   ├── weberbot.py            # replaces weberbot.py
│   └── engagement.py          # replaces engagementbot.py
├── scheduler.toml             (6 new entries)
└── Containerfile              (add LibreOffice)
```

`lib/` is importable from task files as `from lib.text_utils import clean_text` etc. This works because `uv run main.py` is invoked from the `postbot/` directory, which Python adds to `sys.path`. The task runner loads task files via `importlib.util.spec_from_file_location` without changing the working directory, so `postbot/` remains on the path.

## Shared library (`postbot/lib/`)

### `text_utils.py`

```python
def clean_text(s: str) -> str
```

Replaces German umlauts with ASCII equivalents and escapes `"` and `\n` for safe embedding in Mattermost message strings. Replaces the copy-pasted `clean_the_string()` found in every old script.

### `nextcloud.py`

```python
def fetch_file(public_link: str, remote_path: str, local_path: str) -> None
```

Wraps `nextcloud_client.Client.from_public_link(public_link).get_file(remote_path, local_path)`. Raises on failure. No silent fallbacks.

### `pdf.py`

```python
def docx_to_pdf(docx_path: str, out_dir: str) -> str
```

Calls `soffice --headless --convert-to pdf --outdir <out_dir> <docx_path>` via subprocess. Returns the path to the generated `.pdf`. Raises `RuntimeError` if the subprocess exits non-zero or the output file is not produced. LibreOffice must be installed in the container (see Containerfile section).

## Task files

### `maintenance_weekly.py` (replaces `bot.py`)

- `DESCRIPTION`: "Weekly maintenance tasks (Neubau) → WG briefkasten channels with PDF"
- Fetches `Instandhaltungsplan_aktuell.xlsx` from Nextcloud via `lib/nextcloud.py`
- Computes rotation index: weeks elapsed since 2023-01-01 modulo number of tasks, 1-indexed
- Applies Schiebetüren special rule (two WGs per week, rotating)
- Posts markdown table summary to the overview channel
- Iterates per row: resolves `wg-briefkasten-<floor><num>` channel ID via `driver.channels.get_channel_by_name_and_team_name`, downloads matching `.docx` task card, converts to PDF, uploads file, posts message + file attachment
- Per-channel errors are caught individually; loop continues on failure, error logged

### `maintenance_monthly.py` (replaces `bot_monthly.py`)

- `DESCRIPTION`: "Monthly maintenance tasks (Neubau) → WIR:Cluster channels with PDF"
- Fetches same spreadsheet, computes monthly rotation: months elapsed since 2025-10-01 modulo number of tasks
- Applies circular shift of Cluster assignment column
- Posts summary to overview channel
- Iterates per row: resolves `WIR:Cluster <X>` channel by display name, downloads `.docx`, converts to PDF, posts with attachment

### `maintenance_altbau.py` (replaces `bot_altbau.py`)

- `DESCRIPTION`: "Monthly maintenance tasks (Altbau) → per-unit channels with PDF"
- Fetches `Altbau_Instandhaltungsplan_neu.xlsx` and `channels.xlsx` from Nextcloud
- Computes monthly rotation: months elapsed since 2023-01-01 modulo number of tasks, with offset
- `channels.xlsx` maps unit names → channel IDs (two ID columns, `ID1`/`ID2`, for dual-posting)
- Iterates per row × 2 ID columns: posts markdown table + PDF attachment to each channel ID
- Skips NaN channel IDs silently

### `nachweise.py` (replaces `bot_nachweise.py`)

- `DESCRIPTION`: "Tenancy reminders → all wg-briefkasten channels on scheduled dates"
- Contains an internal `dict[tuple[int, int], str]` mapping `(day, month)` → message text, covering all 10 existing message variants
- Checks `(today.day, today.month)` against the table; exits silently if no match
- Resolves all channels matching `wg-briefkasten` via `driver.channels` autocomplete
- Posts the matched message to each channel

### `weberbot.py` (replaces `weberbot.py`)

- `DESCRIPTION`: "General date-triggered scheduler: reads weberbots.xlsx from Nextcloud"
- Fetches `weberbots.xlsx` from Nextcloud
- Iterates rows: reads `Inhalt` (message text) and `channel-ID`, then walks date columns until NaN
- If any date column matches today, posts `clean_text(Inhalt)` to that channel ID

### `engagement.py` (replaces `engagementbot.py`)

- `DESCRIPTION`: "Engagement check → working group channels on 8 specific dates per year"
- Hardcoded list of 19 channel IDs and 8 allowed `(day, month)` dates
- Checks today; exits silently if no match
- Posts the engagement message to all channels, then adds two emoji reactions to each post

## Scheduler configuration

Add to `scheduler.toml`:

```toml
maintenance_weekly   = "0 7 * * 1"    # Monday 07:00
maintenance_monthly  = "0 8 1 * *"    # 1st of month 08:00
maintenance_altbau   = "0 8 1 * *"    # 1st of month 08:00
nachweise            = "0 6 * * *"    # daily 06:00
weberbot             = "0 15 * * *"   # daily 15:00
engagement           = "0 6 * * *"    # daily 06:00
```

## Containerfile changes

Add LibreOffice to the container image:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice && rm -rf /var/lib/apt/lists/*
```

`pyncclient` and `pandas` and `openpyxl` must also be added to `postbot/pyproject.toml` as dependencies (currently only present in `old/requirements.txt`).

## Error handling

- `lib/` functions raise on failure; callers do not suppress exceptions from `fetch_file` or `docx_to_pdf`
- The task runner catches unhandled exceptions, logs them, and posts to the configured log channel — no extra error handling boilerplate needed in task files
- Per-channel iteration errors in maintenance bots are caught at the loop level: one bad channel does not abort the rest of the run

## Testing

All tests go in `postbot/tests/`, following existing test conventions.

**`lib/` unit tests:**
- `test_text_utils.py` — parametrized tests for all umlaut replacements and escape cases
- `test_nextcloud.py` — mock `pyncclient.Client`, assert `get_file` called with correct args; assert exception raised on failure
- `test_pdf.py` — mock `subprocess.call`, assert correct `soffice` arguments; assert `RuntimeError` raised on non-zero exit or missing output file

**Task unit tests (mocked `driver`):**
- `test_maintenance_weekly.py` — mock `driver.channels`, `fetch_file`, `docx_to_pdf`, `driver.files`, `driver.posts`; verify correct channel resolved, correct file uploaded, correct message posted; verify loop continues on per-channel error
- `test_maintenance_monthly.py` — same pattern; additionally verify circular-shift rotation logic
- `test_maintenance_altbau.py` — verify dual-channel posting; verify NaN channel IDs skipped
- `test_nachweise.py` — parametrized over all 10 `(day, month)` entries: assert correct message posted; assert silent exit on non-matching date
- `test_weberbot.py` — verify post triggered on matching date; verify silence on non-matching date
- `test_engagement.py` — verify posts + reactions on allowed date; verify silence on non-allowed date

**Rotation math tests:**
- Dedicated parametrized tests for the `(elapsed // 7) % n_tasks + 1` (weekly) and `(months_elapsed % n_tasks) + 1` (monthly) formulas with known anchor dates and expected outputs
