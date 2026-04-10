# Channel Caching Implementation Plan

**Goal:** Add a generic, TTL-based `CacheManager` to `mmbot_framework` and wire postbot's channel data through it, eliminating repeated API calls on every command.

**Architecture:** A new `CacheManager` class in the framework holds named cache entries, each with an async loader and a TTL. `BaseBot` owns a `self.cache` instance and runs a background refresh task. postbot registers a `"channels"` entry whose loader pre-fetches all channel and team data in one pass; all command handlers read from the cache instead of calling the API directly.

**Tech Stack:** Python 3.14, asyncio, mattermostdriver, mmbot_framework (existing), Pydantic (existing config validation).

---

## Scope

Two components change:

1. **`mmbot_framework`** — new `CacheManager` class + integration into `BaseBot`.
2. **`postbot`** — new config field, new loader function, new `!refresh_channels` command, all channel API call-sites switched to cache lookups.

---

## `CacheManager` (mmbot_framework)

### File

`mmbot_framework/mmbot_framework/core/cache.py`

### Data model

Each named entry is a `CacheEntry` dataclass:

```python
@dataclass
class CacheEntry:
    loader: Callable[[], Awaitable[Any]]
    ttl: float          # seconds
    data: Any = None
    loaded_at: float = 0.0
```

### Public API

```python
class CacheManager:
    def register(self, name: str, loader: Callable[[], Awaitable[Any]], ttl: float) -> None:
        """Register a named cache entry with an async loader and TTL."""

    def get(self, name: str) -> Any:
        """Return cached data for *name*, or None if not yet loaded."""

    async def refresh(self, name: str) -> None:
        """Force-reload the named entry by calling its loader."""

    async def refresh_stale(self) -> None:
        """Reload all entries whose TTL has elapsed. Called by the background task."""
```

### Background task

`BaseBot._async_main` starts a `_cache_refresh_loop` task alongside the existing `_session_cleanup_loop`. The loop wakes every 60 seconds and calls `cache.refresh_stale()`. The 60-second poll interval is a fixed internal constant — operators control freshness via the per-entry TTL.

### BaseBot changes

- `__init__`: `self.cache = CacheManager()`
- `_async_main`: start `_cache_refresh_loop` task, cancel it in the `finally` block alongside `cleanup_task`.
- Export `CacheManager` from `mmbot_framework/__init__.py`.

---

## postbot integration

### New config field

`PostBotConfig` gains one field:

```python
channel_cache_ttl_seconds: int = 3600
```

Set via `CHANNEL_CACHE_TTL_SECONDS` in `.env`. Validated as a positive integer.

### Cache data shape

The loader returns:

```python
{
    "by_id": {
        channel_id: {
            "name": str,           # system name (e.g. "town-square")
            "display_name": str,   # human name (e.g. "Town Square")
            "team_name": str,      # display name of the team, or "N/A"
            "team_id": str,
        }
    },
    "by_name": {
        channel_name: channel_id   # system name → ID
    },
    "all_rows": [str]              # pre-formatted Markdown table rows for !channels
}
```

`"all_rows"` is built once at load time so `!channels` is just a string join with no further processing.

### Loader function

`PostBot._load_channel_cache()` (async, no args):

1. Fetch all teams the bot belongs to (`get_user_teams("me")`).
2. For each team, fetch all channels (`get_channels_for_user("me", team_id)`).
3. Build `by_id`, `by_name`, and `all_rows` in one pass (one `get_team` call per team, not per channel).
4. Return the dict.

Called by `CacheManager` — never directly.

### on_start

```python
self.cache.register("channels", self._load_channel_cache, ttl=self.config.channel_cache_ttl_seconds)
await self.cache.refresh("channels")   # eager load before WebSocket opens
```

### New command: `!refresh_channels`

Registered in `__init__` alongside the other commands. Calls `await self.cache.refresh("channels")` and replies with a success message including the reload timestamp (UTC).

### Call-site changes

| Handler | Old call | New lookup |
|---|---|---|
| `!channels` | teams + channels + get_team per channel | `cache.get("channels")["all_rows"]` |
| `!id <name>` | `get_channel_by_name(team, name)` | `cache.get("channels")["by_name"][name]` |
| `!get_groups` | `get_channel(id)` per group channel | `cache.get("channels")["by_id"][id]` |
| `!get_private_groups` | `get_channel(id)` per group channel | `cache.get("channels")["by_id"][id]` |
| `_handle_new_session` | `get_channel(id)` + `get_team(id)` per whitelist entry | `cache.get("channels")["by_id"][id]` |
| `_resolve_targets` | `get_channel_by_name(team, name)` + `get_channel(id)` per input | `by_name` then `by_id` lookups |

### Cache miss fallback

If a lookup key is absent (channel created after last refresh), the handler falls back to a live API call, logs a warning, and appends a note to the reply:
> `⚠️ Some channel data may be stale — run !refresh_channels to reload.`

---

## README updates

Both `mmbot_framework` and `postbot` READMEs gain a **Caching** section explaining:
- `CacheManager` API (framework README)
- `CHANNEL_CACHE_TTL_SECONDS` config variable and `!refresh_channels` command (postbot README)

---

## Testing

- **`mmbot_framework` tests**: `CacheManager` unit tests — register, get (before/after load), refresh, refresh_stale (with mocked `asyncio.sleep` or manual time manipulation), concurrent refresh safety.
- **`postbot` tests**: `_load_channel_cache` with mocked driver; `!refresh_channels` command; each call-site handler verifies it reads from cache (no driver calls) on a cache hit, and falls back + warns on a cache miss.
