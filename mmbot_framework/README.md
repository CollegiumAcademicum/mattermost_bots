# mmbot-framework

A shared Python library for building Mattermost bots. It provides configuration
loading, WebSocket-driven message handling, command routing, async middleware, and
TTL-based session management so individual bot projects can focus on business logic
rather than boilerplate.

---

## Installation

Add the library as a path dependency in your bot's `pyproject.toml`:

```toml
[project]
dependencies = [
    "mmbot-framework @ ../mmbot_framework",
]
```

Then sync with `uv`:

```bash
uv sync
```

---

## Quick Start

A minimal bot that responds to `!ping` and ignores its own messages:

```python
import asyncio
from mmbot_framework import (
    BaseBot,
    BotConfig,
    ConfigLoader,
    IgnoreSelfMiddleware,
    LoggingMiddleware,
    ParsedMessage,
    command,
)


class PingBot(BaseBot):

    async def on_start(self) -> None:
        print("PingBot is ready!")

    @command("!ping")
    async def ping(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "pong")

    async def on_message(self, msg: ParsedMessage) -> None:
        await self.reply(msg, f"Unknown command: {msg.text!r}")


if __name__ == "__main__":
    config = ConfigLoader.auto_detect()
    bot = PingBot(config)
    bot.add_middleware(IgnoreSelfMiddleware(bot))
    bot.add_middleware(LoggingMiddleware())
    bot.run()
```

---

## Configuration

### BotConfig fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | `str` | yes | — | Mattermost server URL (e.g. `https://mattermost.example.com`) |
| `token` | `str` | yes | — | Bot authentication token |
| `team_name` | `str` | yes | — | Mattermost team name (slug, not display name) |
| `scheme` | `str` | no | `"https"` | HTTP scheme (`"http"` or `"https"`) |
| `port` | `int` | no | `443` | Server port (1–65535) |
| `log_level` | `str` | no | `"INFO"` | Python log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `log_file` | `str \| None` | no | `None` | Path for rotating log file; `None` means console only |
| `session_ttl_seconds` | `int` | no | `3600` | Seconds of inactivity before a session expires |
| `session_cleanup_interval_seconds` | `int` | no | `300` | How often the background cleanup task runs |

### Loading config

**Auto-detect** (searches cwd for `.env` then `config.toml` then `config.json`):

```python
from mmbot_framework import ConfigLoader

config = ConfigLoader.auto_detect()
# Or specify a directory:
config = ConfigLoader.auto_detect("/path/to/bot")
```

**Explicit file** (format inferred from extension):

```python
config = ConfigLoader.from_file("config.toml")
config = ConfigLoader.from_file("settings.json")
config = ConfigLoader.from_file(".env")
```

**Example `.env`:**

```dotenv
URL=https://mattermost.example.com
TOKEN=your-bot-token
TEAM_NAME=my-team
LOG_LEVEL=DEBUG
```

**Example `config.toml`:**

```toml
url = "https://mattermost.example.com"
token = "your-bot-token"
team_name = "my-team"
log_level = "DEBUG"
```

---

## Commands

### Class-based (subclass `BaseBot`)

Decorate methods with `@command(trigger)`. The trigger is matched
case-insensitively using `str.startswith`:

```python
from mmbot_framework import BaseBot, ParsedMessage, command

class MyBot(BaseBot):

    @command("!help")
    async def help_handler(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "Available commands: !help, !ping")

    @command("!ping")
    async def ping(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "pong")
```

### Instance-based (functional style)

Use the `@bot.command(trigger)` instance decorator when you prefer not to subclass:

```python
from mmbot_framework import BaseBot, ConfigLoader, ParsedMessage

config = ConfigLoader.auto_detect()
bot = BaseBot(config)

@bot.command("!ping")
async def ping(msg: ParsedMessage) -> None:
    await bot.reply(msg, "pong")
```

### Default / fallback handler

Handle messages that match no command. Use either the `on_message` lifecycle hook
(subclass style) or `@bot.default_handler` (functional style):

```python
# Subclass style
class MyBot(BaseBot):
    async def on_message(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "I don't understand that.")

# Functional style
@bot.default_handler
async def fallback(msg: ParsedMessage) -> None:
    await bot.reply(msg, "I don't understand that.")
```

---

## Middleware

Middleware functions have the signature:

```python
async def my_middleware(msg: ParsedMessage, call_next: Callable) -> None:
    ...
```

Not calling `call_next` **short-circuits** the chain (useful for guards).

### Built-in middleware

```python
from mmbot_framework import IgnoreSelfMiddleware, LoggingMiddleware

# Drop messages sent by the bot itself (prevents feedback loops)
bot.add_middleware(IgnoreSelfMiddleware(bot))

# Log every incoming message at DEBUG level
bot.add_middleware(LoggingMiddleware())
```

Middleware is executed in the order it is added.

### Custom middleware

```python
import logging
from mmbot_framework import ParsedMessage
from typing import Callable

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    def __init__(self, max_per_minute: int = 10) -> None:
        self._counts: dict[str, int] = {}
        self._max = max_per_minute

    async def __call__(self, msg: ParsedMessage, call_next: Callable) -> None:
        count = self._counts.get(msg.sender_id, 0)
        if count >= self._max:
            logger.warning("Rate limit hit for %s — dropping message.", msg.sender_id)
            return  # short-circuit: do not call call_next
        self._counts[msg.sender_id] = count + 1
        await call_next(msg)

bot.add_middleware(RateLimitMiddleware(max_per_minute=5))
```

---

## Sessions

`BaseBot` exposes a `sessions` attribute (`SessionManager`) for per-user
conversation state. Sessions expire automatically after `session_ttl_seconds`
seconds of inactivity; a background task inside `run()` purges them periodically.

```python
from mmbot_framework import BaseBot, ParsedMessage, command

class WizardBot(BaseBot):

    @command("!start")
    async def start_wizard(self, msg: ParsedMessage) -> None:
        session = self.sessions.get_or_create(msg.sender_id)
        session.data["step"] = 1
        await self.reply(msg, "Step 1: what is your name?")

    @command("!cancel")
    async def cancel(self, msg: ParsedMessage) -> None:
        self.sessions.clear(msg.sender_id)
        await self.reply(msg, "Wizard cancelled.")

    async def on_message(self, msg: ParsedMessage) -> None:
        session = self.sessions.get(msg.sender_id)
        if session is None:
            await self.reply(msg, "No active wizard. Type !start to begin.")
            return
        step = session.data.get("step")
        if step == 1:
            session.data["name"] = msg.text
            session.data["step"] = 2
            await self.reply(msg, f"Hello, {msg.text}! Step 2: what is your role?")
        elif step == 2:
            name = session.data["name"]
            self.sessions.clear(msg.sender_id)
            await self.reply(msg, f"Done! {name} — {msg.text}.")
```

### SessionManager API

| Method | Description |
|---|---|
| `get(sender_id)` | Return the live session or `None` if absent/expired. Updates `last_active`. |
| `get_or_create(sender_id)` | Return or create a fresh session. |
| `clear(sender_id)` | Explicitly delete the session. Safe to call if no session exists. |
| `is_alive(sender_id)` | Return `True` if a non-expired session exists (does not update `last_active`). |
| `purge_expired()` | Remove all expired sessions. Returns the count removed. |

---

## Caching

`BaseBot` exposes a `cache` attribute (`CacheManager`) for storing data that is
expensive to fetch on every request.  Each named entry has an async **loader**
callable and a **TTL**; a background task refreshes stale entries every 60 seconds.

### Registering a cache entry

Call `cache.register()` in `on_start()`, then `await cache.refresh()` to
pre-warm the entry before the WebSocket opens:

```python
class MyBot(BaseBot):

    async def on_start(self) -> None:
        self.cache.register("users", self._load_users, ttl=300)
        await self.cache.refresh("users")   # pre-warm at startup

    async def _load_users(self) -> dict:
        """Fetch all users and index them by ID."""
        return {u["id"]: u for u in self.driver.users.get_users()}
```

### Reading cached data

Use `cache.get(name)` inside command handlers.  It returns `None` if the entry
has never been loaded:

```python
    @command("!whoami")
    async def whoami(self, msg: ParsedMessage) -> None:
        users = self.cache.get("users")
        if users is None:
            await self.reply(msg, "Cache not ready — try again shortly.")
            return
        name = users.get(msg.sender_id, {}).get("username", "unknown")
        await self.reply(msg, f"You are @{name}")
```

### Forcing a refresh

Call `await cache.refresh(name)` to reload a single entry immediately (e.g.
from a `!refresh` command):

```python
    @command("!refresh_users")
    async def refresh_users(self, msg: ParsedMessage) -> None:
        await self.cache.refresh("users")
        await self.reply(msg, "User cache refreshed.")
```

### CacheManager API

| Method | Description |
|---|---|
| `register(name, loader, ttl)` | Register a named entry with an async loader and TTL (seconds). |
| `get(name)` | Return cached data or `None` if not yet loaded. |
| `refresh(name)` | Force-reload the named entry. Raises `KeyError` if not registered. |
| `refresh_stale()` | Reload all entries whose TTL has elapsed. Called by the background task. |

---

## Lifecycle hooks

Override any of these async methods in your `BaseBot` subclass:

```python
class MyBot(BaseBot):

    async def on_start(self) -> None:
        """Called after driver login, before the WebSocket opens."""
        # Open database connections, warm up caches, etc.

    async def on_stop(self) -> None:
        """Called on clean shutdown (Ctrl+C / SIGTERM)."""
        # Close connections, flush state, etc.

    async def on_message(self, msg: ParsedMessage) -> None:
        """Called when a message clears the middleware but matches no command."""
        await self.reply(msg, "Unknown command.")
```

---

## Development

Install the package with dev dependencies and run the full test suite:

```bash
cd mmbot_framework
uv run --extra dev pytest -v
```

The test suite must remain at 100 % passing. To run a single test file:

```bash
uv run --extra dev pytest tests/test_session.py -v
```
