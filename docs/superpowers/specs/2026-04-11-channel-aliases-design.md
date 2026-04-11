# Channel & Group Aliases Design

**Goal:** Allow users to define short alternative names (aliases) for groups and whitelisted channels in `channels.toml`, so broadcast targets can be typed as `cluster` instead of `"ALLE Cluster Briefkästen"`.

**Architecture:** Migrate `channels.toml` to a richer table format that embeds optional `aliases` arrays inline with each entry. `PostBot` builds an `_alias_map` at load time for O(1) case-insensitive resolution. A new `!add_alias` command lets users add aliases at runtime (persisted to `channels.toml`). Aliases are shown inline in `!get_groups` and `!channels` output.

**Tech Stack:** Python 3.14, tomllib / tomli_w, mmbot_framework (existing), postbot (existing).

---

## Scope

One component changes: **`postbot`** — new TOML schema, data model, resolution logic, display changes, and `!add_alias` command. `mmbot_framework` is unchanged.

---

## `channels.toml` Schema

Both `[groups]` / `[private_groups]` and `[whitelist]` migrate from flat value assignments to TOML table-of-tables. `aliases` is always optional.

### Before

```toml
whitelist = ["z46ifx...", "34ep73q6..."]

[groups]
"ALLE Cluster Briefkästen" = ["id1", "id2"]
"Cluster Briefkästen EG"   = ["id3", "id4"]

[private_groups]
all-dev = ["id5", "id6"]
```

### After

```toml
[whitelist.bot-test1]
id = "z46ifxzefinut86nycbzzontao"
aliases = ["test1", "t1"]

[whitelist.main-channel]
id = "14d9s71is3fh3duwj9a6u9k4jr"
# aliases is optional — omit or leave empty

[groups."ALLE Cluster Briefkästen"]
channels = ["id1", "id2"]
aliases = ["cluster", "alle"]

[groups."Cluster Briefkästen EG"]
channels = ["id3", "id4"]
aliases = ["eg"]

[private_groups.all-dev]
channels = ["id5", "id6"]
aliases = ["dev"]
```

### Rules

- **Group canonical name** — the TOML table key (may be quoted for spaces/special chars). Unchanged from the current group names; existing broadcasts that spell out the full name continue to work.
- **Whitelist label** — the TOML table key (e.g. `bot-test1`). Used only for display in `!channels` and as the target argument to `!add_alias`. It is **not** a valid broadcast target; only the `id`, channel system name, and aliases resolve to the channel.
- **`aliases`** — list of strings. Case-insensitive at resolution time. Stored lowercase in `channels.toml`.
- **Collision** — if the same alias is defined on two entries, the bot logs a warning at startup and the first definition wins (TOML file order).
- **Old format detection** — if `channels.toml` contains a flat `whitelist = [...]` array or flat `"Name" = [...]` group entries, the bot logs a clear error and exits. No silent fallback.

---

## Data Model

### Dataclasses (`postbot/bot.py`)

```python
from dataclasses import dataclass, field

@dataclass
class GroupEntry:
    channels: list[str]
    aliases: list[str] = field(default_factory=list)

@dataclass
class WhitelistEntry:
    id: str
    label: str            # TOML key, for display only
    aliases: list[str] = field(default_factory=list)
```

### PostBot instance attributes

| Attribute | Type | Description |
|---|---|---|
| `_visible_groups` | `dict[str, GroupEntry]` | Group name → entry (public groups) |
| `_private_groups` | `dict[str, GroupEntry]` | Group name → entry (private groups) |
| `_whitelist` | `dict[str, WhitelistEntry]` | Label → entry |
| `_alias_map` | `dict[str, str]` | Alias (lowercase) → canonical group name or whitelist label |

`_alias_map` is rebuilt by `_build_alias_map()` whenever `channels.toml` is loaded or modified.

### `_build_alias_map()`

Iterates all groups (visible + private) and whitelist entries. For each alias, inserts `alias.lower() → canonical_name`. On collision, logs a warning and skips the duplicate.

---

## Resolution Changes

### `_resolve_targets(inputs)`

Updated lookup order (case-insensitive throughout):

1. Input matches a **group canonical name** (in `_visible_groups` or `_private_groups`) → expand to channel IDs.
2. Input matches an **alias** in `_alias_map` → retrieve the canonical name, then:
   - If canonical name is in `_visible_groups` or `_private_groups` → expand to channel IDs.
   - Otherwise canonical name is a whitelist label → use `_whitelist[label].id`.
3. Input matches a **channel system name** (via cache `by_name`) → resolve to channel ID.
4. **Cache miss** → live API call, then treat as raw ID.

After resolution, IDs are validated against the whitelist set (all `WhitelistEntry.id` values) as before.

### `_load_channel_data()`

Parses the new TOML schema into `GroupEntry` / `WhitelistEntry` objects. After loading, calls `_build_alias_map()`. Raises a descriptive `ValueError` if the old flat format is detected.

---

## `!add_alias` Command

**Syntax:** `!add_alias <alias> <target>`

- `alias` — the new shortcut (no spaces; stored lowercase)
- `target` — canonical group name or whitelist label of an existing entry

**Behaviour:**

1. Validate `alias` contains no whitespace.
2. Check `alias.lower()` is not already in `_alias_map` → reply with error if so.
3. Look up `target` in groups (visible then private), then whitelist labels → reply with error if not found.
4. Append `alias.lower()` to the entry's `aliases` list and rewrite `channels.toml`.
5. Call `_build_alias_map()` to apply the change immediately (no restart needed).
6. Reply: `` `cluster` → "ALLE Cluster Briefkästen" added. ``

If `target` matches both a group name and a whitelist label (collision), groups take precedence and the reply notes this.

---

## Display Changes

### `!get_groups` / `!get_private_groups`

Groups with aliases show `(aka: ...)` inline:

```
**ALLE Cluster Briefkästen** (aka: `cluster`, `alle`): ch-name1, ch-name2
**Cluster Briefkästen EG** (aka: `eg`): ch-name3
**Cluster Briefkästen 1. OG**: ch-name4, ch-name5
```

Groups with no aliases display as before.

### `!channels`

Adds an `aliases` column to the Markdown table. When building the reply, each row's channel ID is matched against `WhitelistEntry.id` values to find its aliases. Alias data comes from `_whitelist` at render time (not from the API cache), so `all_rows` remains a clean API-only structure. Channels that are not in the whitelist show an empty aliases cell.

```
| display_name | name | ID | team_name | aliases |
| :--- | :--- | :--- | :--- | :--- |
| Bot Test 1 | bot-test1 | z46ifx... | Team | test1, t1 |
| Town Square | town-square | 14d9s7... | Team | |
```

---

## `channels.toml` Migration

The existing `channels.toml` must be migrated to the new format before the bot is started with the new code. The implementation plan includes a one-time migration of the real `channels.toml` file as an explicit step.

---

## Testing

- **TOML parsing** — valid new format, missing `aliases` key, old flat format raises `ValueError`.
- **`_build_alias_map`** — aliases registered correctly, collision logged + skipped.
- **`_resolve_targets`** — group alias resolves to correct IDs, whitelist alias resolves to correct ID, non-alias inputs unchanged.
- **`!add_alias`** — happy path, duplicate alias rejected, unknown target rejected, persisted to TOML and map rebuilt.
- **`!get_groups` display** — entry with aliases shows `(aka: ...)`, entry without does not.
- **`!channels` display** — aliases column present, populated for entries with aliases, empty for entries without.
