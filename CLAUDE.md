# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This is a `uv` workspace. The root `pyproject.toml` declares both sub-projects as workspace members. Each sub-project also has its own `pyproject.toml`.

### mmbot_framework
```bash
cd mmbot_framework
uv sync --extra dev                                                                        # Install with dev dependencies
uv run --extra dev pytest -v                                                               # Run all tests
uv run --extra dev pytest tests/test_bot.py -v                                            # Run a single test file
uv run --extra dev pytest tests/test_bot.py::TestBaseBot::test_reply -v                   # Run a single test
```

### postbot
```bash
cd postbot
uv sync                      # Install dependencies
uv run pytest -v             # Run all tests
uv run pytest tests/test_main.py::TestMailmanBot::test_help_command -v  # Run a single test
uv run main.py               # Run the bot locally
```

postbot also ships a `Containerfile` for containerized deployment.

No linting configuration is defined; the projects use standard Python type hints and Pydantic validation.

## Architecture

This is a monorepo with two components:

### mmbot_framework (reusable library)
A framework for building Mattermost bots. Public API is exported from `mmbot_framework/__init__.py`.

**Message flow:**
```
WebSocket event → BaseBot.message_handler()
  → ParsedMessage.from_raw()       # parse JSON into structured dataclass
  → MiddlewarePipeline             # async chain, can short-circuit
  → CommandDispatcher.dispatch()   # case-insensitive startswith() matching
  → handler / on_message() hook
```

Key classes:
- **`BaseBot`** — subclass this or instantiate directly. Lifecycle hooks: `on_start()`, `on_message()`, `on_stop()`. Send replies with `await self.reply(msg, text)`. Access per-user state via `self.sessions`.
- **`ConfigLoader`** — loads `BotConfig` (Pydantic model) from `.env`, `.toml`, or `.json`. Use `ConfigLoader.auto_detect()` to search cwd.
- **`CommandDispatcher`** — register triggers via `@command("!trigger")` decorator or `dispatcher.register()`. First match wins.
- **`MiddlewarePipeline`** — add middleware with `pipeline.add(mw)`. Built-ins: `LoggingMiddleware`, `IgnoreSelfMiddleware`.
- **`SessionManager`** — TTL-based per-user state store (`self.sessions`). Lazy expiry with background cleanup.

### postbot (bot implementation)
A broadcast relay bot ("mailman bot") — not yet migrated to use mmbot_framework.

Key files:
- `main.py` — WebSocket entry point and message handler loop
- `scripts/handlers.py` — all command handlers (`!help`, `!id`, `!channels`, `!add_group`, broadcast flow)
- `scripts/state.py` — global mutable state (bot_info, known_users, sessions)
- `scripts/database.py` — SQLite broadcast logging
- `scripts/config.py` — environment variable loading and bot configuration
- `scripts/mattermost.py` — driver initialization and Mattermost API helpers
- `channels.json` — channel group definitions with visibility and whitelist settings

**Broadcast wizard flow** (session-based, 2-step):
1. `AWAITING_CHANNELS` — user specifies target channels/groups
2. `CONFIRMATION` — user confirms before broadcast is sent

### Required environment variables
- `MATTERMOST_URL`, `BOT_TOKEN`, `TEAM_NAME`
- See `.env` for full list of optional overrides (session TTL, log levels, DB path, etc.)