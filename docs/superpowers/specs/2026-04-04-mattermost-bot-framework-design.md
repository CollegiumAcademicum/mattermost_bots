# Mattermost Bot Framework — Design Spec

**Date:** 2026-04-04
**Status:** Approved
**Location:** `mmbot_framework/` (shared library alongside `postbot`)

---

## Overview

`mmbot_framework` is an internal shared Python library for building Mattermost bots within this
organisation's monorepo. It provides:

- Flexible config loading from `.env`, `.toml`, and `.json` with auto-detection
- A validated `BotConfig` model
- A `BaseBot` class with lifecycle hooks (`on_start`, `on_stop`, `on_message`)
- A command dispatcher supporting both decorator and class-based registration
- An async middleware pipeline for cross-cutting concerns (logging, auth, rate limiting, etc.)
- Built-in optional middlewares (`LoggingMiddleware`, `IgnoreSelfMiddleware`)
- Structured logging throughout, configurable per-bot
- Full unit test coverage

Bots install it as a local dependency via `pyproject.toml`:

```toml
[tool.uv.sources]
mmbot-framework = { path = "mmbot_framework" }
```

---

## Package Structure

```
mmbot_framework/
├── __init__.py              # Public API re-exports
├── config/
│   ├── __init__.py
│   ├── loader.py            # Auto-detect + explicit config loading
│   └── schema.py            # Pydantic BotConfig model + ConfigError
├── core/
│   ├── __init__.py
│   ├── bot.py               # BaseBot class + lifecycle hooks
│   └── driver.py            # Driver initialisation helper
├── routing/
│   ├── __init__.py
│   └── dispatcher.py        # CommandDispatcher + @command decorator
└── middleware/
    ├── __init__.py
    └── pipeline.py          # Middleware chain + built-in middlewares

tests/
└── mmbot_framework/
    ├── test_config.py
    ├── test_bot.py
    ├── test_dispatcher.py
    └── test_middleware.py
```

---

## Section 1: Config Layer

### `config/schema.py`

`BotConfig` is a Pydantic `BaseModel`:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | `str` | yes | — | Mattermost server URL |
| `token` | `str` | yes | — | Bot authentication token |
| `team_name` | `str` | yes | — | Mattermost team name |
| `scheme` | `str` | no | `"https"` | HTTP scheme |
| `port` | `int` | no | `443` | Server port |
| `log_level` | `str` | no | `"INFO"` | Root log level |
| `log_file` | `str \| None` | no | `None` | Path for file logging; `None` = console only |

Missing required fields raise `ConfigError` with a clear message naming the missing field.

### `config/loader.py`

`ConfigLoader` has two public class methods:

```python
# Explicit — developer specifies the file; format is inferred from extension
config = ConfigLoader.from_file("config.toml")   # .toml
config = ConfigLoader.from_file("settings.json") # .json
config = ConfigLoader.from_file(".env")           # .env

# Auto-detect — searches cwd in order: .env → config.toml → config.json
config = ConfigLoader.auto_detect()
```

All formats are normalised to a `BotConfig` instance. Unsupported file extensions or missing
files raise `ConfigError`.

---

## Section 2: Core Layer

### `core/driver.py`

`DriverFactory.create(config: BotConfig) -> Driver` constructs and returns a
`mattermostdriver.Driver` instance from a `BotConfig`. Does not call `.login()` — that is
`BaseBot`'s responsibility, keeping the factory pure and easily testable.

### `core/bot.py`

`BaseBot` is the central class. It owns a `CommandDispatcher` and a middleware pipeline.

**Lifecycle (in order):**

1. `BaseBot.run()` — single public entry point
2. Logging configured from `config.log_level` / `config.log_file`
3. Driver created and `.login()` called
4. `on_start()` awaited — override for DB init, cache seeding, etc.
5. WebSocket opened; incoming messages flow through middleware → dispatcher → `on_message`
6. On SIGINT/SIGTERM: WebSocket closed, `on_stop()` awaited

**Overridable hooks:**

```python
class MyBot(BaseBot):
    async def on_start(self) -> None:
        """Called after driver login, before WebSocket opens."""
        ...

    async def on_stop(self) -> None:
        """Called on clean shutdown."""
        ...

    async def on_message(self, msg: ParsedMessage) -> None:
        """Fallback for messages that cleared middleware but matched no command."""
        ...
```

**`ParsedMessage` dataclass:**

```python
@dataclass
class ParsedMessage:
    sender_id: str
    sender_name: str
    channel_id: str
    channel_type: str   # "D" = DM, "O" = public, "P" = private group
    text: str
    file_ids: list[str]
    raw: dict           # original WebSocket payload, always available
```

**Helper:**

```python
await bot.reply(msg, "Your message here")
# Shorthand for driver.posts.create_post({"channel_id": msg.channel_id, "message": text})
```

---

## Section 3: Routing Layer

### `routing/dispatcher.py`

`CommandDispatcher` maps trigger strings to async handler functions. Matching uses
`msg.text.lower().startswith(trigger)`. Commands are checked in registration order; first
match wins.

**Standalone usage:**

```python
dispatcher = CommandDispatcher()
dispatcher.register("!ping", ping_handler)
await dispatcher.dispatch(msg)
```

**Decorator on a `BaseBot` instance:**

```python
bot = BaseBot(config)

@bot.command("!help")
async def help_handler(msg: ParsedMessage) -> None:
    await bot.reply(msg, "Help text here...")
```

**Class-based decorator:**

```python
from mmbot_framework.routing import command

class MyBot(BaseBot):
    @command("!help")
    async def help_handler(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "Help text here...")
```

**Default handler** (unmatched messages):

```python
@bot.default_handler
async def fallback(msg: ParsedMessage) -> None:
    await bot.reply(msg, "Unknown command.")
# Equivalent to overriding on_message() in a subclass.
```

---

## Section 4: Middleware Layer

### `middleware/pipeline.py`

Middleware functions are `async` callables:

```python
async def my_middleware(msg: ParsedMessage, next: Callable) -> None:
    # pre-processing
    await next(msg)   # pass to next middleware / dispatcher
    # post-processing (optional)
```

Not calling `next` silently drops the message — useful for guards.

**Registration:**

```python
bot.add_middleware(logging_middleware)
bot.add_middleware(rate_limit_middleware)
# Executed in registration order: logging → rate_limit → dispatcher
```

**Built-in middlewares (optional, importable):**

| Class | Behaviour |
|---|---|
| `IgnoreSelfMiddleware(bot)` | Drops messages where `sender_id == bot_id`. Almost always wanted. |
| `LoggingMiddleware()` | Logs every incoming message at DEBUG with sender and channel. |

```python
from mmbot_framework.middleware import LoggingMiddleware, IgnoreSelfMiddleware

bot.add_middleware(IgnoreSelfMiddleware(bot))
bot.add_middleware(LoggingMiddleware())
```

---

## Testing Strategy

- Each layer is unit-tested in isolation using `pytest` and `unittest.mock`.
- `Driver` is mocked at the `DriverFactory` level; no live Mattermost connection required.
- `ParsedMessage` fixtures are constructed directly for dispatcher and middleware tests.
- Config tests cover all three file formats, auto-detection order, and missing-field errors.
- Lifecycle hook tests verify call order using async mocks.

---

## Non-Goals

- Automatic WebSocket reconnection (left to the developer).
- Persistence / database utilities (bot-specific concern).
- Any HTTP server / webhook support.
- Support for file formats beyond `.env`, `.toml`, `.json`.