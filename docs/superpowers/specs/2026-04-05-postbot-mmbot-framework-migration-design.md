# Design: Migrate postbot to mmbot_framework

**Date:** 2026-04-05
**Status:** Approved

## Overview

Rewrite `postbot` to use `mmbot_framework` as its foundation. The bot's broadcast-relay logic is preserved exactly; only the infrastructure layer (WebSocket lifecycle, session management, logging, driver login) is replaced by the framework.

---

## File Structure

**Before:**
```
postbot/
  main.py
  scripts/
    config.py
    handlers.py
    mattermost.py
    state.py
    database.py
    patches.py
  channels.json
```

**After (flat):**
```
postbot/
  main.py        # ~20 lines: load config, instantiate PostBot, run
  bot.py         # PostBot(BaseBot) — all command handlers + lifecycle
  config.py      # PostBotConfig(BotConfig) + .env loader
  database.py    # SQLite broadcast log (unchanged)
  patches.py     # SSL workaround (unchanged)
  channels.json  # channel group definitions (unchanged)
```

Eliminated: `scripts/state.py` (state lives on PostBot instance), `scripts/mattermost.py` (driver owned by framework; `resolve_targets` becomes a PostBot method), `scripts/handlers.py` (handlers become PostBot methods).

---

## Configuration

`PostBotConfig(BotConfig)` in `config.py` extends the framework's `BotConfig` with postbot-specific fields:

| Field | Env var | Default | Description |
|---|---|---|---|
| `bot_log_channel_id` | `BOT_LOG_CHANNEL_ID` | `""` | Channel to post audit messages after each broadcast. Empty = disabled. |
| `channels_json_path` | `CHANNELS_JSON_PATH` | `"channels.json"` | Path to the channel group definitions file. |
| `db_path` | `DB_PATH` | `"broadcast_log.db"` | Path to the SQLite broadcast log. |
| `console_log_level` | `CONSOLE_LOGGING_LEVEL` | `"WARNING"` | Log level for console output (separate from file log). |

`channels.json` content (`VISIBLE_CHANNEL_GROUPS`, `PRIVATE_CHANNEL_GROUPS`, `WHITELIST`) is **not** part of the Pydantic model — it is loaded at runtime and held on the `PostBot` instance, because it is mutable via the `!add_group`/`!add_private_group` commands.

A `PostBotConfig.load(path)` classmethod reads the `.env` file with `dotenv_values` and validates via Pydantic.

---

## PostBot Class (`bot.py`)

`PostBot(BaseBot)` owns all bot-specific logic. Framework infrastructure (WebSocket loop, session TTL cleanup, logging, driver login) is inherited.

### Instance state

| Attribute | Type | Description |
|---|---|---|
| `_team_id` | `str` | Fetched in `on_start()`. |
| `_bot_username` | `str` | Fetched in `on_start()`. |
| `_known_users` | `set[str]` | In-memory set of user IDs that have seen the welcome message. Resets on restart (matches current behaviour). |
| `_visible_groups` | `dict[str, list[str]]` | Loaded from `channels.json`, updated by `!add_group`. |
| `_private_groups` | `dict[str, list[str]]` | Loaded from `channels.json`, updated by `!add_private_group`. |
| `_whitelist` | `set[str]` | Loaded from `channels.json`. |

### Lifecycle hooks

- **`on_start()`** — applies SSL patch, initialises DB, fetches `_team_id` and `_bot_username`, loads channel data from `channels.json`, registers extra help triggers.
- **`on_stop()`** — closes DB connection.
- **`_session_cleanup_loop()` (override)** — before calling `self.sessions.purge_expired()`, iterates expired sessions and sends a "session expired" DM to each user (current behaviour). The framework's default silently drops sessions without notification.

### Middleware stack

Applied in order, before command dispatch:

1. `IgnoreSelfMiddleware(bot)` — drops messages from the bot's own account.
2. `DMOnlyMiddleware` — drops any message where `msg.channel_type != "D"`. Short-circuits without logging noise. Defined as a small class in `bot.py`.

### Commands

Multiple triggers for the same handler are registered explicitly in `__init__` via `self._dispatcher.register()`, since `@command` supports one trigger per method.

| Trigger(s) | Handler | Notes |
|---|---|---|
| `!help`, `help`, `--help`, `man` | `_handle_help` | Shows usage message |
| `!id` | `_handle_id` | Looks up channel ID by name |
| `!channels` | `_handle_channels` | Lists all channels bot has access to |
| `!get_groups` | `_handle_get_groups` | Lists visible groups |
| `!get_private_groups` | `_handle_get_private_groups` | Lists private groups |
| `!add_group` | `_handle_add_group` | Adds public group(s) from JSON |
| `!add_private_group` | `_handle_add_private_group` | Adds private group(s) from JSON |

`on_message()` (fallback) handles the broadcast wizard for all non-command DMs.

### Broadcast wizard (`on_message`)

State machine using `self.sessions` (framework `SessionManager`):

```
No session → new user?
  Yes → welcome message, add to _known_users, return
  No  → create session (AWAITING_CHANNELS), ask for targets

Session.data["state"] == "AWAITING_CHANNELS"
  → resolve targets, update session to CONFIRMATION, show preview

Session.data["state"] == "CONFIRMATION"
  → "yes": relay message + files, log to DB, clear session
  → "no": cancel, clear session
  → other: ask again
```

Session data keys: `state`, `message`, `file_ids`, `dm_channel_id`, `target_ids`, `valid_names`.

### Helper methods

- `_post(channel_id, text)` — thin wrapper over `self.driver.posts.create_post()`.
- `_resolve_targets(inputs)` — resolves comma-separated channel names/IDs/group names to valid whitelisted channel IDs. Moved from `scripts/mattermost.py`.
- `_load_channel_data()` — reads `channels.json` and populates `_visible_groups`, `_private_groups`, `_whitelist`. Called in `on_start()` and after any `!add_group` mutation.

### Bug fix

`handle_add_group` in the current code uses `text.strip().lstrip("!_add_group")` which strips individual characters rather than a prefix string (Python `lstrip` semantics). Replaced with `text[len("!add_group"):].strip()`.

---

## main.py

```python
from bot import PostBot
from config import PostBotConfig
from mmbot_framework import IgnoreSelfMiddleware

config = PostBotConfig.load(".env")
bot = PostBot(config)
bot.add_middleware(IgnoreSelfMiddleware(bot))
bot.add_middleware(DMOnlyMiddleware())
bot.run()
```

---

## pyproject.toml changes

Add `mmbot-framework` as a path dependency (already declared at workspace root level):

```toml
[tool.uv.sources]
mmbot-framework = { path = "../mmbot_framework" }
```

---

## What is NOT changing

- `database.py` — identical, just relocated to top level.
- `patches.py` — identical, just relocated to top level.
- `channels.json` — unchanged.
- Broadcast logic and all user-facing messages — preserved exactly.
- Session expiry notification behaviour — preserved (framework default does not notify).
- Tests — out of scope for this migration; existing tests will need separate updates.
