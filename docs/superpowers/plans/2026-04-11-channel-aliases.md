# Channel & Group Aliases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional aliases to channel groups and whitelisted channels in `channels.toml`, enabling shorter broadcast target names, with a `!add_alias` command and inline alias display.

**Architecture:** Migrate `channels.toml` from flat group/whitelist assignments to TOML table-of-tables with optional `aliases` arrays. `PostBot` loads `GroupEntry`/`WhitelistEntry` dataclasses and builds `_alias_map` + `_whitelist_ids` at startup. `_resolve_targets` checks the alias map before cache lookups. Aliases appear inline in `!get_groups` and `!channels` output. `!add_alias <alias> <target>` persists new aliases at runtime via a `_save_channel_data()` helper.

**Tech Stack:** Python 3.14, `toml` package (already used), mmbot_framework (existing), pytest + anyio (existing).

---

## File Structure

| Action | Path | Change |
|---|---|---|
| Modify | `postbot/bot.py` | Add `GroupEntry`/`WhitelistEntry` dataclasses; rewrite `_load_channel_data`; add `_build_alias_map`, `_save_channel_data`, `_handle_add_alias`; update all consumers |
| Modify | `postbot/tests/conftest.py` | `channels_file` fixture: write TOML instead of JSON |
| Modify | `postbot/tests/test_bot.py` | Fix `channels_json_path` → `channels_toml_path` in `config` fixture; update `bot` fixture data types; fix `TestHandleAddGroup` payload format |
| Modify | `postbot/tests/test_cache.py` | Update `bot` fixture data types |
| Create | `postbot/tests/test_aliases.py` | TOML parsing, alias map, alias resolution, `!add_alias` tests |
| Modify | `postbot/channels.toml` | Migrate to new schema (one-time manual step) |
| Modify | `postbot/README.md` | Add `!add_alias` to Bot Commands table |

---

## Task 1: Data model, TOML parser, and fixture updates

This task changes the in-memory data types for groups and whitelist, rewrites the TOML loader, updates every method that reads those types, and brings all test fixtures in line. After this task all existing tests should pass (except the 4 pre-existing `TestHandleAddGroup` failures — those are fixed in Task 4).

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/conftest.py`
- Modify: `postbot/tests/test_bot.py`
- Modify: `postbot/tests/test_cache.py`
- Create: `postbot/tests/test_aliases.py`

- [ ] **Step 1: Write failing tests for TOML loading and alias map**

Create `postbot/tests/test_aliases.py`:

```python
"""Tests for channel/group alias feature."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import toml

from bot import GroupEntry, PostBot, WhitelistEntry
from config import PostBotConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(tmp_path: Path, toml_content: dict) -> PostBot:
    """Write toml_content to a temp file and return a bot that uses it."""
    p = tmp_path / "channels.toml"
    p.write_text(toml.dumps(toml_content))
    cfg = PostBotConfig(
        url="mm.example.com",
        token="tok",
        team_name="team",
        channels_toml_path=p,
        db_path=tmp_path / "test.db",
        bot_log_channel_id="",
        console_log_level="WARNING",
        log_file=None,
    )
    with patch("mmbot_framework.core.driver.DriverFactory.create", return_value=MagicMock()):
        bot = PostBot(cfg)
    return bot


_VALID_TOML = {
    "whitelist": {
        "ch-id-1": {"id": "ch_id_1", "aliases": ["c1", "one"]},
        "ch-id-2": {"id": "ch_id_2"},  # no aliases key
    },
    "groups": {
        "TestGroup": {"channels": ["ch_id_1", "ch_id_2"], "aliases": ["tg", "test"]},
        "NoAliasGroup": {"channels": ["ch_id_2"]},  # no aliases key
    },
    "private_groups": {
        "PrivGroup": {"channels": ["ch_id_1"], "aliases": ["priv"]},
    },
}


# ---------------------------------------------------------------------------
# TestLoadChannelData
# ---------------------------------------------------------------------------


class TestLoadChannelData:
    def test_loads_group_entries(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert isinstance(bot._visible_groups["TestGroup"], GroupEntry)
        assert bot._visible_groups["TestGroup"].channels == ["ch_id_1", "ch_id_2"]
        assert bot._visible_groups["TestGroup"].aliases == ["tg", "test"]

    def test_missing_aliases_key_defaults_to_empty_list(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert bot._visible_groups["NoAliasGroup"].aliases == []

    def test_loads_whitelist_entries(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert isinstance(bot._whitelist["ch-id-1"], WhitelistEntry)
        assert bot._whitelist["ch-id-1"].id == "ch_id_1"
        assert bot._whitelist["ch-id-1"].aliases == ["c1", "one"]

    def test_whitelist_entry_no_aliases_defaults_empty(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert bot._whitelist["ch-id-2"].aliases == []

    def test_old_flat_whitelist_raises_value_error(self, tmp_path):
        old_format = {
            "whitelist": ["ch_id_1", "ch_id_2"],
            "groups": {},
            "private_groups": {},
        }
        bot = _make_bot(tmp_path, old_format)
        with pytest.raises(ValueError, match="old flat whitelist format"):
            bot._load_channel_data()

    def test_old_flat_group_value_raises_value_error(self, tmp_path):
        old_format = {
            "whitelist": {},
            "groups": {"OldGroup": ["ch_id_1"]},
            "private_groups": {},
        }
        bot = _make_bot(tmp_path, old_format)
        with pytest.raises(ValueError, match="old flat group format"):
            bot._load_channel_data()

    def test_builds_whitelist_ids_set(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert "ch_id_1" in bot._whitelist_ids
        assert "ch_id_2" in bot._whitelist_ids


# ---------------------------------------------------------------------------
# TestBuildAliasMap
# ---------------------------------------------------------------------------


class TestBuildAliasMap:
    def test_group_alias_registered(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert bot._alias_map["tg"] == "TestGroup"
        assert bot._alias_map["test"] == "TestGroup"

    def test_whitelist_alias_registered(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert bot._alias_map["c1"] == "ch-id-1"
        assert bot._alias_map["one"] == "ch-id-1"

    def test_private_group_alias_registered(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        assert bot._alias_map["priv"] == "PrivGroup"

    def test_collision_first_definition_wins(self, tmp_path, caplog):
        collision = {
            "whitelist": {},
            "groups": {
                "GroupA": {"channels": ["id1"], "aliases": ["dup"]},
                "GroupB": {"channels": ["id2"], "aliases": ["dup"]},
            },
            "private_groups": {},
        }
        bot = _make_bot(tmp_path, collision)
        import logging
        with caplog.at_level(logging.WARNING, logger="bot"):
            bot._load_channel_data()
        assert bot._alias_map["dup"] == "GroupA"
        assert "dup" in caplog.text
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd /Users/philipp/git-repos/mattermost_bots/postbot
uv run pytest tests/test_aliases.py -v 2>&1 | head -30
```

Expected: ImportError (`GroupEntry`, `WhitelistEntry` do not exist yet).

- [ ] **Step 3: Add `GroupEntry` and `WhitelistEntry` dataclasses to `bot.py`**

Add after the existing imports (after line `from patches import apply_ssl_patch`), before the middleware class:

```python
from dataclasses import dataclass, field as _field


@dataclass
class GroupEntry:
    """A channel group with an optional list of short-name aliases."""

    channels: list[str]
    aliases: list[str] = _field(default_factory=list)


@dataclass
class WhitelistEntry:
    """A whitelisted channel with its TOML label and optional aliases."""

    id: str
    label: str
    aliases: list[str] = _field(default_factory=list)
```

- [ ] **Step 4: Update `PostBot.__init__` to declare new attribute types**

In `__init__`, replace:

```python
        # Channel groups and whitelist loaded from channels.json at startup
        # and mutated in-place by !add_group / !add_private_group.
        self._visible_groups: dict[str, list[str]] = {}
        self._private_groups: dict[str, list[str]] = {}
        self._whitelist: set[str] = set()
```

with:

```python
        # Channel groups and whitelist loaded from channels.toml at startup.
        self._visible_groups: dict[str, GroupEntry] = {}
        self._private_groups: dict[str, GroupEntry] = {}
        self._whitelist: dict[str, WhitelistEntry] = {}
        self._whitelist_ids: set[str] = set()
        self._alias_map: dict[str, str] = {}
```

Also register the new `!add_alias` command (add below the `!refresh_channels` line):

```python
        self._dispatcher.register("!add_alias", self._handle_add_alias)
```

- [ ] **Step 5: Rewrite `_load_channel_data`**

Replace the entire `_load_channel_data` method (currently lines ~954–978):

```python
    def _load_channel_data(self) -> None:
        """Read ``channels.toml`` and populate in-memory group and whitelist data.

        Called at startup via :meth:`on_start` and after any successful
        ``!add_group``, ``!add_private_group``, or ``!add_alias`` mutation.

        Raises:
            FileNotFoundError: If :attr:`~PostBotConfig.channels_toml_path` does not exist.
            ValueError: If the file uses the old flat whitelist or group format.
        """
        path: Path = self.config.channels_toml_path
        logger.info(f"Loading channel data from {path}.")
        with path.open("r", encoding="utf-8") as fh:
            data = toml.load(fh)

        # Detect old flat whitelist format.
        if isinstance(data.get("whitelist"), list):
            raise ValueError(
                f"{path} uses the old flat whitelist format. "
                "Migrate to: [whitelist.<label>] with id = '...' and optional aliases = [...]."
            )

        # Parse whitelist.
        raw_whitelist: dict = data.get("whitelist", {})
        self._whitelist = {}
        for label, entry in raw_whitelist.items():
            self._whitelist[label] = WhitelistEntry(
                id=entry["id"],
                label=label,
                aliases=[a.lower() for a in entry.get("aliases", [])],
            )

        # Detect old flat group format and parse groups.
        def _parse_groups(raw: dict, section: str) -> dict[str, GroupEntry]:
            result: dict[str, GroupEntry] = {}
            for name, val in raw.items():
                if isinstance(val, list):
                    raise ValueError(
                        f"{path} uses the old flat group format for {name!r} "
                        f"in [{section}]. Migrate to: [\"{section}\".\"{name}\"] "
                        "with channels = [...] and optional aliases = [...]."
                    )
                result[name] = GroupEntry(
                    channels=val["channels"],
                    aliases=[a.lower() for a in val.get("aliases", [])],
                )
            return result

        self._visible_groups = _parse_groups(data.get("groups", {}), "groups")
        self._private_groups = _parse_groups(data.get("private_groups", {}), "private_groups")

        self._build_alias_map()
        logger.debug(
            f"Loaded {len(self._visible_groups)} visible groups, "
            f"{len(self._private_groups)} private groups, "
            f"{len(self._whitelist)} whitelist entries."
        )
```

- [ ] **Step 6: Add `_build_alias_map`**

Add this method directly after `_load_channel_data`:

```python
    def _build_alias_map(self) -> None:
        """Rebuild ``_alias_map`` and ``_whitelist_ids`` from current state.

        Called by :meth:`_load_channel_data` and :meth:`_handle_add_alias`.
        On alias collision (same alias on two entries) the first definition
        (TOML file order: visible groups → private groups → whitelist) wins and
        a warning is logged.
        """
        self._alias_map = {}
        self._whitelist_ids = {e.id for e in self._whitelist.values()}

        sources: list[tuple[str, list[str]]] = []
        for name, entry in self._visible_groups.items():
            sources.append((name, entry.aliases))
        for name, entry in self._private_groups.items():
            sources.append((name, entry.aliases))
        for label, entry in self._whitelist.items():
            sources.append((label, entry.aliases))

        for canonical, aliases in sources:
            for alias in aliases:
                key = alias.lower()
                if key in self._alias_map:
                    logger.warning(
                        f"Alias {alias!r} already mapped to "
                        f"{self._alias_map[key]!r}; skipping duplicate "
                        f"for {canonical!r}."
                    )
                else:
                    self._alias_map[key] = canonical
```

- [ ] **Step 7: Run the alias tests to confirm they pass**

```bash
uv run pytest tests/test_aliases.py -v
```

Expected: all tests in `TestLoadChannelData` and `TestBuildAliasMap` pass.

- [ ] **Step 8: Update `_resolve_group_channel_names` to use `GroupEntry`**

Replace the method signature and inner loop (currently at lines ~418–456):

```python
    def _resolve_group_channel_names(
        self,
        groups: dict[str, GroupEntry],
        ch_cache: dict | None,
        context: str,
    ) -> tuple[list[str], bool]:
        """Return formatted group/channel lines and whether any cache miss occurred.

        Args:
            groups: mapping of group name → :class:`GroupEntry`
            ch_cache: the ``"channels"`` cache dict, or ``None`` if not loaded
            context: label for log messages (``"group"`` or ``"private group"``)

        Returns:
            ``(lines, used_fallback)`` where ``used_fallback`` is ``True`` if any
            channel was fetched from the live API due to a cache miss.
        """
        lines: list[str] = []
        used_fallback = False
        for name, entry in groups.items():
            resolved: list[str] = []
            for cid in entry.channels:
                if ch_cache and cid in ch_cache["by_id"]:
                    resolved.append(ch_cache["by_id"][cid]["name"])
                else:
                    logger.warning(
                        f"Cache miss for channel {cid!r} in {context} {name!r}; "
                        f"falling back to live API."
                    )
                    used_fallback = True
                    try:
                        resolved.append(self.driver.channels.get_channel(cid)["name"])
                    except Exception as exc:
                        logger.error(
                            f"Error resolving channel {cid!r} for {context} {name!r}: {exc}"
                        )
                        resolved.append(f"(error: {cid})")
            if entry.aliases:
                aka = ", ".join(f"`{a}`" for a in entry.aliases)
                lines.append(f"**{name}** (aka: {aka}): {resolved}\n")
            else:
                lines.append(f"**{name}:** {resolved}\n")
        return lines, used_fallback
```

- [ ] **Step 9: Update `_handle_new_session` whitelist iteration**

In `_handle_new_session`, replace the whitelist loop (the block from `for channel_id in self._whitelist:` through `allowed_channels.sort()`):

```python
        for entry in self._whitelist.values():
            channel_id = entry.id
            if ch_cache and channel_id in ch_cache["by_id"]:
                info = ch_cache["by_id"][channel_id]
                aliases_str = (
                    f" (aliases: {', '.join(f'`{a}`' for a in entry.aliases)})"
                    if entry.aliases
                    else ""
                )
                allowed_channels.append(
                    f"- name: `{info['name']}`{aliases_str}    "
                    f"(display name: `{info['display_name']}` — "
                    f"ID: `{channel_id}` — team: `{info['team_name']}`)"
                )
            else:
                logger.warning(
                    f"Cache miss for whitelisted channel {channel_id!r}; "
                    f"falling back to live API."
                )
                used_fallback = True
                try:
                    info = self.driver.channels.get_channel(channel_id)
                    team_name = (
                        self.driver.teams.get_team(info["team_id"]).get(
                            "display_name", "N/A"
                        )
                        if info["team_id"]
                        else "N/A"
                    )
                    aliases_str = (
                        f" (aliases: {', '.join(f'`{a}`' for a in entry.aliases)})"
                        if entry.aliases
                        else ""
                    )
                    allowed_channels.append(
                        f"- name: `{info['name']}`{aliases_str}    "
                        f"(display name: `{info['display_name']}` — "
                        f"ID: `{channel_id}` — team: `{team_name}`)"
                    )
                except Exception as exc:
                    logger.error(
                        f"Error fetching info for channel {channel_id!r}: {exc}"
                    )
                    allowed_channels.append(f"- `(ID not found)` (`{channel_id}`)")
        allowed_channels.sort()
```

Also update the `group_list` line below (it stays the same but references `self._visible_groups` which now has `GroupEntry` values, so the f-string must use `.keys()` or just iterate the dict):

```python
        group_list = "".join(f"- `{g}`\n" for g in self._visible_groups)
```

This line is fine as-is (iterating a dict yields its keys).

- [ ] **Step 10: Update `_resolve_targets` to use `_whitelist_ids` and `GroupEntry.channels`**

In `_resolve_targets`, replace:

```python
        all_groups: dict[str, list[str]] = {
            **self._visible_groups,
            **self._private_groups,
        }
```

with:

```python
        all_groups: dict[str, GroupEntry] = {
            **self._visible_groups,
            **self._private_groups,
        }
```

Replace the group expansion:

```python
            if stripped in all_groups:
                valid_ids.update(all_groups[stripped])
```

with:

```python
            if stripped in all_groups:
                valid_ids.update(all_groups[stripped].channels)
```

Replace the whitelist check:

```python
                if channel_id in self._whitelist:
```

with:

```python
                if channel_id in self._whitelist_ids:
```

And the `invalid_inputs` block:

```python
                    invalid_inputs.add(stripped)
                    logger.warning(
                        f"Channel {stripped!r} (resolved to {channel_id!r}) "
                        f"is not in the whitelist."
                    )
```

stays the same.

- [ ] **Step 11: Update `conftest.py` to write TOML format**

Replace the entire `conftest.py` with:

```python
"""Shared pytest fixtures for the postbot test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
import toml

from mmbot_framework import ParsedMessage


# ---------------------------------------------------------------------------
# Minimal config kwargs
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_config_kwargs() -> dict:
    """Return the minimum required fields for constructing a PostBotConfig."""
    return {
        "url": "mm.example.com",
        "token": "test-token",
        "team_name": "myteam",
    }


# ---------------------------------------------------------------------------
# channels.toml fixture file
# ---------------------------------------------------------------------------

_CHANNELS_TOML_CONTENT = {
    "whitelist": {
        "ch-id-1": {"id": "ch_id_1", "aliases": []},
        "ch-id-2": {"id": "ch_id_2", "aliases": []},
        "ch-id-3": {"id": "ch_id_3", "aliases": []},
        "whitelisted": {"id": "whitelisted_id", "aliases": []},
    },
    "groups": {
        "TestGroup": {"channels": ["ch_id_1", "ch_id_2"], "aliases": ["tg"]},
    },
    "private_groups": {
        "PrivateGroup": {"channels": ["ch_id_3"], "aliases": []},
    },
}


@pytest.fixture
def channels_file(tmp_path: Path) -> Path:
    """Write a channels.toml into tmp_path and return the Path."""
    p = tmp_path / "channels.toml"
    p.write_text(toml.dumps(_CHANNELS_TOML_CONTENT))
    return p


# ---------------------------------------------------------------------------
# ParsedMessage factory
# ---------------------------------------------------------------------------


def _make_msg(
    *,
    sender_id: str = "user_id_1",
    sender_name: str = "@testuser",
    channel_id: str = "dm_channel_id_1",
    channel_type: str = "D",
    text: str = "",
    file_ids: list[str] | None = None,
    raw: dict | None = None,
) -> ParsedMessage:
    """Create a :class:`ParsedMessage` with sensible defaults."""
    return ParsedMessage(
        sender_id=sender_id,
        sender_name=sender_name,
        channel_id=channel_id,
        channel_type=channel_type,
        text=text,
        file_ids=file_ids if file_ids is not None else [],
        raw=raw if raw is not None else {},
    )


@pytest.fixture
def make_msg():
    """Return the ``_make_msg`` factory function."""
    return _make_msg
```

- [ ] **Step 12: Update `test_bot.py` fixtures**

Replace the `config` fixture (fix `channels_json_path` → `channels_toml_path`):

```python
@pytest.fixture
def config(channels_file: Path, tmp_path: Path) -> PostBotConfig:
    return PostBotConfig(
        url="mm.example.com",
        token="test-token",
        team_name="test-team",
        channels_toml_path=channels_file,
        db_path=tmp_path / "test.db",
        bot_log_channel_id="",
        console_log_level="WARNING",
        log_file=None,
    )
```

Replace the `bot` fixture (update data types):

```python
@pytest.fixture
def bot(config: PostBotConfig, mock_driver: MagicMock) -> PostBot:
    with patch("mmbot_framework.core.driver.DriverFactory.create", return_value=mock_driver):
        b = PostBot(config)
    b._team_id = "test-team-id"
    b._bot_username = "testbot"
    b._visible_groups = {"TestGroup": GroupEntry(channels=["ch_id_1", "ch_id_2"], aliases=["tg"])}
    b._private_groups = {"PrivateGroup": GroupEntry(channels=["ch_id_3"], aliases=[])}
    b._whitelist = {
        "ch-id-1": WhitelistEntry(id="ch_id_1", label="ch-id-1", aliases=[]),
        "ch-id-2": WhitelistEntry(id="ch_id_2", label="ch-id-2", aliases=[]),
        "ch-id-3": WhitelistEntry(id="ch_id_3", label="ch-id-3", aliases=[]),
        "whitelisted": WhitelistEntry(id="whitelisted_id", label="whitelisted", aliases=[]),
    }
    b._whitelist_ids = {"ch_id_1", "ch_id_2", "ch_id_3", "whitelisted_id"}
    b._alias_map = {"tg": "TestGroup"}
    return b
```

Add the import at the top of `test_bot.py`:

```python
from bot import DMOnlyMiddleware, GroupEntry, PostBot, WhitelistEntry
```

- [ ] **Step 13: Update `test_cache.py` bot fixture**

Replace the `bot` fixture in `test_cache.py`:

```python
@pytest.fixture
def bot(config, mock_driver):
    with patch("mmbot_framework.core.driver.DriverFactory.create", return_value=mock_driver):
        b = PostBot(config)
    b._team_id = "test-team-id"
    b._bot_username = "testbot"
    b._visible_groups = {"TestGroup": GroupEntry(channels=["ch_id_1", "ch_id_2"], aliases=["tg"])}
    b._private_groups = {"PrivateGroup": GroupEntry(channels=["ch_id_3"], aliases=[])}
    b._whitelist = {
        "ch-id-1": WhitelistEntry(id="ch_id_1", label="ch-id-1", aliases=[]),
        "ch-id-2": WhitelistEntry(id="ch_id_2", label="ch-id-2", aliases=[]),
        "ch-id-3": WhitelistEntry(id="ch_id_3", label="ch-id-3", aliases=[]),
        "whitelisted": WhitelistEntry(id="whitelisted_id", label="whitelisted", aliases=[]),
    }
    b._whitelist_ids = {"ch_id_1", "ch_id_2", "ch_id_3", "whitelisted_id"}
    b._alias_map = {"tg": "TestGroup"}
    return b
```

Add the import at the top of `test_cache.py`:

```python
from bot import GroupEntry, PostBot, WhitelistEntry
```

- [ ] **Step 14: Run all tests**

```bash
cd /Users/philipp/git-repos/mattermost_bots/postbot
uv run pytest -v 2>&1 | tail -20
```

Expected: same 4 pre-existing `TestHandleAddGroup` failures, everything else passes.

- [ ] **Step 15: Commit**

```bash
git add bot.py tests/conftest.py tests/test_bot.py tests/test_cache.py tests/test_aliases.py
git commit -m "feat(postbot): add GroupEntry/WhitelistEntry dataclasses, migrate TOML parser, update all consumers"
```

---

## Task 2: Alias resolution in `_resolve_targets`

With `_alias_map` built in Task 1, this task adds alias lookup to the resolution pipeline and adds tests for it.

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/test_aliases.py`

- [ ] **Step 1: Write failing tests for alias resolution**

Append to `postbot/tests/test_aliases.py`:

```python
# ---------------------------------------------------------------------------
# TestResolveTargetsWithAliases
# ---------------------------------------------------------------------------


class TestResolveTargetsWithAliases:
    """_resolve_targets should resolve group and whitelist aliases."""

    @pytest.fixture
    def bot(self, tmp_path):
        bot = _make_bot(tmp_path, _VALID_TOML)
        bot._load_channel_data()
        bot._team_id = "team1"
        bot.driver = MagicMock()
        # Seed the channel cache so by_name lookups work.
        from mmbot_framework.core.cache import CacheManager
        bot.cache = CacheManager()
        bot.cache.register(
            "channels",
            lambda: {},
            ttl=3600,
        )
        # Manually set cache data.
        entry = bot.cache._entries["channels"]
        entry.data = {
            "by_id": {
                "ch_id_1": {"display_name": "Channel 1", "name": "ch-1"},
                "ch_id_2": {"display_name": "Channel 2", "name": "ch-2"},
            },
            "by_name": {"ch-1": "ch_id_1", "ch-2": "ch_id_2"},
            "all_rows": [],
        }
        import time
        entry.loaded_at = time.time()
        return bot

    def test_group_alias_expands_to_channel_ids(self, bot):
        valid_ids, valid_names, invalid, _ = bot._resolve_targets({"tg"})
        assert "ch_id_1" in valid_ids
        assert "ch_id_2" in valid_ids
        assert invalid == []

    def test_group_alias_case_insensitive(self, bot):
        valid_ids, _, _, _ = bot._resolve_targets({"TG"})
        assert "ch_id_1" in valid_ids

    def test_whitelist_alias_resolves_to_channel_id(self, bot):
        valid_ids, _, invalid, _ = bot._resolve_targets({"c1"})
        assert "ch_id_1" in valid_ids
        assert invalid == []

    def test_canonical_group_name_still_works(self, bot):
        valid_ids, _, invalid, _ = bot._resolve_targets({"TestGroup"})
        assert "ch_id_1" in valid_ids
        assert "ch_id_2" in valid_ids

    def test_unknown_input_ends_up_invalid(self, bot):
        bot.driver.channels.get_channel_by_name.side_effect = Exception("not found")
        _, _, invalid, _ = bot._resolve_targets({"totally-unknown"})
        assert "totally-unknown" in invalid
```

- [ ] **Step 2: Run tests to see them fail**

```bash
uv run pytest tests/test_aliases.py::TestResolveTargetsWithAliases -v
```

Expected: FAIL — alias inputs fall through to cache/API lookup and end up invalid.

- [ ] **Step 3: Update `_resolve_targets` to check `_alias_map`**

In `_resolve_targets`, find the block that starts `for item in inputs:`. Currently the first check is:

```python
            if stripped in all_groups:
                valid_ids.update(all_groups[stripped].channels)
                logger.debug(...)
```

Add alias resolution **between** the group-name check and the cache lookup. Replace the entire inner `for item in inputs:` loop body:

```python
        for item in inputs:
            stripped = item.strip()
            stripped_lower = stripped.lower()

            # 1. Check canonical group name (case-insensitive).
            group_match = next(
                (name for name in all_groups if name.lower() == stripped_lower),
                None,
            )
            if group_match is not None:
                valid_ids.update(all_groups[group_match].channels)
                logger.debug(
                    f"Resolved group {stripped!r} to {all_groups[group_match].channels}."
                )
                continue

            # 2. Check alias map.
            if stripped_lower in self._alias_map:
                canonical = self._alias_map[stripped_lower]
                if canonical in all_groups:
                    valid_ids.update(all_groups[canonical].channels)
                elif canonical in self._whitelist:
                    wl_id = self._whitelist[canonical].id
                    valid_ids.add(wl_id)
                logger.debug(
                    f"Resolved alias {stripped!r} → {canonical!r}."
                )
                continue

            # 3. Try channel cache by system name.
            clean = stripped_lower.lstrip("#")
            channel_id = (
                ch_cache["by_name"].get(clean) if ch_cache else None
            )

            if channel_id is None:
                # Cache miss: fall back to live API.
                logger.warning(
                    f"Cache miss for {clean!r}; falling back to live API."
                )
                used_fallback = True
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

            if channel_id in self._whitelist_ids:
                valid_ids.add(channel_id)
            else:
                invalid_inputs.add(stripped)
                logger.warning(
                    f"Channel {stripped!r} (resolved to {channel_id!r}) "
                    f"is not in the whitelist."
                )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_aliases.py::TestResolveTargetsWithAliases -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v 2>&1 | tail -15
```

Expected: same 4 pre-existing failures, everything else passes.

- [ ] **Step 6: Commit**

```bash
git add bot.py tests/test_aliases.py
git commit -m "feat(postbot): resolve group and whitelist aliases in _resolve_targets"
```

---

## Task 3: `!channels` aliases column

`_handle_channels` currently uses the pre-built `all_rows` strings. To add an aliases column, it instead iterates `ch_cache["by_id"]` directly and looks up alias data from `_whitelist` at render time.

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/test_aliases.py`

- [ ] **Step 1: Write a failing test for the aliases column**

Append to `postbot/tests/test_aliases.py`:

```python
# ---------------------------------------------------------------------------
# TestHandleChannelsAliasesColumn
# ---------------------------------------------------------------------------


class TestHandleChannelsAliasesColumn:
    @pytest.fixture
    def bot(self, tmp_path):
        content = {
            "whitelist": {
                "ch-id-1": {"id": "ch_id_1", "aliases": ["shortname", "sn"]},
                "ch-id-2": {"id": "ch_id_2", "aliases": []},
            },
            "groups": {},
            "private_groups": {},
        }
        bot = _make_bot(tmp_path, content)
        bot._load_channel_data()
        bot._team_id = "team1"
        bot.driver = MagicMock()
        from mmbot_framework.core.cache import CacheManager
        import time
        bot.cache = CacheManager()
        bot.cache.register("channels", lambda: {}, ttl=3600)
        entry = bot.cache._entries["channels"]
        entry.data = {
            "by_id": {
                "ch_id_1": {
                    "display_name": "Channel One",
                    "name": "channel-one",
                    "team_name": "Team",
                    "team_id": "t1",
                },
                "ch_id_2": {
                    "display_name": "Channel Two",
                    "name": "channel-two",
                    "team_name": "Team",
                    "team_id": "t1",
                },
            },
            "by_name": {},
            "all_rows": [],
        }
        entry.loaded_at = time.time()
        return bot

    @pytest.mark.anyio
    async def test_aliases_column_present_in_header(self, bot, make_msg):
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        reply = bot.driver.posts.create_post.call_args_list[-1][0][0]["message"]
        assert "aliases" in reply

    @pytest.mark.anyio
    async def test_aliases_populated_for_whitelisted_channel(self, bot, make_msg):
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        reply = bot.driver.posts.create_post.call_args_list[-1][0][0]["message"]
        assert "shortname" in reply
        assert "sn" in reply

    @pytest.mark.anyio
    async def test_no_aliases_shows_empty_cell(self, bot, make_msg):
        msg = make_msg(text="!channels")
        await bot._handle_channels(msg)
        reply = bot.driver.posts.create_post.call_args_list[-1][0][0]["message"]
        # ch_id_2 row should exist but its alias cell should be empty
        assert "Channel Two" in reply
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_aliases.py::TestHandleChannelsAliasesColumn -v
```

Expected: FAIL — no `aliases` column in the current reply.

- [ ] **Step 3: Update `_handle_channels` to build rows from `by_id` with aliases column**

Replace the entire `_handle_channels` method:

```python
    async def _handle_channels(self, msg: ParsedMessage) -> None:
        """List all Mattermost channels the bot has access to.

        Reads from the channel cache.  Adds an ``aliases`` column for channels
        that appear in the whitelist with one or more aliases.  If the cache is
        not yet loaded, the user is asked to retry or run ``!refresh_channels``.

        Args:
            msg: The incoming message.
        """
        logger.info(f"User @{msg.sender_name} requested the channel list.")
        ch_cache = self.cache.get("channels")
        if ch_cache is None:
            self._post(
                msg.channel_id,
                "⚠️ Channel cache not yet loaded. Please try again shortly "
                "or run `!refresh_channels`.",
            )
            return

        # Build a channel-ID → alias list map from the whitelist.
        id_to_aliases: dict[str, list[str]] = {
            e.id: e.aliases for e in self._whitelist.values()
        }

        lines = [
            "| display_name | name | ID | team_name | aliases |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for cid, info in ch_cache["by_id"].items():
            aliases = id_to_aliases.get(cid, [])
            aliases_str = ", ".join(f"`{a}`" for a in aliases)
            lines.append(
                f"| `{info['display_name']}` | {info['name']} "
                f"| `{cid}` | {info['team_name']} | {aliases_str} |"
            )
        self._post(msg.channel_id, "\n".join(lines))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_aliases.py::TestHandleChannelsAliasesColumn tests/test_cache.py::TestHandleChannelsWithCache -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -v 2>&1 | tail -15
```

Expected: same 4 pre-existing failures only.

- [ ] **Step 6: Commit**

```bash
git add bot.py tests/test_aliases.py
git commit -m "feat(postbot): add aliases column to !channels output"
```

---

## Task 4: `!add_alias` command, `_save_channel_data`, and fix `_add_group_impl`

This task adds the `!add_alias` command with persistence, introduces `_save_channel_data` as a unified save helper, fixes `_add_group_impl` to use new data types, and repairs the 4 pre-existing `TestHandleAddGroup` test failures.

**Files:**
- Modify: `postbot/bot.py`
- Modify: `postbot/tests/test_bot.py`
- Modify: `postbot/tests/test_aliases.py`

- [ ] **Step 1: Write failing tests for `!add_alias`**

Append to `postbot/tests/test_aliases.py`:

```python
# ---------------------------------------------------------------------------
# TestHandleAddAlias
# ---------------------------------------------------------------------------


class TestHandleAddAlias:
    @pytest.fixture
    def bot(self, tmp_path):
        content = {
            "whitelist": {
                "ch-id-1": {"id": "ch_id_1", "aliases": []},
            },
            "groups": {
                "MyGroup": {"channels": ["ch_id_1"], "aliases": []},
            },
            "private_groups": {},
        }
        bot = _make_bot(tmp_path, content)
        bot._load_channel_data()
        bot.driver = MagicMock()
        return bot

    def _last_post(self, bot) -> str:
        return bot.driver.posts.create_post.call_args_list[-1][0][0]["message"]

    @pytest.mark.anyio
    async def test_add_alias_to_group_succeeds(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias mg MyGroup")))
        assert "mg" in bot._alias_map
        assert bot._alias_map["mg"] == "MyGroup"
        assert "✅" in self._last_post(bot)

    @pytest.mark.anyio
    async def test_add_alias_to_whitelist_succeeds(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias c1 ch-id-1")))
        assert "c1" in bot._alias_map
        assert bot._alias_map["c1"] == "ch-id-1"

    @pytest.mark.anyio
    async def test_duplicate_alias_rejected(self, bot, make_msg):
        bot._alias_map["mg"] = "MyGroup"
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias mg MyGroup")))
        assert "❌" in self._last_post(bot)
        assert "already mapped" in self._last_post(bot)

    @pytest.mark.anyio
    async def test_unknown_target_rejected(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias x NoSuchThing")))
        assert "❌" in self._last_post(bot)
        assert "not found" in self._last_post(bot)

    @pytest.mark.anyio
    async def test_alias_with_space_rejected(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias my alias MyGroup")))
        assert "❌" in self._last_post(bot)

    @pytest.mark.anyio
    async def test_alias_persisted_to_toml(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias mg MyGroup")))
        saved = toml.loads(bot.config.channels_toml_path.read_text())
        assert "mg" in saved["groups"]["MyGroup"]["aliases"]

    @pytest.mark.anyio
    async def test_no_payload_shows_usage(self, bot, make_msg):
        asyncio.run(bot._handle_add_alias(make_msg(text="!add_alias")))
        assert "Usage" in self._last_post(bot)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_aliases.py::TestHandleAddAlias -v
```

Expected: FAIL — `_handle_add_alias` does not exist yet.

- [ ] **Step 3: Add `_save_channel_data` helper to `bot.py`**

Add this method after `_build_alias_map`:

```python
    def _save_channel_data(self) -> None:
        """Write current groups and whitelist state to ``channels.toml``.

        Converts in-memory :class:`GroupEntry` and :class:`WhitelistEntry`
        objects back to plain dicts before serialising with ``toml.dump``.
        """
        data = {
            "whitelist": {
                label: {"id": e.id, "aliases": e.aliases}
                for label, e in self._whitelist.items()
            },
            "groups": {
                name: {"channels": e.channels, "aliases": e.aliases}
                for name, e in self._visible_groups.items()
            },
            "private_groups": {
                name: {"channels": e.channels, "aliases": e.aliases}
                for name, e in self._private_groups.items()
            },
        }
        path: Path = self.config.channels_toml_path
        with path.open("w", encoding="utf-8") as fh:
            toml.dump(data, fh)
        logger.debug(f"Persisted channel data to {path}.")
```

- [ ] **Step 4: Add `_handle_add_alias` to `bot.py`**

Add after `_handle_refresh_channels`:

```python
    async def _handle_add_alias(self, msg: ParsedMessage) -> None:
        """Register a new alias for a group or whitelisted channel.

        Usage: ``!add_alias <alias> <target>``

        ``alias`` must not contain spaces and is stored lowercase.  ``target``
        is the canonical group name or whitelist label of an existing entry.
        Groups take precedence over whitelist labels when names collide.

        Args:
            msg: The incoming message.
        """
        payload = msg.text[len("!add_alias"):].strip()
        if not payload:
            self._post(msg.channel_id, "Usage: `!add_alias <alias> <target>`")
            return

        parts = payload.split(None, 1)
        if len(parts) != 2:
            self._post(msg.channel_id, "Usage: `!add_alias <alias> <target>`")
            return

        alias, target = parts[0].lower(), parts[1].strip()

        if " " in alias:
            self._post(msg.channel_id, "❌ Alias must not contain spaces.")
            return

        if alias in self._alias_map:
            existing = self._alias_map[alias]
            self._post(
                msg.channel_id,
                f"❌ Alias `{alias}` is already mapped to `{existing}`.",
            )
            return

        all_groups: dict[str, GroupEntry] = {
            **self._visible_groups,
            **self._private_groups,
        }
        group_match = next(
            (name for name in all_groups if name.lower() == target.lower()),
            None,
        )
        whitelist_match = next(
            (label for label in self._whitelist if label.lower() == target.lower()),
            None,
        )

        if group_match is None and whitelist_match is None:
            self._post(
                msg.channel_id,
                f"❌ Target `{target}` not found in groups or whitelist.",
            )
            return

        note = ""
        if group_match is not None:
            resolved_target = group_match
            if group_match in self._visible_groups:
                self._visible_groups[group_match].aliases.append(alias)
            else:
                self._private_groups[group_match].aliases.append(alias)
            if whitelist_match is not None:
                note = " (group takes precedence over whitelist label with same name)"
        else:
            resolved_target = whitelist_match
            self._whitelist[whitelist_match].aliases.append(alias)

        self._save_channel_data()
        self._build_alias_map()

        logger.info(
            f"User @{msg.sender_name} added alias {alias!r} → {resolved_target!r}."
        )
        self._post(
            msg.channel_id,
            f"✅ `{alias}` → `{resolved_target}` added.{note}",
        )
```

- [ ] **Step 5: Run the add_alias tests**

```bash
uv run pytest tests/test_aliases.py::TestHandleAddAlias -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Fix `_add_group_impl` to use new data types**

Replace the end of `_add_group_impl` — the part that builds `cleaned` and saves — to convert to `GroupEntry` and use `_save_channel_data`:

Replace this block:

```python
        # Update in-memory state.
        target_dict.update(cleaned)

        # Persist to channels.json.
        path: Path = self.config.channels_toml_path
        with path.open("r", encoding="utf-8") as fh:
            data = toml.load(fh)
        data[json_key] = target_dict
        with path.open("w", encoding="utf-8") as fh:
            toml.dump(data, fh)

        logger.info(
            f"Persisted new groups to {path}: {list(cleaned.keys())}."
        )
        self._post(msg.channel_id, "✅ Group added successfully!")
```

with:

```python
        # Convert to GroupEntry and update in-memory state.
        cleaned_entries = {
            name: GroupEntry(channels=ids, aliases=[])
            for name, ids in cleaned.items()
        }
        target_dict.update(cleaned_entries)

        self._save_channel_data()
        self._build_alias_map()

        logger.info(
            f"Persisted new groups: {list(cleaned.keys())}."
        )
        self._post(msg.channel_id, "✅ Group added successfully!")
```

- [ ] **Step 7: Fix `TestHandleAddGroup` tests in `test_bot.py`**

The 4 pre-existing failures send JSON payloads but the bot uses `toml.loads()`. TOML inline table syntax uses `{key = value}`, not `{"key": value}`. Update all four tests to use TOML inline format:

Replace `test_add_group_valid_json`:

```python
    def test_add_group_valid_json(self, bot: PostBot, make_msg):
        bot.driver.channels.get_channel.return_value = {"id": "ch_id_1"}
        asyncio.run(
            bot._handle_add_group(make_msg(text="!add_group TestGroup = [\"ch_id_1\"]"))
        )
        assert "TestGroup" in bot._visible_groups
        assert "✅" in _last_post(bot)
```

Replace `test_add_group_all_invalid_channels`:

```python
    def test_add_group_all_invalid_channels(self, bot: PostBot, make_msg):
        bot.driver.channels.get_channel.side_effect = Exception("not found")
        asyncio.run(
            bot._handle_add_group(make_msg(text="!add_group BadGroup = [\"invalid_id\"]"))
        )
        assert "BadGroup" not in bot._visible_groups
        assert "❌" in _last_post(bot)
```

Replace `test_add_private_group`:

```python
    def test_add_private_group(self, bot: PostBot, make_msg):
        bot.driver.channels.get_channel.return_value = {"id": "ch_id_1"}
        asyncio.run(
            bot._handle_add_private_group(make_msg(text="!add_private_group PrivNew = [\"ch_id_1\"]"))
        )
        assert "PrivNew" in bot._private_groups
        assert "✅" in _last_post(bot)
```

Replace `test_add_group_payload_parsing_no_lstrip_bug`:

```python
    def test_add_group_payload_parsing_no_lstrip_bug(self, bot: PostBot, make_msg):
        """Payload is parsed with toml.loads, not lstrip. All group names preserved."""
        bot.driver.channels.get_channel.return_value = {"id": "ch_id_1"}
        asyncio.run(
            bot._handle_add_group(make_msg(text="!add_group purple_group = [\"ch_id_1\"]"))
        )
        assert "purple_group" in bot._visible_groups
```

- [ ] **Step 8: Update `_HELP_MESSAGE` to include `!add_alias`**

In `_HELP_MESSAGE`, add after the `!refresh_channels` line:

```python
    "- `!add_alias <alias> <target>` — add a short alias for a group or whitelisted channel\n"
```

- [ ] **Step 9: Run all tests**

```bash
uv run pytest -v 2>&1 | tail -15
```

Expected: **0 failures** (the 4 pre-existing failures are now fixed).

- [ ] **Step 10: Commit**

```bash
git add bot.py tests/test_bot.py tests/test_aliases.py
git commit -m "feat(postbot): add !add_alias command, _save_channel_data helper, fix _add_group_impl and TestHandleAddGroup tests"
```

---

## Task 5: Migrate `channels.toml` and update docs

One-time migration of the real `channels.toml` to the new schema, plus README update. No new tests — the bot's startup validation will catch any mistakes.

**Files:**
- Modify: `postbot/channels.toml`
- Modify: `postbot/README.md`

- [ ] **Step 1: Rewrite `channels.toml` to the new schema**

Convert every entry. Keep all existing channel IDs and group names unchanged. Add empty `aliases = []` to every entry — users will add aliases via `!add_alias` at runtime. Here is the structure to follow (fill in the real IDs from the current file):

```toml
[whitelist.bot-test1]
id = "z46ifxzefinut86nycbzzontao"
aliases = []

[whitelist.bot-test2]
id = "34ep73q6kprb8c57bps8xsm7rr"
aliases = []

# ... one [whitelist.<label>] block per existing whitelist ID

[groups."ALLE Cluster Briefkästen"]
channels = ["wjkwhihmb38gjdfhesaqqm64ra", "3r3hg497o788tbe5r1xdn357ic", ...]
aliases = []

[groups."Cluster Briefkästen EG"]
channels = [...]
aliases = []

# ... one [groups."<name>"] block per existing group

[private_groups.all-dev]
channels = [...]
aliases = []
```

Labels for whitelist entries (the key after `[whitelist.]`) must be valid TOML bare keys — use only letters, digits, `-`, and `_`. The existing whitelist IDs are opaque strings, so create readable labels (e.g., `bot-test1`, `bot-test2`).

- [ ] **Step 2: Start the bot locally to verify it loads without errors**

```bash
cd /Users/philipp/git-repos/mattermost_bots/postbot
uv run main.py
```

Expected: bot starts, logs show "Loaded N visible groups, M private groups, K whitelist entries." with the correct counts. Press Ctrl+C to stop.

- [ ] **Step 3: Update `postbot/README.md` Bot Commands table**

Add `!add_alias` row after `!refresh_channels`:

```markdown
| `!add_alias <alias> <target>` | Add a short alias for a group or whitelisted channel |
```

- [ ] **Step 4: Commit**

```bash
git add channels.toml README.md
git commit -m "feat(postbot): migrate channels.toml to new schema, document !add_alias command"
```
