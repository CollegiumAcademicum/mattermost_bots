# Postbot → mmbot_framework Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite postbot to use mmbot_framework for all infrastructure (WebSocket lifecycle, session management, logging, driver login) while preserving the broadcast-relay logic exactly.

**Architecture:** `PostBot(BaseBot)` subclass owns all broadcast logic as methods. `PostBotConfig(BotConfig)` extends the framework config with postbot-specific env vars. The `scripts/` package is dissolved; all files live flat at `postbot/`.

**Tech Stack:** Python 3.14, `uv`, `mmbot-framework` (local path dep), `mattermostdriver`, `pydantic` v2, `sqlite3`, `python-dotenv`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| **Modify** | `postbot/pyproject.toml` | Add `mmbot-framework` path dependency |
| **Create** | `postbot/config.py` | `PostBotConfig(BotConfig)` + `.env` loader |
| **Create** | `postbot/database.py` | SQLite broadcast log (replaces `scripts/database.py`) |
| **Create** | `postbot/patches.py` | SSL workaround (replaces `scripts/patches.py`) |
| **Create** | `postbot/bot.py` | `DMOnlyMiddleware` + `PostBot(BaseBot)` with all handlers |
| **Rewrite** | `postbot/main.py` | Thin entry point: load config, build bot, run |
| **Delete** | `postbot/scripts/` | Entire directory — all contents replaced by the above |

---

## Task 1: Add mmbot-framework dependency

**Files:**
- Modify: `postbot/pyproject.toml`

- [ ] **Step 1: Add the dependency and source**

Open `postbot/pyproject.toml`. Add `mmbot-framework` to `dependencies` and a `[tool.uv.sources]` section pointing at the sibling directory:

```toml
[project]
name = "mailman"
version = "0.1.0"
description = "The mailman bot is a simple Mattermost Bot used to relay messages to many groups easily"
readme = "README.md"
authors = [
    { name = "Philipp", email = "162928651+philipp-btz@users.noreply.github.com" }
]
requires-python = ">=3.12"
dependencies = [
    "anyio>=4.13.0",
    "dotenv>=0.9.9",
    "fastapi>=0.135.2",
    "mattermostdriver>=7.3.2",
    "mmbot-framework",
    "pydantic-core>=2.41.5",
    "pytest>=9.0.2",
    "python-dotenv>=1.2.2",
    "requests>=2.33.0",
    "starlette>=1.0.0",
    "ty>=0.0.24",
    "uvicorn>=0.42.0",
]

[tool.uv.sources]
mmbot-framework = { path = "../mmbot_framework" }

[project.scripts]
mailman-bot = "main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["."]

[tool.pytest.ini_options]
pythonpath = "."
testpaths = "tests"
```

- [ ] **Step 2: Sync the environment**

```bash
cd postbot
uv sync
```

Expected: resolves and installs `mmbot-framework` from the local path. No errors.

- [ ] **Step 3: Commit**

```bash
git add postbot/pyproject.toml
git commit -m "feat(postbot): add mmbot-framework dependency"
```

---

## Task 2: Create postbot/config.py

**Files:**
- Create: `postbot/config.py`

- [ ] **Step 1: Write the file**

```python
"""PostBotConfig — extends BotConfig with postbot-specific configuration.

All fields are loaded from a ``.env`` file via :meth:`PostBotConfig.load`.
The base :class:`mmbot_framework.BotConfig` fields (``url``, ``token``,
``team_name``, etc.) are documented there.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from mmbot_framework import BotConfig, ConfigError
from pydantic import field_validator


class PostBotConfig(BotConfig):
    """Configuration for the postbot broadcast relay bot.

    Extends :class:`mmbot_framework.BotConfig` with postbot-specific fields.
    All fields can be set via environment variables (or a ``.env`` file).

    Additional attributes:
        bot_log_channel_id: Mattermost channel ID for audit posts after each
            broadcast. Empty string disables audit logging.
        channels_json_path: Path to ``channels.json`` which defines channel
            groups and the broadcast whitelist.
        db_path: Path to the SQLite database used to log broadcasts.
        console_log_level: Log level for console (stderr) output. Independent
            of the file log level set by :attr:`~BotConfig.log_level`.
    """

    bot_log_channel_id: str = ""
    channels_json_path: Path = Path("channels.json")
    db_path: Path = Path("broadcast_log.db")
    console_log_level: str = "WARNING"

    @field_validator("console_log_level")
    @classmethod
    def _validate_console_log_level(cls, value: str) -> str:
        """Ensure ``console_log_level`` is a recognised Python log level name."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in valid:
            raise ValueError(
                f"console_log_level must be one of {sorted(valid)}, got {value!r}"
            )
        return upper

    @classmethod
    def load(cls, path: str | Path = ".env") -> "PostBotConfig":
        """Load configuration from a ``.env`` file.

        All keys are lowercased before validation so environment variable
        names are case-insensitive (e.g. ``BOT_TOKEN`` and ``bot_token``
        are equivalent).

        Args:
            path: Path to the ``.env`` file. Defaults to ``".env"`` in the
                current working directory.

        Returns:
            A validated :class:`PostBotConfig` instance.

        Raises:
            ConfigError: If the file does not exist or required fields are
                missing or invalid.
        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {p}")
        raw = dict(dotenv_values(p))
        normalised = {k.lower(): v for k, v in raw.items()}
        try:
            return cls(**normalised)
        except Exception as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc
```

- [ ] **Step 2: Verify the import resolves**

```bash
cd postbot
uv run python -c "from config import PostBotConfig; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add postbot/config.py
git commit -m "feat(postbot): add PostBotConfig extending BotConfig"
```

---

## Task 3: Create postbot/database.py

The original `scripts/database.py` imported `DB_PATH` from `scripts.config` at module load time. The new version accepts `db_path` as a parameter to `initialize_database()` and stores it in a module-level variable so all other functions can use it without needing the config imported.

**Files:**
- Create: `postbot/database.py`

- [ ] **Step 1: Write the file**

```python
"""Broadcast log — SQLite persistence for sent broadcasts.

Call :func:`initialize_database` once at startup (passing the DB path from
config) before calling any other function in this module.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Thread-local storage ensures each thread gets its own connection.
_db_local = threading.local()

# Set by initialize_database(); all functions below rely on this being set.
_db_path: Path | None = None


def initialize_database(db_path: Path) -> None:
    """Create (or migrate) the ``broadcasts`` table and set the DB path.

    Safe to call multiple times — ``CREATE TABLE IF NOT EXISTS`` and the
    ``ALTER TABLE`` migration are idempotent.

    The function also installs a SQLite trigger that keeps the table under
    100 000 rows by automatically deleting the oldest rows after each insert.

    Args:
        db_path: Filesystem path to the SQLite database file. Created if it
            does not exist.
    """
    global _db_path
    _db_path = db_path

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA auto_vacuum = FULL;")
        cursor.execute("VACUUM;")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP,
                sender_name      TEXT NOT NULL,
                message_content  TEXT NOT NULL,
                target_channels  TEXT NOT NULL,
                file_ids         TEXT
            )
        """)

        # Housekeeping trigger: keep the table under 100 000 rows.
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_row_limit
            AFTER INSERT ON broadcasts
            BEGIN
                DELETE FROM broadcasts WHERE id <= (NEW.id - 100000);
            END;
        """)

        # Backward-compatibility migration: add file_ids column if absent.
        cursor.execute("PRAGMA table_info(broadcasts)")
        columns = [row[1] for row in cursor.fetchall()]
        if "file_ids" not in columns:
            logger.info("Migrating database: adding 'file_ids' column.")
            cursor.execute("ALTER TABLE broadcasts ADD COLUMN file_ids TEXT")

        conn.commit()
        logger.info(f"Database initialised at {_db_path}.")
    except sqlite3.Error as exc:
        logger.error(f"Database initialisation error: {exc}")


def log_broadcast(
    sender_name: str,
    message_content: str,
    target_channels: list[str],
    file_ids: list[str] | None = None,
) -> None:
    """Persist a successful broadcast to the database.

    Args:
        sender_name: Mattermost username of the sender.
        message_content: The message body that was broadcast.
        target_channels: Display names of channels the message was sent to.
        file_ids: Mattermost file IDs of attachments that were relayed.
            ``None`` or empty list if no files were attached.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO broadcasts (sender_name, message_content, target_channels, file_ids)"
            " VALUES (?, ?, ?, ?)",
            (
                sender_name,
                message_content,
                json.dumps(target_channels),
                json.dumps(file_ids) if file_ids else None,
            ),
        )
        conn.commit()
        logger.info(f"Logged broadcast from {sender_name!r} to database.")
    except sqlite3.Error as exc:
        logger.error(f"Failed to log broadcast: {exc}")


def close_db_connection() -> None:
    """Close the database connection for the current thread.

    Called from :meth:`PostBot.on_stop` during bot shutdown.
    Safe to call even if no connection has been opened.
    """
    conn = getattr(_db_local, "conn", None)
    if conn is not None:
        conn.close()
        _db_local.conn = None
        logger.debug("Database connection closed.")


# ── Internal ──────────────────────────────────────────────────────────────────


def _get_connection() -> sqlite3.Connection:
    """Return the thread-local database connection, opening it if needed.

    Returns:
        An open :class:`sqlite3.Connection`.

    Raises:
        RuntimeError: If :func:`initialize_database` has not been called yet.
    """
    if _db_path is None:
        raise RuntimeError(
            "Database not initialised. Call initialize_database() before use."
        )
    if not hasattr(_db_local, "conn") or _db_local.conn is None:
        logger.debug(f"Opening new database connection to {_db_path}.")
        _db_local.conn = sqlite3.connect(str(_db_path), check_same_thread=False)
    return _db_local.conn
```

- [ ] **Step 2: Verify the import resolves**

```bash
cd postbot
uv run python -c "from database import initialize_database, log_broadcast, close_db_connection; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add postbot/database.py
git commit -m "feat(postbot): add database.py (flat relocation, path-param interface)"
```

---

## Task 4: Create postbot/patches.py

This file is identical in content to `scripts/patches.py` — it is simply relocated. No logic changes.

**Files:**
- Create: `postbot/patches.py`

- [ ] **Step 1: Write the file**

```python
"""SSL patch for mattermostdriver.

``mattermostdriver`` calls ``ssl.create_default_context()`` without the
``purpose`` keyword argument on Python 3.10+, which triggers a deprecation
warning and may fail in strict environments.  This module monkey-patches the
standard library function to always pass ``purpose=ssl.Purpose.SERVER_AUTH``.

Call :func:`apply_ssl_patch` once, early in the startup sequence (before the
driver connects), to activate the patch for the lifetime of the process.
"""

from __future__ import annotations

import logging
import ssl

logger = logging.getLogger(__name__)


def apply_ssl_patch() -> None:
    """Monkey-patch ``ssl.create_default_context`` to force ``SERVER_AUTH``.

    Intercepts every call to the standard library function and injects
    ``purpose=ssl.Purpose.SERVER_AUTH`` into the keyword arguments.  The
    original function is still called — only the missing argument is supplied.
    """
    original = ssl.create_default_context

    def _patched(*args, **kwargs):
        logger.debug("SSL patch: forcing purpose=SERVER_AUTH.")
        kwargs["purpose"] = ssl.Purpose.SERVER_AUTH
        return original(*args, **kwargs)

    ssl.create_default_context = _patched
    logger.info("Applied SSL patch for mattermostdriver.")
```

- [ ] **Step 2: Commit**

```bash
git add postbot/patches.py
git commit -m "feat(postbot): add patches.py (flat relocation)"
```

---

## Task 5: Create postbot/bot.py

This is the main migration task. `PostBot(BaseBot)` contains `DMOnlyMiddleware`, all command handlers, the broadcast wizard, and the helper methods that replace `scripts/handlers.py`, `scripts/mattermost.py`, and `scripts/state.py`.

**Files:**
- Create: `postbot/bot.py`

- [ ] **Step 1: Write the file**

```python
"""PostBot — broadcast relay bot built on mmbot_framework.

Usage::

    from config import PostBotConfig
    from bot import PostBot, DMOnlyMiddleware
    from mmbot_framework import IgnoreSelfMiddleware

    config = PostBotConfig.load(".env")
    bot = PostBot(config)
    bot.add_middleware(IgnoreSelfMiddleware(bot))
    bot.add_middleware(DMOnlyMiddleware())
    bot.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Callable

from mmbot_framework import BaseBot, ParsedMessage

from config import PostBotConfig
from database import close_db_connection, initialize_database, log_broadcast
from patches import apply_ssl_patch

logger = logging.getLogger(__name__)


# ── Middleware ────────────────────────────────────────────────────────────────


class DMOnlyMiddleware:
    """Drop any message that did not arrive in a direct-message channel.

    Postbot only acts on DMs (``channel_type == "D"``).  Messages from public
    channels, private groups, or any other channel type are silently discarded
    here so that none of the command handlers ever see them.

    Example::

        bot.add_middleware(DMOnlyMiddleware())
    """

    async def __call__(self, msg: ParsedMessage, call_next: Callable) -> None:
        """Pass DMs down the pipeline; drop everything else.

        Args:
            msg: The parsed incoming message.
            call_next: Coroutine that continues the middleware chain.
        """
        if msg.channel_type != "D":
            logger.debug(
                f"DMOnlyMiddleware: dropping message from non-DM channel {msg.channel_id!r}."
            )
            return
        await call_next(msg)


# ── Help text ─────────────────────────────────────────────────────────────────

_HELP_MESSAGE = (
    "### Usage\n"
    "**DM me with the message you want delivered — I'll guide you through the process.**\n\n"
    "**Other commands:**\n"
    "- `!id <channel>` — return the channel ID for `<channel>` "
    "(use the system name, not the display name)\n"
    "- `!channels` — list all channels the bot has access to\n"
    "- `!get_groups` — list all available groups and their channels\n"
    "- `!get_private_groups` — same as above but for private groups\n"
    '- `!add_group <json>` — add public group(s): `{"GroupName": ["id1", "id2"]}`\n'
    "- `!add_private_group <json>` — add private group(s): same JSON format"
)


# ── Bot ───────────────────────────────────────────────────────────────────────


class PostBot(BaseBot):
    """Broadcast relay bot that lets authorised users send messages to many channels.

    Users interact exclusively via DM.  The bot guides them through a two-step
    wizard: composing a message, selecting target channels or groups, and
    confirming before the broadcast is sent.

    Infrastructure (WebSocket lifecycle, session management, driver login,
    logging) is inherited from :class:`mmbot_framework.BaseBot`.

    Attributes:
        config: The validated :class:`PostBotConfig` for this instance.
    """

    def __init__(self, config: PostBotConfig) -> None:
        """Initialise the bot and register all command triggers.

        Args:
            config: Validated postbot configuration.
        """
        super().__init__(config)
        self.config: PostBotConfig  # narrow the type hint for type-checkers

        # State populated at startup via on_start().
        self._team_id: str = ""
        self._bot_username: str = ""

        # In-memory set of users who have received the welcome message.
        # Resets on bot restart — this matches the original behaviour.
        self._known_users: set[str] = set()

        # Channel groups and whitelist loaded from channels.json at startup
        # and mutated in-place by !add_group / !add_private_group.
        self._visible_groups: dict[str, list[str]] = {}
        self._private_groups: dict[str, list[str]] = {}
        self._whitelist: set[str] = set()

        # Register all command triggers.  The @command decorator supports only
        # one trigger per method, so we use _dispatcher.register() directly.
        for trigger in ("help", "!help", "--help", "man"):
            self._dispatcher.register(trigger, self._handle_help)

        self._dispatcher.register("!id", self._handle_id)
        self._dispatcher.register("!channels", self._handle_channels)
        # Register !get_private_groups before !get_groups so the longer prefix
        # is checked first (the dispatcher matches on startswith, first wins).
        self._dispatcher.register("!get_private_groups", self._handle_get_private_groups)
        self._dispatcher.register("!get_groups", self._handle_get_groups)
        # Same ordering rationale for !add_private_group vs !add_group.
        self._dispatcher.register("!add_private_group", self._handle_add_private_group)
        self._dispatcher.register("!add_group", self._handle_add_group)

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    async def on_start(self) -> None:
        """Run setup tasks after driver login, before the WebSocket opens.

        Steps:
        1. Apply the SSL patch required by the installed mattermostdriver version.
        2. Initialise the SQLite broadcast-log database.
        3. Fetch the bot's Mattermost team ID and username.
        4. Load channel group definitions from ``channels.json``.
        """
        apply_ssl_patch()
        initialize_database(self.config.db_path)

        me = self.driver.users.get_user("me")
        self._bot_username = me["username"]

        try:
            team = self.driver.teams.get_team_by_name(self.config.team_name)
            self._team_id = team["id"]
            logger.info(
                f"Bot connected as @{self._bot_username} "
                f"(team_id={self._team_id!r})."
            )
        except Exception as exc:
            logger.critical(
                f"Could not find team {self.config.team_name!r}. "
                f"Check TEAM_NAME in your .env file. Details: {exc}"
            )
            raise

        self._load_channel_data()

    async def on_stop(self) -> None:
        """Close the SQLite connection on shutdown."""
        close_db_connection()
        logger.info("Database connection closed.")

    # ── Session cleanup with expiry notifications ─────────────────────────────

    async def _session_cleanup_loop(self) -> None:
        """Background task: notify users of expired sessions, then purge them.

        Overrides :meth:`~mmbot_framework.BaseBot._session_cleanup_loop` to
        send a DM to each user whose session has expired before the session is
        removed.  The base-class implementation silently purges without
        notifying the user.

        Session data must contain ``"dm_channel_id"`` for a notification to be
        sent; sessions without it are still purged but not notified.
        """
        interval = self.config.session_cleanup_interval_seconds
        while True:
            await asyncio.sleep(interval)
            logger.debug("Running session expiry check.")

            # Collect sessions that have expired and have a DM channel to
            # notify.  We iterate a snapshot (list) to avoid mutating the dict
            # during iteration.
            expired = [
                s
                for s in list(self.sessions._sessions.values())
                if s.is_expired() and "dm_channel_id" in s.data
            ]

            for session in expired:
                try:
                    self._post(
                        session.data["dm_channel_id"],
                        "⏱️ **Session expired.** You took too long to confirm. "
                        "Send a new message to start over.",
                    )
                    logger.info(
                        f"Sent expiry notice to user {session.sender_id!r}."
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to send expiry notice to user "
                        f"{session.sender_id!r}: {exc}"
                    )

            removed = self.sessions.purge_expired()
            if removed:
                logger.info(
                    f"Session cleanup: removed {removed} expired session(s)."
                )

    # ── Broadcast wizard (on_message fallback) ────────────────────────────────

    async def on_message(self, msg: ParsedMessage) -> None:
        """Handle DMs that did not match any registered command.

        Implements the broadcast wizard state machine:

        - **New user** (first DM ever): show welcome message, wait for content.
        - **No active session**: user sends content — capture it, ask for targets.
        - **AWAITING_CHANNELS**: user specifies targets — validate and preview.
        - **CONFIRMATION**: user replies ``yes`` / ``no`` — relay or cancel.

        Args:
            msg: The unmatched parsed message (always a DM due to middleware).
        """
        sender_id = msg.sender_id

        if sender_id not in self._known_users:
            logger.info(f"New user: @{msg.sender_name} ({sender_id}).")
            await self._handle_new_user(msg)
            return

        session = self.sessions.get(sender_id)

        if session is None:
            logger.info(f"Starting new broadcast session for @{msg.sender_name}.")
            await self._handle_new_session(msg)
            return

        state = session.data.get("state")

        if state == "AWAITING_CHANNELS":
            logger.info(f"Handling channel selection for @{msg.sender_name}.")
            await self._handle_channel_selection(session, msg)
        elif state == "CONFIRMATION":
            logger.info(f"Handling broadcast confirmation for @{msg.sender_name}.")
            await self._handle_confirmation(session, msg)
        else:
            logger.warning(
                f"User @{msg.sender_name} is in unknown session state {state!r}."
            )

    # ── Command handlers ──────────────────────────────────────────────────────

    async def _handle_help(self, msg: ParsedMessage) -> None:
        """Respond with the usage help text.

        Triggered by: ``!help``, ``help``, ``--help``, ``man``.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested help.")
        self._post(msg.channel_id, _HELP_MESSAGE)

    async def _handle_id(self, msg: ParsedMessage) -> None:
        """Look up and return the Mattermost channel ID for a given channel name.

        Usage: ``!id <channel-name>``

        The channel name must be the *system* name (e.g. ``town-square``), not
        the display name (e.g. ``Town Square``).

        Args:
            msg: The incoming message.  The channel name is the text after the
                ``!id`` prefix.
        """
        channel_name = msg.text[len("!id"):].strip()
        if not channel_name:
            logger.warning(
                f"User @{msg.sender_name} used !id without a channel name."
            )
            self._post(
                msg.channel_id,
                "Please provide a channel name after `!id`, "
                "e.g. `!id town-square`.",
            )
            return

        logger.info(
            f"User @{msg.sender_name} requested ID for channel {channel_name!r}."
        )
        try:
            channel = self.driver.channels.get_channel_by_name(
                self._team_id, channel_name
            )
            self._post(
                msg.channel_id,
                f"The ID for channel `{channel_name}` is: `{channel['id']}`",
            )
        except Exception as exc:
            logger.error(f"Could not find channel {channel_name!r}: {exc}")
            self._post(
                msg.channel_id,
                f"⚠️ Could not find a channel named `{channel_name}`.",
            )

    async def _handle_channels(self, msg: ParsedMessage) -> None:
        """List all Mattermost channels the bot has access to.

        Outputs a Markdown table with display name, system name, channel ID,
        and team name for every channel across all teams the bot belongs to.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested the channel list.")
        lines = [
            "| display_name | name | ID | team_name |",
            "| :--- | :--- | :--- | :--- |",
        ]
        try:
            teams = self.driver.teams.get_user_teams("me")
            for team in teams:
                channels = self.driver.channels.get_channels_for_user(
                    "me", team["id"]
                )
                for channel in channels:
                    if channel["team_id"]:
                        team_name = self.driver.teams.get_team(
                            channel["team_id"]
                        ).get("display_name", "N/A")
                        lines.append(
                            f"| `{channel['display_name']}` | {channel['name']} "
                            f"| `{channel['id']}` | {team_name} |"
                        )
        except Exception as exc:
            logger.error(f"Error fetching channels: {exc}")
            lines.append("Error fetching channels.")

        self._post(msg.channel_id, "\n".join(lines))

    async def _handle_get_groups(self, msg: ParsedMessage) -> None:
        """List all visible channel groups and their resolved channel names.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested visible groups.")
        lines: list[str] = []
        for name, channel_ids in self._visible_groups.items():
            try:
                resolved = [
                    self.driver.channels.get_channel(cid)["name"]
                    for cid in channel_ids
                ]
                lines.append(f"**{name}:** {resolved}\n")
            except Exception as exc:
                logger.error(
                    f"Error resolving channels for group {name!r}: {exc}"
                )
                lines.append(f"**{name}:** [error fetching channel names]\n")
        self._post(
            msg.channel_id,
            "\n".join(lines) if lines else "No groups configured.",
        )

    async def _handle_get_private_groups(self, msg: ParsedMessage) -> None:
        """List all private channel groups and their resolved channel names.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested private groups.")
        lines: list[str] = []
        for name, channel_ids in self._private_groups.items():
            try:
                resolved = [
                    self.driver.channels.get_channel(cid)["name"]
                    for cid in channel_ids
                ]
                lines.append(f"**{name}:** {resolved}\n")
            except Exception as exc:
                logger.error(
                    f"Error resolving channels for private group {name!r}: {exc}"
                )
                lines.append(f"**{name}:** [error fetching channel names]\n")
        self._post(
            msg.channel_id,
            "\n".join(lines) if lines else "No private groups configured.",
        )

    async def _handle_add_group(self, msg: ParsedMessage) -> None:
        """Add one or more public channel groups from a JSON payload.

        Usage: ``!add_group {"GroupName": ["channel_id_1", "channel_id_2"]}``

        Invalid channel IDs are removed silently.  Groups where every ID is
        invalid are not added.  Valid groups are persisted to ``channels.json``
        and the in-memory state is updated immediately.

        Args:
            msg: The incoming message.
        """
        await self._add_group_impl(msg, private=False)

    async def _handle_add_private_group(self, msg: ParsedMessage) -> None:
        """Add one or more private channel groups from a JSON payload.

        Usage: ``!add_private_group {"GroupName": ["channel_id_1", "channel_id_2"]}``

        Private groups are only visible via ``!get_private_groups``, not
        ``!get_groups``.

        Args:
            msg: The incoming message.
        """
        await self._add_group_impl(msg, private=True)

    # ── Broadcast wizard helpers ──────────────────────────────────────────────

    async def _handle_new_user(self, msg: ParsedMessage) -> None:
        """Send the welcome message to a first-time user and register them.

        After the welcome, the user must send their broadcast content in a
        subsequent message before a session is created.

        Args:
            msg: The message that identified this user as new.
        """
        self._known_users.add(msg.sender_id)
        self._post(
            msg.channel_id,
            "👋 **Welcome, I'm the Postbot**\n\n"
            "To send a broadcast, just send me the message you want to share "
            "(you can attach files too!). I'll then ask you to specify the "
            "target channels or groups.\n\n"
            "Your message will *not* be sent until you confirm.\n\n"
            "**TYPE YOUR MESSAGE AND/OR ATTACH FILES NOW:**",
        )

    async def _handle_new_session(self, msg: ParsedMessage) -> None:
        """Capture the user's broadcast content and ask for target channels.

        Creates a new session in the ``AWAITING_CHANNELS`` state.

        Args:
            msg: The message containing the broadcast content and optional files.
        """
        session = self.sessions.get_or_create(msg.sender_id)
        session.data.update(
            {
                "state": "AWAITING_CHANNELS",
                "message": msg.text,
                "file_ids": msg.file_ids,
                "dm_channel_id": msg.channel_id,
            }
        )

        # Build the displayed list of whitelisted channels.
        allowed_channels: list[str] = []
        for channel_id in self._whitelist:
            try:
                info = self.driver.channels.get_channel(channel_id)
                team_name = (
                    self.driver.teams.get_team(info["team_id"]).get(
                        "display_name", "N/A"
                    )
                    if info["team_id"]
                    else "N/A"
                )
                allowed_channels.append(
                    f"- name: `{info['name']}`    "
                    f"(display name: `{info['display_name']}` — "
                    f"ID: `{channel_id}` — team: `{team_name}`)"
                )
            except Exception as exc:
                logger.error(
                    f"Error fetching info for channel {channel_id!r}: {exc}"
                )
                allowed_channels.append(f"- `(ID not found)` (`{channel_id}`)")

        allowed_channels.sort()
        group_list = "".join(f"- `{g}`\n" for g in self._visible_groups)
        file_notice = (
            f"\n_You have attached {len(msg.file_ids)} file(s)._"
            if msg.file_ids
            else ""
        )

        self._post(
            msg.channel_id,
            f"I've captured your message.{file_notice}\n\n"
            f"Reply with the **channel names** or **groups** you want to send "
            f"it to, separated by commas.\n\n"
            f"### Available Groups:\n{group_list}"
            f"**Available Channels:**\n"
            + "\n".join(allowed_channels),
        )

    async def _handle_channel_selection(self, session, msg: ParsedMessage) -> None:
        """Validate the user's target selection and show a confirmation preview.

        Updates the session state to ``CONFIRMATION`` on success.  If no valid
        channels are found the user is asked to try again (session is NOT
        cleared).

        Args:
            session: The active :class:`~mmbot_framework.Session` for this user.
            msg: The message containing the comma-separated channel/group targets.
        """
        requested = [item.strip() for item in msg.text.split(",")]
        valid_ids, valid_names, invalid_names = self._resolve_targets(requested)

        if not valid_ids:
            logger.warning(
                f"No valid channels found for input from @{msg.sender_name}."
            )
            self._post(
                msg.channel_id,
                "⚠️ No valid channels found. Please try again.",
            )
            return

        session.data.update(
            {
                "target_ids": valid_ids,
                "valid_names": valid_names,
                "state": "CONFIRMATION",
            }
        )

        file_notice = (
            f"\n**Files attached:** {len(session.data['file_ids'])}"
            if session.data.get("file_ids")
            else ""
        )
        warning = (
            f"\n⚠️ *Ignored invalid inputs: {', '.join(invalid_names)}*"
            if invalid_names
            else ""
        )
        self._post(
            msg.channel_id,
            f"**Preview:**\n{session.data['message']}\n\n"
            f"**Targets:**\n"
            + "\n".join(valid_names)
            + file_notice
            + warning
            + "\n\nReply with **yes** to send or **no** to cancel.",
        )

    async def _handle_confirmation(self, session, msg: ParsedMessage) -> None:
        """Handle the user's final yes/no confirmation.

        - ``yes``: relay message and files to all target channels, log to DB,
          post audit entry (if configured), clear session.
        - ``no``: cancel and clear session.
        - anything else: ask again without clearing the session.

        Args:
            session: The active :class:`~mmbot_framework.Session` for this user.
            msg: The confirmation message.
        """
        text_lower = msg.text.lower()

        if text_lower == "yes":
            await self._send_broadcast(session, msg)
        elif text_lower == "no":
            logger.info(f"User @{msg.sender_name} cancelled broadcast.")
            self._post(msg.channel_id, "❌ **Broadcast cancelled.**")
        else:
            logger.warning(
                f"Invalid confirmation from @{msg.sender_name}: {msg.text!r}."
            )
            self._post(
                msg.channel_id,
                "Invalid response. Please reply with **yes** or **no**.",
            )
            return  # Keep the session alive — the user can still confirm.

        self.sessions.clear(msg.sender_id)
        logger.info(f"Session for @{msg.sender_name} cleared.")

    async def _send_broadcast(self, session, msg: ParsedMessage) -> None:
        """Relay the broadcast message and files to all selected target channels.

        For each target channel:

        1. Download every attached file from Mattermost (once).
        2. Re-upload each file to the target channel.
        3. Post the broadcast message with the re-uploaded file IDs.

        After all channels are posted, persists the broadcast to SQLite and
        optionally posts an audit entry to the configured log channel.

        Args:
            session: The confirmed :class:`~mmbot_framework.Session`.
            msg: The ``yes`` confirmation message (provides sender metadata).
        """
        logger.info(f"User @{msg.sender_name} confirmed broadcast.")
        broadcast_text = (
            f"📢 **Message from @{msg.sender_name}**\n\n\n"
            f"{session.data['message']}"
            f"\n\n\n\n*--- END of Message ---*\n"
            f"*To use my services (@{self._bot_username}) just DM me*"
        )

        # Download all attached files once (they'll be re-uploaded per channel).
        files: dict[str, bytes] = {}
        for file_id in session.data.get("file_ids", []):
            try:
                response = self.driver.files.get_file(file_id)
                metadata = self.driver.files.get_file_metadata(file_id)
                filename = metadata.get("name", "relayed_file.dat")
                # get_file() returns a dict for JSON files, a Response otherwise.
                files[filename] = (
                    json.dumps(response).encode("utf-8")
                    if isinstance(response, dict)
                    else response.content
                )
            except Exception as exc:
                logger.error(f"Failed to fetch file {file_id!r}: {exc}")

        # Post to each target channel; re-upload files per channel.
        all_uploaded_ids: list[str] = []
        for channel_id in session.data["target_ids"]:
            channel_file_ids: list[str] = []
            for filename, content in files.items():
                try:
                    info = self.driver.files.upload_file(
                        channel_id=channel_id,
                        files={"files": (filename, content)},
                    )
                    channel_file_ids.append(info["file_infos"][0]["id"])
                except Exception as exc:
                    logger.error(
                        f"Failed to upload {filename!r} to channel "
                        f"{channel_id!r}: {exc}"
                    )
            all_uploaded_ids.extend(channel_file_ids)

            try:
                self.driver.posts.create_post(
                    {
                        "channel_id": channel_id,
                        "message": broadcast_text,
                        "file_ids": channel_file_ids,
                    }
                )
                logger.info(f"Posted broadcast to channel {channel_id!r}.")
            except Exception as exc:
                logger.error(
                    f"Failed to post to channel {channel_id!r}: {exc}"
                )

        # Persist to the SQLite broadcast log.
        log_broadcast(
            sender_name=msg.sender_name,
            message_content=session.data["message"],
            target_channels=session.data["valid_names"],
            file_ids=all_uploaded_ids,
        )

        # Optional audit post to the configured log channel.
        if self.config.bot_log_channel_id:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            self._post(
                self.config.bot_log_channel_id,
                f"Sender *{msg.sender_name}* sent a broadcast. "
                f"Timestamp (UTC): {timestamp}. "
                f"Target channel count: {len(session.data['valid_names'])}. "
                f"Attached file count: {len(all_uploaded_ids)}.",
            )

        self._post(
            msg.channel_id,
            "✅ **Broadcast sent successfully.**\n\n"
            "Thank you for using the Broadcast Bot!\n\n\n"
            "**If you want to send another broadcast, SEND THE MESSAGE "
            "AND/OR ATTACH FILES NOW:**\n"
            "If not, just do nothing :feuervoigl:",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _post(self, channel_id: str, text: str) -> None:
        """Post a plain-text / Markdown message to a Mattermost channel.

        Thin wrapper over ``self.driver.posts.create_post`` that avoids
        repeating the dict-construction boilerplate throughout the handlers.

        Args:
            channel_id: The Mattermost channel ID to post to.
            text: The message body.  Mattermost renders Markdown.
        """
        self.driver.posts.create_post({"channel_id": channel_id, "message": text})

    def _resolve_targets(
        self, inputs: list[str]
    ) -> tuple[list[str], list[str], list[str]]:
        """Resolve user-supplied channel names, IDs, and group names to channel IDs.

        Each input is processed as follows:

        1. If it exactly matches a known group name (visible or private), the
           group's channel IDs are added directly.
        2. Otherwise it is treated as a channel name and resolved to an ID via
           the Mattermost API.  If the API call fails it is assumed to already
           be an ID.
        3. Any resolved ID **not** in :attr:`_whitelist` is rejected.

        Args:
            inputs: Raw user inputs, typically split on commas.

        Returns:
            A three-tuple of:

            - ``valid_ids``: Whitelisted channel IDs to broadcast to.
            - ``valid_names``: Display names corresponding to ``valid_ids``.
            - ``invalid_names``: Inputs that could not be resolved or are not
              whitelisted.
        """
        all_groups: dict[str, list[str]] = {
            **self._visible_groups,
            **self._private_groups,
        }
        valid_ids: set[str] = set()
        invalid_inputs: set[str] = set()

        for item in inputs:
            stripped = item.strip()
            if stripped in all_groups:
                valid_ids.update(all_groups[stripped])
                logger.debug(
                    f"Resolved group {stripped!r} to {all_groups[stripped]}."
                )
            else:
                clean = stripped.lower().lstrip("#")
                try:
                    channel = self.driver.channels.get_channel_by_name(
                        self._team_id, clean
                    )
                    channel_id = channel["id"]
                except Exception:
                    channel_id = clean
                    logger.debug(
                        f"Could not resolve {clean!r} as a channel name; "
                        f"treating as raw ID."
                    )

                if channel_id in self._whitelist:
                    valid_ids.add(channel_id)
                else:
                    invalid_inputs.add(stripped)
                    logger.warning(
                        f"Channel {stripped!r} (resolved to {channel_id!r}) "
                        f"is not in the whitelist."
                    )

        valid_names: list[str] = []
        for cid in valid_ids:
            try:
                valid_names.append(
                    self.driver.channels.get_channel(cid)["display_name"]
                )
            except Exception:
                valid_names.append(cid)
                logger.warning(
                    f"Could not get display name for channel {cid!r}."
                )

        return list(valid_ids), valid_names, list(invalid_inputs)

    def _load_channel_data(self) -> None:
        """Read ``channels.json`` and populate in-memory group and whitelist data.

        Called at startup via :meth:`on_start` and after any successful
        ``!add_group`` or ``!add_private_group`` mutation.

        Raises:
            FileNotFoundError: If :attr:`~PostBotConfig.channels_json_path`
                does not exist.
            json.JSONDecodeError: If the file contains invalid JSON.
        """
        path: Path = self.config.channels_json_path
        logger.info(f"Loading channel data from {path}.")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._visible_groups = data.get("groups", {})
        self._private_groups = data.get("private_groups", {})
        self._whitelist = set(data.get("whitelist", []))
        logger.debug(
            f"Loaded {len(self._visible_groups)} visible groups, "
            f"{len(self._private_groups)} private groups, "
            f"{len(self._whitelist)} whitelist entries."
        )

    async def _add_group_impl(self, msg: ParsedMessage, *, private: bool) -> None:
        """Shared implementation for !add_group and !add_private_group.

        Parses the JSON payload from the message text, validates each channel
        ID against the Mattermost API, removes invalid IDs, and persists the
        cleaned result to ``channels.json``.  The in-memory state is updated
        immediately on success.

        Args:
            msg: The incoming message whose text contains the JSON payload
                after the command trigger.
            private: If ``True``, the group is written to ``private_groups``;
                otherwise to ``groups``.
        """
        trigger = "!add_private_group" if private else "!add_group"
        json_key = "private_groups" if private else "groups"
        target_dict = self._private_groups if private else self._visible_groups

        payload_str = msg.text[len(trigger):].strip()
        if not payload_str:
            self._post(
                msg.channel_id,
                f"❌ Please provide a JSON payload. "
                f'Example: `{trigger} {{"NewGroup": ["id1", "id2"]}}`',
            )
            return

        try:
            new_groups: dict = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in {trigger} command: {exc}")
            self._post(
                msg.channel_id,
                "❌ Invalid JSON format. Please check your syntax.",
            )
            return

        if not isinstance(new_groups, dict):
            self._post(
                msg.channel_id,
                "❌ Input must be a JSON object (dictionary).",
            )
            return

        # Validate each channel ID; drop those that don't exist in Mattermost.
        cleaned: dict[str, list[str]] = {}
        for group_name, channel_ids in new_groups.items():
            valid: list[str] = []
            for channel_id in channel_ids:
                try:
                    self.driver.channels.get_channel(channel_id)
                    valid.append(channel_id)
                except Exception:
                    logger.warning(
                        f"Removed invalid channel ID {channel_id!r} "
                        f"from group {group_name!r}."
                    )
            if valid:
                cleaned[group_name] = valid
            else:
                logger.warning(
                    f"Group {group_name!r} had no valid channels; skipped."
                )

        if not cleaned:
            self._post(
                msg.channel_id,
                "❌ No valid groups to add. "
                "Check your JSON syntax and channel IDs.",
            )
            return

        # Update in-memory state.
        target_dict.update(cleaned)

        # Persist to channels.json.
        path: Path = self.config.channels_json_path
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data[json_key] = target_dict
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4)

        logger.info(
            f"Persisted new groups to {path}: {list(cleaned.keys())}."
        )
        self._post(msg.channel_id, "✅ Group added successfully!")
```

- [ ] **Step 2: Verify the import resolves**

```bash
cd postbot
uv run python -c "from bot import PostBot, DMOnlyMiddleware; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add postbot/bot.py
git commit -m "feat(postbot): add PostBot and DMOnlyMiddleware"
```

---

## Task 6: Rewrite postbot/main.py

**Files:**
- Modify: `postbot/main.py`

- [ ] **Step 1: Replace the file contents**

```python
"""Entry point for the postbot broadcast relay bot.

Loads configuration from ``.env``, constructs a :class:`~bot.PostBot`
instance, attaches middleware, and starts the bot.

Run with::

    uv run main.py

Or via the installed script (see ``pyproject.toml``)::

    mailman-bot
"""

from __future__ import annotations

from mmbot_framework import IgnoreSelfMiddleware

from bot import DMOnlyMiddleware, PostBot
from config import PostBotConfig


def main() -> None:
    """Load configuration, build the bot, and run it until interrupted."""
    config = PostBotConfig.load(".env")

    bot = PostBot(config)

    # Middleware is applied in registration order.
    # 1. Drop the bot's own messages first (cheapest check).
    # 2. Then drop any messages not from a DM channel.
    bot.add_middleware(IgnoreSelfMiddleware(bot))
    bot.add_middleware(DMOnlyMiddleware())

    bot.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the import resolves**

```bash
cd postbot
uv run python -c "from main import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add postbot/main.py
git commit -m "feat(postbot): rewrite main.py as thin entry point"
```

---

## Task 7: Delete the scripts/ directory

**Files:**
- Delete: `postbot/scripts/` (all contents)

- [ ] **Step 1: Remove the directory**

```bash
git rm -r postbot/scripts/
```

Expected output lists each removed file:
```
rm 'postbot/scripts/__init__.py'
rm 'postbot/scripts/config.py'
rm 'postbot/scripts/database.py'
rm 'postbot/scripts/handlers.py'
rm 'postbot/scripts/mattermost.py'
rm 'postbot/scripts/patches.py'
rm 'postbot/scripts/state.py'
```

- [ ] **Step 2: Commit**

```bash
git commit -m "refactor(postbot): remove scripts/ — logic migrated to bot.py and flat modules"
```

---

## Task 8: Smoke-test the full import chain

Verifies that all modules import cleanly together with no circular imports or missing symbols before attempting a live run.

- [ ] **Step 1: Run the smoke test**

```bash
cd postbot
uv run python -c "
from config import PostBotConfig
from bot import PostBot, DMOnlyMiddleware
from database import initialize_database, log_broadcast, close_db_connection
from patches import apply_ssl_patch
from mmbot_framework import IgnoreSelfMiddleware
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 2: Update CLAUDE.md if the run command changed**

The run command is unchanged (`uv run main.py`), so no CLAUDE.md update is needed.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(postbot): complete migration to mmbot_framework"
```

---

## Post-migration notes

- **Existing tests** in `postbot/tests/` mock the old `scripts.*` module paths and will fail. They are out of scope for this migration and should be updated in a follow-up.
- **`_session_cleanup_loop` accesses `self.sessions._sessions`** (a private attribute of `SessionManager`). This is intentional — the framework does not expose a pre-purge hook. Document this in a follow-up if the framework is extended.
- **`known_users` resets on restart** — this matches the original behaviour. If persistence is wanted, it should be stored in SQLite in a follow-up.
