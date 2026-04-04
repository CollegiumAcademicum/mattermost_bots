# Mattermost Bot Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `mmbot_framework`, a shared Python library that provides config loading, a `BaseBot` class with lifecycle hooks, decorator- and class-based command routing, an async middleware pipeline, and TTL-based session management for all bots in this monorepo.

**Architecture:** Layered package (`config/`, `core/`, `routing/`, `middleware/`) installed as a local uv dependency alongside `postbot`. Each layer has one responsibility and a clean interface. `BaseBot` wires all layers together; developers subclass it or use it directly with decorators.

**Tech Stack:** Python 3.14, `pydantic` v2, `python-dotenv`, `tomllib` (stdlib), `mattermostdriver`, `pytest`, `pytest-asyncio`

---

## File Map

| File | Responsibility |
|---|---|
| `mmbot_framework/pyproject.toml` | Package metadata + dependencies |
| `mmbot_framework/mmbot_framework/__init__.py` | Public API re-exports |
| `mmbot_framework/mmbot_framework/config/schema.py` | `BotConfig` Pydantic model + `ConfigError` |
| `mmbot_framework/mmbot_framework/config/loader.py` | `ConfigLoader.from_file()` + `.auto_detect()` |
| `mmbot_framework/mmbot_framework/config/__init__.py` | Re-exports `BotConfig`, `ConfigError`, `ConfigLoader` |
| `mmbot_framework/mmbot_framework/core/message.py` | `ParsedMessage` dataclass + `.from_raw()` parser |
| `mmbot_framework/mmbot_framework/core/driver.py` | `DriverFactory.create()` |
| `mmbot_framework/mmbot_framework/core/session.py` | `Session` dataclass + `SessionManager` |
| `mmbot_framework/mmbot_framework/core/bot.py` | `BaseBot` — wires config, driver, sessions, routing, middleware |
| `mmbot_framework/mmbot_framework/core/__init__.py` | Re-exports core public types |
| `mmbot_framework/mmbot_framework/routing/dispatcher.py` | `CommandDispatcher` + `command` class decorator |
| `mmbot_framework/mmbot_framework/routing/__init__.py` | Re-exports `CommandDispatcher`, `command` |
| `mmbot_framework/mmbot_framework/middleware/pipeline.py` | `MiddlewarePipeline` + `LoggingMiddleware` + `IgnoreSelfMiddleware` |
| `mmbot_framework/mmbot_framework/middleware/__init__.py` | Re-exports middleware types |
| `mmbot_framework/tests/test_config.py` | Tests for `BotConfig` + `ConfigLoader` |
| `mmbot_framework/tests/test_message.py` | Tests for `ParsedMessage.from_raw()` |
| `mmbot_framework/tests/test_driver.py` | Tests for `DriverFactory` |
| `mmbot_framework/tests/test_session.py` | Tests for `Session` + `SessionManager` |
| `mmbot_framework/tests/test_dispatcher.py` | Tests for `CommandDispatcher` + `command` decorator |
| `mmbot_framework/tests/test_middleware.py` | Tests for `MiddlewarePipeline` + built-in middlewares |
| `mmbot_framework/tests/test_bot.py` | Tests for `BaseBot` command registration + `reply` |
| `mmbot_framework/README.md` | Developer documentation |
| `pyproject.toml` *(modify)* | Add `mmbot-framework` as local dependency |

---

## Task 1: Scaffold Package Structure

**Files:**
- Create: `mmbot_framework/pyproject.toml`
- Create: `mmbot_framework/mmbot_framework/__init__.py`
- Create: `mmbot_framework/mmbot_framework/config/__init__.py`
- Create: `mmbot_framework/mmbot_framework/core/__init__.py`
- Create: `mmbot_framework/mmbot_framework/routing/__init__.py`
- Create: `mmbot_framework/mmbot_framework/middleware/__init__.py`
- Create: `mmbot_framework/tests/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p mmbot_framework/mmbot_framework/config
mkdir -p mmbot_framework/mmbot_framework/core
mkdir -p mmbot_framework/mmbot_framework/routing
mkdir -p mmbot_framework/mmbot_framework/middleware
mkdir -p mmbot_framework/tests
```

Run from `/Users/philipp/git-repos/mattermost_bots/`.

- [ ] **Step 2: Create `mmbot_framework/pyproject.toml`**

```toml
[project]
name = "mmbot-framework"
version = "0.1.0"
description = "Shared framework for building Mattermost bots"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "mattermostdriver>=7.3.2",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["mmbot_framework"]

[tool.pytest.ini_options]
pythonpath = "."
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create each of the following files with empty content (just a newline):
- `mmbot_framework/mmbot_framework/__init__.py`
- `mmbot_framework/mmbot_framework/config/__init__.py`
- `mmbot_framework/mmbot_framework/core/__init__.py`
- `mmbot_framework/mmbot_framework/routing/__init__.py`
- `mmbot_framework/mmbot_framework/middleware/__init__.py`
- `mmbot_framework/tests/__init__.py`

- [ ] **Step 4: Add `mmbot-framework` to the root `pyproject.toml`**

In `/Users/philipp/git-repos/mattermost_bots/pyproject.toml`, add `mmbot-framework` to `dependencies` and `[tool.uv.sources]`:

```toml
[project]
name = "mattermost-bots"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "mailman",
    "mmbot-framework",
]

[tool.uv.sources]
mailman = { path = "postbot" }
mmbot-framework = { path = "mmbot_framework" }
```

- [ ] **Step 5: Verify uv can resolve the package**

```bash
uv sync
```

Expected: no errors, `mmbot-framework` appears in the resolved lockfile.

- [ ] **Step 6: Commit**

```bash
git add mmbot_framework/ pyproject.toml uv.lock
git commit -m "feat: scaffold mmbot_framework package structure"
```

---

## Task 2: BotConfig Schema

**Files:**
- Create: `mmbot_framework/mmbot_framework/config/schema.py`
- Create: `mmbot_framework/tests/test_config.py` (schema section)

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_config.py`:

```python
"""Tests for BotConfig schema validation."""

import pytest
from pydantic import ValidationError

from mmbot_framework.config.schema import BotConfig, ConfigError


def _valid_kwargs() -> dict:
    return {"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}


def test_botconfig_defaults():
    config = BotConfig(**_valid_kwargs())
    assert config.scheme == "https"
    assert config.port == 443
    assert config.log_level == "INFO"
    assert config.log_file is None
    assert config.session_ttl_seconds == 3600
    assert config.session_cleanup_interval_seconds == 300


def test_botconfig_custom_values():
    config = BotConfig(
        url="http://localhost",
        token="abc",
        team_name="dev",
        scheme="http",
        port=8065,
        log_level="debug",
        log_file="/tmp/bot.log",
        session_ttl_seconds=600,
        session_cleanup_interval_seconds=60,
    )
    assert config.port == 8065
    assert config.scheme == "http"
    assert config.log_level == "DEBUG"   # normalised to upper
    assert config.session_ttl_seconds == 600


def test_botconfig_missing_url():
    with pytest.raises(ValidationError):
        BotConfig(token="tok", team_name="myteam")


def test_botconfig_missing_token():
    with pytest.raises(ValidationError):
        BotConfig(url="https://mm.example.com", team_name="myteam")


def test_botconfig_missing_team_name():
    with pytest.raises(ValidationError):
        BotConfig(url="https://mm.example.com", token="tok")


def test_botconfig_invalid_log_level():
    with pytest.raises(ValidationError, match="log_level"):
        BotConfig(**_valid_kwargs(), log_level="VERBOSE")


def test_botconfig_log_level_case_insensitive():
    config = BotConfig(**_valid_kwargs(), log_level="warning")
    assert config.log_level == "WARNING"


def test_config_error_is_exception():
    err = ConfigError("something went wrong")
    assert isinstance(err, Exception)
    assert str(err) == "something went wrong"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_config.py -v
```

Expected: `ImportError` — `mmbot_framework.config.schema` does not exist yet.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/config/schema.py`**

```python
"""BotConfig — validated configuration model for a Mattermost bot."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""


class BotConfig(BaseModel):
    """Validated configuration for a Mattermost bot.

    Required fields (must be present in every config source):
        url: Mattermost server URL (e.g. ``https://mattermost.example.com``).
        token: Bot authentication token.
        team_name: Mattermost team name (not display name).

    Optional fields:
        scheme: HTTP scheme. Defaults to ``"https"``.
        port: Server port. Defaults to ``443``.
        log_level: Python log level name. Defaults to ``"INFO"``.
        log_file: Path for rotating file logging. ``None`` means console only.
        session_ttl_seconds: Seconds of inactivity before a session expires. Defaults to ``3600``.
        session_cleanup_interval_seconds: How often the background cleanup task runs. Defaults to ``300``.
    """

    url: str
    token: str
    team_name: str
    scheme: str = "https"
    port: int = 443
    log_level: str = "INFO"
    log_file: str | None = None
    session_ttl_seconds: int = 3600
    session_cleanup_interval_seconds: int = 300

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in valid:
            raise ValueError(
                f"log_level must be one of {sorted(valid)}, got {value!r}"
            )
        return upper
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_config.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/config/schema.py mmbot_framework/tests/test_config.py
git commit -m "feat: add BotConfig schema with validation"
```

---

## Task 3: ConfigLoader

**Files:**
- Create: `mmbot_framework/mmbot_framework/config/loader.py`
- Modify: `mmbot_framework/tests/test_config.py` (append loader tests)

- [ ] **Step 1: Append loader tests to `mmbot_framework/tests/test_config.py`**

Add these imports at the top of the file:

```python
import json
from pathlib import Path
from mmbot_framework.config.loader import ConfigLoader
```

Then append the following test functions:

```python
# ── ConfigLoader tests ───────────────────────────────────────────────────────

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_from_file_env(tmp_path):
    p = _write(tmp_path, ".env", "URL=https://mm.example.com\nTOKEN=tok\nTEAM_NAME=myteam\n")
    config = ConfigLoader.from_file(p)
    assert isinstance(config, BotConfig)
    assert config.url == "https://mm.example.com"
    assert config.token == "tok"


def test_from_file_toml(tmp_path):
    p = _write(
        tmp_path,
        "config.toml",
        'url = "https://mm.example.com"\ntoken = "tok"\nteam_name = "myteam"\n',
    )
    config = ConfigLoader.from_file(p)
    assert config.team_name == "myteam"


def test_from_file_json(tmp_path):
    p = _write(
        tmp_path,
        "config.json",
        json.dumps({"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}),
    )
    config = ConfigLoader.from_file(p)
    assert config.token == "tok"


def test_from_file_unsupported_extension(tmp_path):
    p = _write(tmp_path, "config.yaml", "url: https://mm.example.com")
    with pytest.raises(ConfigError, match="Unsupported"):
        ConfigLoader.from_file(p)


def test_from_file_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        ConfigLoader.from_file("/nonexistent/path/.env")


def test_from_file_missing_required_field(tmp_path):
    p = _write(tmp_path, "config.json", json.dumps({"url": "https://mm.example.com"}))
    with pytest.raises(ConfigError, match="Invalid configuration"):
        ConfigLoader.from_file(p)


def test_auto_detect_prefers_env_over_toml(tmp_path):
    _write(tmp_path, ".env", "URL=https://env.example.com\nTOKEN=tok\nTEAM_NAME=myteam\n")
    _write(tmp_path, "config.toml", 'url = "https://toml.example.com"\ntoken = "tok"\nteam_name = "myteam"\n')
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.url == "https://env.example.com"


def test_auto_detect_falls_back_to_toml(tmp_path):
    _write(tmp_path, "config.toml", 'url = "https://mm.example.com"\ntoken = "tok"\nteam_name = "myteam"\n')
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.url == "https://mm.example.com"


def test_auto_detect_falls_back_to_json(tmp_path):
    _write(
        tmp_path,
        "config.json",
        json.dumps({"url": "https://mm.example.com", "token": "tok", "team_name": "myteam"}),
    )
    config = ConfigLoader.auto_detect(tmp_path)
    assert config.team_name == "myteam"


def test_auto_detect_raises_when_no_file(tmp_path):
    with pytest.raises(ConfigError, match="No config file found"):
        ConfigLoader.auto_detect(tmp_path)


def test_from_file_keys_are_case_insensitive(tmp_path):
    p = _write(
        tmp_path,
        "config.json",
        json.dumps({"URL": "https://mm.example.com", "TOKEN": "tok", "TEAM_NAME": "myteam"}),
    )
    config = ConfigLoader.from_file(p)
    assert config.url == "https://mm.example.com"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_config.py -v -k "loader or from_file or auto_detect"
```

Expected: `ImportError` — `mmbot_framework.config.loader` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/config/loader.py`**

```python
"""ConfigLoader — loads BotConfig from .env, .toml, or .json files."""

from __future__ import annotations

import json
import logging
import tomllib
from pathlib import Path

from dotenv import dotenv_values

from mmbot_framework.config.schema import BotConfig, ConfigError

logger = logging.getLogger(__name__)

_AUTO_DETECT_ORDER = (".env", "config.toml", "config.json")


class ConfigLoader:
    """Loads and validates bot configuration from various file formats.

    Supports ``.env``, ``.toml``, and ``.json`` files. All formats are
    normalised to a :class:`BotConfig` instance.

    Examples::

        # Explicit file — format inferred from extension
        config = ConfigLoader.from_file("config.toml")
        config = ConfigLoader.from_file("settings.json")
        config = ConfigLoader.from_file(".env")

        # Auto-detect — searches cwd for .env → config.toml → config.json
        config = ConfigLoader.auto_detect()
    """

    @classmethod
    def from_file(cls, path: str | Path) -> BotConfig:
        """Load config from an explicit file path.

        The format is inferred from the file name:
        - Files named ``.env`` or ending in ``.env`` use dotenv format.
        - Files ending in ``.toml`` use TOML format.
        - Files ending in ``.json`` use JSON format.

        Args:
            path: Absolute or relative path to the config file.

        Returns:
            A validated :class:`BotConfig` instance.

        Raises:
            ConfigError: If the file does not exist, the format is unsupported,
                or required fields are missing / invalid.
        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {p}")

        logger.debug("Loading config from %s", p)

        suffix = p.suffix.lower()

        if p.name == ".env" or suffix == ".env":
            raw: dict = dict(dotenv_values(p))
        elif suffix == ".toml":
            with p.open("rb") as fh:
                raw = tomllib.load(fh)
        elif suffix == ".json":
            with p.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        else:
            raise ConfigError(
                f"Unsupported config format {suffix!r}. Expected .env, .toml, or .json."
            )

        return cls._build(raw)

    @classmethod
    def auto_detect(cls, directory: str | Path | None = None) -> BotConfig:
        """Auto-detect a config file in *directory* (default: current working directory).

        Searches in this order: ``.env`` → ``config.toml`` → ``config.json``.
        The first file found is used.

        Args:
            directory: Directory to search. Defaults to :func:`Path.cwd`.

        Returns:
            A validated :class:`BotConfig` from the first config file found.

        Raises:
            ConfigError: If no recognised config file exists in the directory.
        """
        search_dir = Path(directory) if directory else Path.cwd()

        for name in _AUTO_DETECT_ORDER:
            candidate = search_dir / name
            if candidate.exists():
                logger.info("Auto-detected config file: %s", candidate)
                return cls.from_file(candidate)

        raise ConfigError(
            f"No config file found in {search_dir}. "
            f"Expected one of: {', '.join(_AUTO_DETECT_ORDER)}"
        )

    @classmethod
    def _build(cls, raw: dict) -> BotConfig:
        """Normalise raw key-value pairs to lowercase and construct a BotConfig."""
        normalised = {k.lower(): v for k, v in raw.items()}
        try:
            return BotConfig(**normalised)
        except Exception as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc
```

- [ ] **Step 4: Run all config tests**

```bash
cd mmbot_framework && uv run pytest tests/test_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/config/loader.py mmbot_framework/tests/test_config.py
git commit -m "feat: add ConfigLoader with .env/.toml/.json support and auto-detection"
```

---

## Task 4: ParsedMessage

**Files:**
- Create: `mmbot_framework/mmbot_framework/core/message.py`
- Create: `mmbot_framework/tests/test_message.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_message.py`:

```python
"""Tests for ParsedMessage.from_raw()."""

import json
import pytest

from mmbot_framework.core.message import ParsedMessage


def _make_raw(
    event: str = "posted",
    user_id: str = "user1",
    channel_id: str = "chan1",
    channel_type: str = "D",
    sender_name: str = "@alice",
    message: str = "hello",
    file_ids: list | None = None,
) -> str:
    post = {
        "user_id": user_id,
        "channel_id": channel_id,
        "message": message,
        "file_ids": file_ids or [],
    }
    return json.dumps(
        {
            "event": event,
            "data": {
                "post": json.dumps(post),
                "channel_type": channel_type,
                "sender_name": sender_name,
            },
        }
    )


def test_from_raw_parses_valid_message():
    msg = ParsedMessage.from_raw(_make_raw())
    assert msg is not None
    assert msg.sender_id == "user1"
    assert msg.sender_name == "alice"   # leading @ stripped
    assert msg.channel_id == "chan1"
    assert msg.channel_type == "D"
    assert msg.text == "hello"
    assert msg.file_ids == []


def test_from_raw_strips_at_from_sender_name():
    msg = ParsedMessage.from_raw(_make_raw(sender_name="@bob"))
    assert msg is not None
    assert msg.sender_name == "bob"


def test_from_raw_trims_text_whitespace():
    msg = ParsedMessage.from_raw(_make_raw(message="  hi there  "))
    assert msg is not None
    assert msg.text == "hi there"


def test_from_raw_includes_file_ids():
    msg = ParsedMessage.from_raw(_make_raw(file_ids=["f1", "f2"]))
    assert msg is not None
    assert msg.file_ids == ["f1", "f2"]


def test_from_raw_returns_none_for_non_posted_event():
    raw = json.dumps({"event": "typing", "data": {}})
    assert ParsedMessage.from_raw(raw) is None


def test_from_raw_returns_none_for_invalid_json():
    assert ParsedMessage.from_raw("not json") is None


def test_from_raw_returns_none_for_missing_user_id():
    post = {"channel_id": "chan1", "message": "hi", "file_ids": []}
    raw = json.dumps({
        "event": "posted",
        "data": {"post": json.dumps(post), "channel_type": "D", "sender_name": "@alice"},
    })
    assert ParsedMessage.from_raw(raw) is None


def test_from_raw_returns_none_for_missing_channel_id():
    post = {"user_id": "user1", "message": "hi", "file_ids": []}
    raw = json.dumps({
        "event": "posted",
        "data": {"post": json.dumps(post), "channel_type": "D", "sender_name": "@alice"},
    })
    assert ParsedMessage.from_raw(raw) is None


def test_from_raw_preserves_raw_payload():
    raw = _make_raw()
    msg = ParsedMessage.from_raw(raw)
    assert msg is not None
    assert msg.raw == json.loads(raw)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_message.py -v
```

Expected: `ImportError` — `mmbot_framework.core.message` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/core/message.py`**

```python
"""ParsedMessage — a structured representation of an incoming Mattermost WebSocket event."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedMessage:
    """A parsed Mattermost ``posted`` WebSocket event.

    Attributes:
        sender_id: Mattermost user ID of the message author.
        sender_name: Username of the author (leading ``@`` stripped).
        channel_id: ID of the channel the message was posted in.
        channel_type: Channel type — ``"D"`` direct, ``"O"`` public, ``"P"`` private group.
        text: Message body, whitespace-trimmed.
        file_ids: List of attached file IDs (empty list if none).
        raw: Original WebSocket payload dict for advanced use.
    """

    sender_id: str
    sender_name: str
    channel_id: str
    channel_type: str
    text: str
    file_ids: list[str]
    raw: dict = field(repr=False)

    @classmethod
    def from_raw(cls, raw_str: str) -> ParsedMessage | None:
        """Parse a WebSocket message string into a :class:`ParsedMessage`.

        Returns ``None`` for non-``posted`` events, malformed JSON, or messages
        missing required fields (``user_id`` or ``channel_id``).

        Args:
            raw_str: Raw JSON string received from the WebSocket.

        Returns:
            A :class:`ParsedMessage` instance, or ``None`` if the message
            should be ignored.
        """
        try:
            payload = json.loads(raw_str)
        except json.JSONDecodeError:
            logger.error("Could not decode WebSocket message: %.200s", raw_str)
            return None

        if payload.get("event") != "posted":
            logger.debug("Ignoring non-post event: %r", payload.get("event"))
            return None

        data = payload.get("data", {})

        try:
            post = json.loads(data.get("post", "{}"))
        except json.JSONDecodeError:
            logger.error("Could not decode nested post payload.")
            return None

        sender_id: str = post.get("user_id", "")
        channel_id: str = post.get("channel_id", "")

        if not sender_id or not channel_id:
            logger.debug("Ignoring message with missing sender_id or channel_id.")
            return None

        return cls(
            sender_id=sender_id,
            sender_name=data.get("sender_name", "").lstrip("@"),
            channel_id=channel_id,
            channel_type=data.get("channel_type", ""),
            text=post.get("message", "").strip(),
            file_ids=post.get("file_ids", []),
            raw=payload,
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_message.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/core/message.py mmbot_framework/tests/test_message.py
git commit -m "feat: add ParsedMessage dataclass with WebSocket parser"
```

---

## Task 5: DriverFactory

**Files:**
- Create: `mmbot_framework/mmbot_framework/core/driver.py`
- Create: `mmbot_framework/tests/test_driver.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_driver.py`:

```python
"""Tests for DriverFactory."""

from unittest.mock import MagicMock, patch

import pytest

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.driver import DriverFactory


def _config(**kwargs) -> BotConfig:
    return BotConfig(url="https://mm.example.com", token="mytoken", team_name="myteam", **kwargs)


def test_driver_factory_passes_correct_params():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        MockDriver.return_value = MagicMock()
        DriverFactory.create(_config())
        MockDriver.assert_called_once_with(
            {"url": "https://mm.example.com", "token": "mytoken", "scheme": "https", "port": 443}
        )


def test_driver_factory_respects_custom_scheme_and_port():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        MockDriver.return_value = MagicMock()
        DriverFactory.create(_config(scheme="http", port=8065))
        call_kwargs = MockDriver.call_args[0][0]
        assert call_kwargs["scheme"] == "http"
        assert call_kwargs["port"] == 8065


def test_driver_factory_does_not_call_login():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        mock_driver = MagicMock()
        MockDriver.return_value = mock_driver
        DriverFactory.create(_config())
        mock_driver.login.assert_not_called()


def test_driver_factory_returns_driver_instance():
    with patch("mmbot_framework.core.driver.Driver") as MockDriver:
        mock_driver = MagicMock()
        MockDriver.return_value = mock_driver
        result = DriverFactory.create(_config())
        assert result is mock_driver
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_driver.py -v
```

Expected: `ImportError` — `mmbot_framework.core.driver` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/core/driver.py`**

```python
"""DriverFactory — constructs a mattermostdriver.Driver from a BotConfig."""

from __future__ import annotations

import logging

from mattermostdriver import Driver

from mmbot_framework.config.schema import BotConfig

logger = logging.getLogger(__name__)


class DriverFactory:
    """Creates :class:`mattermostdriver.Driver` instances from a :class:`BotConfig`.

    The factory does **not** call ``driver.login()`` — that is :class:`BaseBot`'s
    responsibility, keeping this factory pure and easily mockable in tests.
    """

    @staticmethod
    def create(config: BotConfig) -> Driver:
        """Construct a Driver from *config*.

        Args:
            config: Validated bot configuration.

        Returns:
            An uninitialised :class:`mattermostdriver.Driver` ready for login.
        """
        logger.debug(
            "Creating Driver — url=%s scheme=%s port=%s",
            config.url,
            config.scheme,
            config.port,
        )
        return Driver(
            {
                "url": config.url,
                "token": config.token,
                "scheme": config.scheme,
                "port": config.port,
            }
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_driver.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/core/driver.py mmbot_framework/tests/test_driver.py
git commit -m "feat: add DriverFactory"
```

---

## Task 6: Session + SessionManager

**Files:**
- Create: `mmbot_framework/mmbot_framework/core/session.py`
- Create: `mmbot_framework/tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_session.py`:

```python
"""Tests for Session and SessionManager."""

import time
from unittest.mock import patch

import pytest

from mmbot_framework.core.session import Session, SessionManager


def test_get_returns_none_for_unknown_user():
    mgr = SessionManager(ttl_seconds=60)
    assert mgr.get("nobody") is None


def test_get_or_create_returns_new_session():
    mgr = SessionManager(ttl_seconds=60)
    session = mgr.get_or_create("user1")
    assert isinstance(session, Session)
    assert session.sender_id == "user1"
    assert session.ttl_seconds == 60
    assert session.data == {}


def test_get_or_create_returns_same_session_on_repeat_call():
    mgr = SessionManager(ttl_seconds=60)
    s1 = mgr.get_or_create("user1")
    s2 = mgr.get_or_create("user1")
    assert s1 is s2


def test_get_updates_last_active():
    mgr = SessionManager(ttl_seconds=60)
    session = mgr.get_or_create("user1")
    original = session.last_active
    with patch("mmbot_framework.core.session.time.time", return_value=original + 10.0):
        mgr.get("user1")
    assert session.last_active == original + 10.0


def test_get_returns_none_after_ttl_elapsed():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    with patch("mmbot_framework.core.session.time.time", return_value=time.time() + 61.0):
        assert mgr.get("user1") is None


def test_get_or_create_replaces_expired_session():
    mgr = SessionManager(ttl_seconds=60)
    old = mgr.get_or_create("user1")
    old_created = old.created_at
    future = time.time() + 61.0
    with patch("mmbot_framework.core.session.time.time", return_value=future):
        new = mgr.get_or_create("user1")
    assert new is not old
    assert new.created_at == future


def test_session_data_persists_between_accesses():
    mgr = SessionManager(ttl_seconds=60)
    s = mgr.get_or_create("user1")
    s.data["step"] = "awaiting_input"
    s2 = mgr.get("user1")
    assert s2 is not None
    assert s2.data["step"] == "awaiting_input"


def test_clear_removes_session():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    mgr.clear("user1")
    assert mgr.get("user1") is None


def test_clear_nonexistent_user_is_safe():
    mgr = SessionManager(ttl_seconds=60)
    mgr.clear("nobody")  # must not raise


def test_is_alive_true_for_live_session():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    assert mgr.is_alive("user1") is True


def test_is_alive_false_for_expired_session():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    with patch("mmbot_framework.core.session.time.time", return_value=time.time() + 61.0):
        assert mgr.is_alive("user1") is False


def test_is_alive_false_for_unknown_user():
    mgr = SessionManager(ttl_seconds=60)
    assert mgr.is_alive("nobody") is False


def test_is_alive_does_not_update_last_active():
    mgr = SessionManager(ttl_seconds=60)
    s = mgr.get_or_create("user1")
    original = s.last_active
    mgr.is_alive("user1")
    assert s.last_active == original


def test_purge_expired_removes_all_expired_sessions():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    mgr.get_or_create("user2")
    with patch("mmbot_framework.core.session.time.time", return_value=time.time() + 61.0):
        count = mgr.purge_expired()
    assert count == 2


def test_purge_expired_keeps_live_sessions():
    mgr = SessionManager(ttl_seconds=60)
    mgr.get_or_create("user1")
    count = mgr.purge_expired()
    assert count == 0
    assert mgr.is_alive("user1") is True


def test_purge_expired_returns_zero_when_nothing_to_do():
    mgr = SessionManager(ttl_seconds=60)
    assert mgr.purge_expired() == 0
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_session.py -v
```

Expected: `ImportError` — `mmbot_framework.core.session` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/core/session.py`**

```python
"""TTL-based session management for per-user conversation state."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Holds conversation state for a single user.

    Attributes:
        sender_id: Mattermost user ID this session belongs to.
        data: Arbitrary bot-specific state. The bot owns the keys in this dict.
        created_at: Unix timestamp when the session was created.
        last_active: Unix timestamp of the last access via
            :meth:`SessionManager.get` or :meth:`SessionManager.get_or_create`.
            Updated on every access.
        ttl_seconds: Seconds of inactivity after which the session is expired.
    """

    sender_id: str
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    ttl_seconds: int = 3600

    def is_expired(self) -> bool:
        """Return ``True`` if the session has been inactive longer than its TTL."""
        return time.time() - self.last_active > self.ttl_seconds


class SessionManager:
    """Manages TTL-bounded per-user sessions.

    Sessions expire after :attr:`Session.ttl_seconds` seconds of inactivity.
    Expiry is checked lazily on every :meth:`get` / :meth:`get_or_create` call,
    and eagerly by :meth:`purge_expired` (called by the background cleanup task
    inside :class:`BaseBot`).

    Example::

        sessions = SessionManager(ttl_seconds=3600)

        # Retrieve or create a session
        session = sessions.get_or_create("user123")
        session.data["step"] = "awaiting_confirmation"

        # Later: retrieve only if alive
        session = sessions.get("user123")
        if session is None:
            # Session expired — treat as a fresh start
            ...

        # Explicit cleanup after a completed flow
        sessions.clear("user123")
    """

    def __init__(self, ttl_seconds: int) -> None:
        """Args:
            ttl_seconds: Default TTL applied to all newly created sessions.
        """
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, sender_id: str) -> Session | None:
        """Return the live session for *sender_id*, or ``None`` if absent or expired.

        Updates :attr:`Session.last_active` on a live session.

        Args:
            sender_id: Mattermost user ID.

        Returns:
            The live :class:`Session`, or ``None``.
        """
        session = self._sessions.get(sender_id)
        if session is None:
            return None
        if session.is_expired():
            logger.debug("Session for %s expired on access; discarding.", sender_id)
            del self._sessions[sender_id]
            return None
        session.last_active = time.time()
        return session

    def get_or_create(self, sender_id: str) -> Session:
        """Return a live session or create a fresh one.

        If an expired session exists it is cleared before a new one is created,
        so the caller always receives a session with a clean ``data`` dict.

        Args:
            sender_id: Mattermost user ID.

        Returns:
            A live :class:`Session` (possibly newly created).
        """
        existing = self.get(sender_id)
        if existing is not None:
            return existing
        session = Session(sender_id=sender_id, ttl_seconds=self._ttl_seconds)
        self._sessions[sender_id] = session
        logger.debug("Created new session for %s (TTL=%ds).", sender_id, self._ttl_seconds)
        return session

    def clear(self, sender_id: str) -> None:
        """Explicitly delete the session for *sender_id*.

        Safe to call even if no session exists.

        Args:
            sender_id: Mattermost user ID.
        """
        if self._sessions.pop(sender_id, None) is not None:
            logger.debug("Session for %s explicitly cleared.", sender_id)

    def is_alive(self, sender_id: str) -> bool:
        """Return ``True`` if a non-expired session exists for *sender_id*.

        Does **not** update :attr:`Session.last_active`.

        Args:
            sender_id: Mattermost user ID.
        """
        session = self._sessions.get(sender_id)
        return session is not None and not session.is_expired()

    def purge_expired(self) -> int:
        """Remove all expired sessions.

        Called by the background cleanup task in :class:`BaseBot`.

        Returns:
            The number of sessions removed.
        """
        expired = [sid for sid, s in list(self._sessions.items()) if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]
            logger.info("Purged expired session for user %s.", sid)
        return len(expired)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_session.py -v
```

Expected: all 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/core/session.py mmbot_framework/tests/test_session.py
git commit -m "feat: add Session and SessionManager with TTL expiry"
```

---

## Task 7: CommandDispatcher + `command` Decorator

**Files:**
- Create: `mmbot_framework/mmbot_framework/routing/dispatcher.py`
- Create: `mmbot_framework/tests/test_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_dispatcher.py`:

```python
"""Tests for CommandDispatcher and the @command class decorator."""

import pytest

from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.routing.dispatcher import CommandDispatcher, command


def _msg(text: str = "hello") -> ParsedMessage:
    return ParsedMessage(
        sender_id="u1",
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


async def test_dispatch_calls_matching_handler():
    called_with = []

    async def handler(msg: ParsedMessage) -> None:
        called_with.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    result = await dispatcher.dispatch(_msg("!ping"))
    assert result is True
    assert called_with == ["!ping"]


async def test_dispatch_matches_prefix_not_exact():
    called = []

    async def handler(msg):
        called.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.register("!help", handler)
    await dispatcher.dispatch(_msg("!help me please"))
    assert called == ["!help me please"]


async def test_dispatch_is_case_insensitive():
    called = []

    async def handler(msg):
        called.append(True)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    await dispatcher.dispatch(_msg("!PING"))
    assert called == [True]


async def test_dispatch_first_match_wins():
    order = []

    async def h1(msg):
        order.append("h1")

    async def h2(msg):
        order.append("h2")

    dispatcher = CommandDispatcher()
    dispatcher.register("!p", h1)
    dispatcher.register("!ping", h2)
    await dispatcher.dispatch(_msg("!ping"))
    assert order == ["h1"]  # "!p" is a prefix of "!ping"


async def test_dispatch_returns_false_when_no_match():
    dispatcher = CommandDispatcher()
    result = await dispatcher.dispatch(_msg("!unknown"))
    assert result is False


async def test_dispatch_calls_default_handler_on_no_match():
    called = []

    async def fallback(msg):
        called.append(msg.text)

    dispatcher = CommandDispatcher()
    dispatcher.set_default(fallback)
    result = await dispatcher.dispatch(_msg("anything"))
    assert result is True
    assert called == ["anything"]


async def test_dispatch_does_not_call_default_when_command_matched():
    default_called = []

    async def handler(msg):
        pass

    async def fallback(msg):
        default_called.append(True)

    dispatcher = CommandDispatcher()
    dispatcher.register("!ping", handler)
    dispatcher.set_default(fallback)
    await dispatcher.dispatch(_msg("!ping"))
    assert default_called == []


def test_command_decorator_sets_trigger_on_method():
    class MyBot:
        @command("!help")
        async def help_handler(self, msg):
            pass

    assert MyBot.help_handler._command_trigger == "!help"


async def test_command_decorator_methods_are_discovered_by_base_bot():
    """BaseBot.__init__ scans for _command_trigger and registers methods."""
    # We test the scanning logic directly without importing BaseBot to keep this isolated.
    called = []

    class FakeBot:
        def __init__(self):
            self._dispatcher = CommandDispatcher()
            for name in dir(type(self)):
                method = getattr(type(self), name, None)
                if callable(method) and hasattr(method, "_command_trigger"):
                    bound = getattr(self, name)
                    self._dispatcher.register(method._command_trigger, bound)

        @command("!ping")
        async def ping(self, msg):
            called.append(msg.text)

    bot = FakeBot()
    await bot._dispatcher.dispatch(_msg("!ping"))
    assert called == ["!ping"]
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_dispatcher.py -v
```

Expected: `ImportError` — `mmbot_framework.routing.dispatcher` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/routing/dispatcher.py`**

```python
"""Command routing — maps trigger strings to async handler functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from mmbot_framework.core.message import ParsedMessage

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


def command(trigger: str) -> Callable[[Handler], Handler]:
    """Class-level decorator that registers a method as a command handler.

    Use this inside a :class:`BaseBot` subclass to define commands::

        class MyBot(BaseBot):
            @command("!help")
            async def help_handler(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "Help text here...")

    :class:`BaseBot` discovers these methods in ``__init__`` and registers
    them automatically with its :class:`CommandDispatcher`.

    Args:
        trigger: Prefix to match (case-insensitive ``startswith``).

    Returns:
        The original method unchanged. The trigger is attached as
        ``method._command_trigger``.
    """

    def decorator(fn: Handler) -> Handler:
        fn._command_trigger = trigger  # type: ignore[attr-defined]
        return fn

    return decorator


class CommandDispatcher:
    """Routes incoming messages to registered async handler functions.

    Matching uses ``msg.text.lower().startswith(trigger)`` checked in
    registration order. The first match wins.

    Can be used standalone or via :class:`BaseBot`::

        dispatcher = CommandDispatcher()
        dispatcher.register("!ping", ping_handler)
        matched = await dispatcher.dispatch(msg)
    """

    def __init__(self) -> None:
        self._commands: list[tuple[str, Handler]] = []
        self._default: Handler | None = None

    def register(self, trigger: str, handler: Handler) -> None:
        """Register *handler* for messages starting with *trigger*.

        Args:
            trigger: Prefix string (case-insensitive).
            handler: Async callable ``(msg: ParsedMessage) -> None``.
        """
        logger.debug("Registering command handler for trigger %r.", trigger)
        self._commands.append((trigger.lower(), handler))

    def set_default(self, handler: Handler) -> None:
        """Set the fallback handler invoked when no command matches.

        Equivalent to overriding :meth:`BaseBot.on_message`.

        Args:
            handler: Async callable ``(msg: ParsedMessage) -> None``.
        """
        self._default = handler

    async def dispatch(self, msg: ParsedMessage) -> bool:
        """Dispatch *msg* to the first matching handler.

        Args:
            msg: The parsed incoming message.

        Returns:
            ``True`` if a handler (or the default) was invoked,
            ``False`` if no command matched and no default is set.
        """
        text_lower = msg.text.lower()

        for trigger, handler in self._commands:
            if text_lower.startswith(trigger):
                logger.debug("Matched trigger %r for message %r.", trigger, msg.text[:50])
                await handler(msg)
                return True

        if self._default is not None:
            logger.debug("No command matched; invoking default handler.")
            await self._default(msg)
            return True

        logger.debug("No command matched and no default handler registered.")
        return False
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_dispatcher.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/routing/dispatcher.py mmbot_framework/tests/test_dispatcher.py
git commit -m "feat: add CommandDispatcher and @command class decorator"
```

---

## Task 8: MiddlewarePipeline + Built-in Middlewares

**Files:**
- Create: `mmbot_framework/mmbot_framework/middleware/pipeline.py`
- Create: `mmbot_framework/tests/test_middleware.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_middleware.py`:

```python
"""Tests for MiddlewarePipeline, LoggingMiddleware, and IgnoreSelfMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.middleware.pipeline import (
    IgnoreSelfMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
)


def _msg(sender_id: str = "u1", text: str = "hello") -> ParsedMessage:
    return ParsedMessage(
        sender_id=sender_id,
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


async def test_pipeline_calls_endpoint_when_no_middleware():
    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    msg = _msg()
    await pipeline.run(msg, endpoint)
    endpoint.assert_awaited_once_with(msg)


async def test_pipeline_calls_middleware_in_order():
    order = []

    async def mw1(msg, next):
        order.append("mw1")
        await next(msg)

    async def mw2(msg, next):
        order.append("mw2")
        await next(msg)

    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    pipeline.add(mw1)
    pipeline.add(mw2)
    await pipeline.run(_msg(), endpoint)
    assert order == ["mw1", "mw2"]
    endpoint.assert_awaited_once()


async def test_pipeline_short_circuits_when_next_not_called():
    endpoint = AsyncMock()
    second_mw = AsyncMock()

    async def guard(msg, next):
        return  # does not call next

    pipeline = MiddlewarePipeline()
    pipeline.add(guard)
    pipeline.add(second_mw)
    await pipeline.run(_msg(), endpoint)
    endpoint.assert_not_awaited()
    second_mw.assert_not_awaited()


async def test_pipeline_middleware_can_modify_message():
    received = []

    async def mw(msg, next):
        modified = ParsedMessage(
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            channel_id=msg.channel_id,
            channel_type=msg.channel_type,
            text=msg.text.upper(),
            file_ids=msg.file_ids,
            raw=msg.raw,
        )
        await next(modified)

    async def endpoint(msg):
        received.append(msg.text)

    pipeline = MiddlewarePipeline()
    pipeline.add(mw)
    await pipeline.run(_msg(text="hello"), endpoint)
    assert received == ["HELLO"]


async def test_logging_middleware_calls_next():
    endpoint = AsyncMock()
    pipeline = MiddlewarePipeline()
    pipeline.add(LoggingMiddleware())
    await pipeline.run(_msg(), endpoint)
    endpoint.assert_awaited_once()


async def test_ignore_self_middleware_drops_bot_messages():
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = "bot123"

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="bot123"), endpoint)
    endpoint.assert_not_awaited()


async def test_ignore_self_middleware_passes_other_users():
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = "bot123"

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="user456"), endpoint)
    endpoint.assert_awaited_once()


async def test_ignore_self_middleware_passes_when_bot_id_not_set():
    """Before login, _bot_id is None — messages should pass through."""
    endpoint = AsyncMock()

    fake_bot = MagicMock()
    fake_bot._bot_id = None

    pipeline = MiddlewarePipeline()
    pipeline.add(IgnoreSelfMiddleware(fake_bot))
    await pipeline.run(_msg(sender_id="anyuser"), endpoint)
    endpoint.assert_awaited_once()
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_middleware.py -v
```

Expected: `ImportError` — `mmbot_framework.middleware.pipeline` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/middleware/pipeline.py`**

```python
"""Async middleware pipeline and built-in middlewares."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from mmbot_framework.core.bot import BaseBot
    from mmbot_framework.core.message import ParsedMessage

logger = logging.getLogger(__name__)

MiddlewareFn = Callable[["ParsedMessage", Callable], Awaitable[None]]
EndpointFn = Callable[["ParsedMessage"], Awaitable[None]]


class MiddlewarePipeline:
    """Chains async middleware functions before a terminal endpoint.

    Each middleware has the signature::

        async def my_middleware(msg: ParsedMessage, next: Callable) -> None:
            # pre-processing
            await next(msg)   # forward to the next middleware or endpoint
            # post-processing (optional)

    Not calling ``next`` **short-circuits** the chain — no further middleware
    or the endpoint will be called. This is useful for guards (auth, rate limiting, etc.).

    Example::

        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware())
        pipeline.add(IgnoreSelfMiddleware(bot))
        await pipeline.run(msg, dispatcher.dispatch)
    """

    def __init__(self) -> None:
        self._middlewares: list[MiddlewareFn] = []

    def add(self, middleware: MiddlewareFn) -> None:
        """Append *middleware* to the chain.

        Middleware is executed in the order it is added.

        Args:
            middleware: Async callable ``(msg, next) -> None``.
        """
        self._middlewares.append(middleware)

    async def run(self, msg: ParsedMessage, endpoint: EndpointFn) -> None:
        """Execute the middleware chain, terminating at *endpoint*.

        Args:
            msg: The incoming parsed message.
            endpoint: Final async callable invoked after all middleware passes.
        """
        index = 0

        async def _next(current_msg: ParsedMessage) -> None:
            nonlocal index
            if index < len(self._middlewares):
                mw = self._middlewares[index]
                index += 1
                await mw(current_msg, _next)
            else:
                await endpoint(current_msg)

        await _next(msg)


class LoggingMiddleware:
    """Logs every incoming message at DEBUG level and passes it through.

    Logs the sender name, channel ID, channel type, and a truncated message body.

    Example::

        bot.add_middleware(LoggingMiddleware())
    """

    async def __call__(self, msg: ParsedMessage, next: Callable) -> None:
        logger.debug(
            "Incoming message — sender=%s channel=%s (%s): %.100r",
            msg.sender_name,
            msg.channel_id,
            msg.channel_type,
            msg.text,
        )
        await next(msg)


class IgnoreSelfMiddleware:
    """Drops messages sent by the bot itself.

    You almost always want this as the first middleware so the bot does not
    react to its own posts and enter a feedback loop.

    Example::

        bot.add_middleware(IgnoreSelfMiddleware(bot))
    """

    def __init__(self, bot: BaseBot) -> None:
        """Args:
            bot: The :class:`BaseBot` instance. Its ``_bot_id`` is read at
                message-handling time, so it is safe to add this middleware
                before ``run()`` is called.
        """
        self._bot = bot

    async def __call__(self, msg: ParsedMessage, next: Callable) -> None:
        if self._bot._bot_id is not None and msg.sender_id == self._bot._bot_id:
            logger.debug("Dropping message from self (bot_id=%s).", self._bot._bot_id)
            return
        await next(msg)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_middleware.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mmbot_framework/mmbot_framework/middleware/pipeline.py mmbot_framework/tests/test_middleware.py
git commit -m "feat: add MiddlewarePipeline, LoggingMiddleware, IgnoreSelfMiddleware"
```

---

## Task 9: BaseBot

**Files:**
- Create: `mmbot_framework/mmbot_framework/core/bot.py`
- Create: `mmbot_framework/tests/test_bot.py`

- [ ] **Step 1: Write the failing tests**

Create `mmbot_framework/tests/test_bot.py`:

```python
"""Tests for BaseBot — command registration, reply, middleware wiring."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.bot import BaseBot
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.routing.dispatcher import command


def _config(**kwargs) -> BotConfig:
    return BotConfig(url="https://mm.example.com", token="tok", team_name="myteam", **kwargs)


def _msg(text: str = "hello", sender_id: str = "u1") -> ParsedMessage:
    return ParsedMessage(
        sender_id=sender_id,
        sender_name="alice",
        channel_id="c1",
        channel_type="D",
        text=text,
        file_ids=[],
        raw={},
    )


def _make_bot(config: BotConfig | None = None) -> BaseBot:
    """Return a BaseBot with a mocked Driver (no network calls)."""
    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = BaseBot(config or _config())
    return bot


def test_bot_exposes_sessions():
    bot = _make_bot()
    from mmbot_framework.core.session import SessionManager
    assert isinstance(bot.sessions, SessionManager)


async def test_instance_command_decorator_registers_handler():
    bot = _make_bot()
    called = []

    @bot.command("!ping")
    async def ping(msg: ParsedMessage) -> None:
        called.append(msg.text)

    await bot._dispatcher.dispatch(_msg("!ping"))
    assert called == ["!ping"]


async def test_instance_default_handler_decorator():
    bot = _make_bot()
    called = []

    @bot.default_handler
    async def fallback(msg: ParsedMessage) -> None:
        called.append(msg.text)

    await bot._dispatcher.dispatch(_msg("!unknown"))
    assert called == ["!unknown"]


async def test_class_command_decorator_registered_on_init():
    called = []

    class MyBot(BaseBot):
        @command("!greet")
        async def greet(self, msg: ParsedMessage) -> None:
            called.append(msg.text)

    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = MyBot(_config())

    await bot._dispatcher.dispatch(_msg("!greet world"))
    assert called == ["!greet world"]


async def test_reply_calls_driver_posts_create_post():
    bot = _make_bot()
    msg = _msg()
    await bot.reply(msg, "hi there")
    bot.driver.posts.create_post.assert_called_once_with(
        {"channel_id": "c1", "message": "hi there"}
    )


async def test_add_middleware_appends_to_pipeline():
    bot = _make_bot()
    called = []

    async def mw(msg, next):
        called.append("mw")
        await next(msg)

    bot.add_middleware(mw)

    endpoint = AsyncMock()
    await bot._pipeline.run(_msg(), endpoint)
    assert called == ["mw"]
    endpoint.assert_awaited_once()


async def test_on_start_is_noop_by_default():
    bot = _make_bot()
    await bot.on_start()   # must not raise


async def test_on_stop_is_noop_by_default():
    bot = _make_bot()
    await bot.on_stop()    # must not raise


async def test_on_message_is_noop_by_default():
    bot = _make_bot()
    await bot.on_message(_msg())   # must not raise


async def test_dispatch_falls_through_to_on_message():
    received = []

    class MyBot(BaseBot):
        async def on_message(self, msg: ParsedMessage) -> None:
            received.append(msg.text)

    with patch("mmbot_framework.core.bot.DriverFactory") as MockFactory:
        MockFactory.create.return_value = MagicMock()
        bot = MyBot(_config())

    await bot._dispatch(_msg("unmatched"))
    assert received == ["unmatched"]
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd mmbot_framework && uv run pytest tests/test_bot.py -v
```

Expected: `ImportError` — `mmbot_framework.core.bot` does not exist.

- [ ] **Step 3: Implement `mmbot_framework/mmbot_framework/core/bot.py`**

```python
"""BaseBot — the central class for building Mattermost bots."""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import threading
from typing import Callable

from mmbot_framework.config.schema import BotConfig
from mmbot_framework.core.driver import DriverFactory
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.core.session import SessionManager
from mmbot_framework.middleware.pipeline import MiddlewarePipeline
from mmbot_framework.routing.dispatcher import CommandDispatcher

logger = logging.getLogger(__name__)


class BaseBot:
    """Base class for Mattermost bots.

    Subclass it to define commands and lifecycle hooks, or use it directly
    with instance decorators.

    **Subclass example (class-based commands):**

    .. code-block:: python

        from mmbot_framework import BaseBot, BotConfig, ParsedMessage
        from mmbot_framework.config import ConfigLoader
        from mmbot_framework.routing import command
        from mmbot_framework.middleware import LoggingMiddleware, IgnoreSelfMiddleware

        class MyBot(BaseBot):
            async def on_start(self) -> None:
                print("Bot is ready!")

            @command("!ping")
            async def ping(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "pong")

            async def on_message(self, msg: ParsedMessage) -> None:
                await self.reply(msg, "I don't understand that command.")

        config = ConfigLoader.auto_detect()
        bot = MyBot(config)
        bot.add_middleware(IgnoreSelfMiddleware(bot))
        bot.add_middleware(LoggingMiddleware())
        bot.run()

    **Decorator example (instance-based commands):**

    .. code-block:: python

        config = ConfigLoader.auto_detect()
        bot = BaseBot(config)

        @bot.command("!ping")
        async def ping(msg: ParsedMessage) -> None:
            await bot.reply(msg, "pong")

        @bot.default_handler
        async def fallback(msg: ParsedMessage) -> None:
            await bot.reply(msg, "Unknown command.")

        bot.add_middleware(IgnoreSelfMiddleware(bot))
        bot.run()
    """

    def __init__(self, config: BotConfig) -> None:
        """Args:
            config: Validated bot configuration. Use :class:`ConfigLoader` to build one.
        """
        self.config = config
        self.driver = DriverFactory.create(config)
        self.sessions = SessionManager(ttl_seconds=config.session_ttl_seconds)
        self._dispatcher = CommandDispatcher()
        self._pipeline = MiddlewarePipeline()
        self._bot_id: str | None = None

        # Discover class-level @command-decorated methods and register them.
        for name in dir(type(self)):
            method = getattr(type(self), name, None)
            if callable(method) and hasattr(method, "_command_trigger"):
                bound = getattr(self, name)
                self._dispatcher.register(method._command_trigger, bound)

    # ── Public registration API ─────────────────────────────────────────────

    def command(self, trigger: str) -> Callable:
        """Instance decorator: register an async function as a command handler.

        Use this when you prefer a functional style over subclassing::

            @bot.command("!help")
            async def help_handler(msg: ParsedMessage) -> None:
                await bot.reply(msg, "Help text here...")

        Args:
            trigger: Prefix string to match (case-insensitive ``startswith``).

        Returns:
            A decorator that registers the function and returns it unchanged.
        """

        def decorator(fn: Callable) -> Callable:
            self._dispatcher.register(trigger, fn)
            return fn

        return decorator

    @property
    def default_handler(self) -> Callable:
        """Instance decorator: register the fallback handler for unmatched messages.

        Equivalent to overriding :meth:`on_message` in a subclass::

            @bot.default_handler
            async def fallback(msg: ParsedMessage) -> None:
                await bot.reply(msg, "Unknown command.")
        """

        def decorator(fn: Callable) -> Callable:
            self._dispatcher.set_default(fn)
            return fn

        return decorator

    def add_middleware(self, middleware: Callable) -> None:
        """Add a middleware to the processing pipeline.

        Middleware is executed in the order it is added, before the dispatcher.
        See :class:`MiddlewarePipeline` for the middleware signature.

        Args:
            middleware: Async callable ``(msg: ParsedMessage, next: Callable) -> None``.
        """
        self._pipeline.add(middleware)

    # ── Lifecycle hooks ──────────────────────────────────────────────────────

    async def on_start(self) -> None:
        """Called after driver login, before the WebSocket opens.

        Override to run setup logic (open database connections, seed caches, etc.).
        """

    async def on_stop(self) -> None:
        """Called on clean shutdown (KeyboardInterrupt / SIGTERM).

        Override to run teardown logic (close connections, flush state, etc.).
        """

    async def on_message(self, msg: ParsedMessage) -> None:
        """Fallback called when a message clears the middleware pipeline but matches no command.

        Override this or use ``@bot.default_handler`` to handle unmatched messages.

        Args:
            msg: The unmatched parsed message.
        """

    # ── Helper ───────────────────────────────────────────────────────────────

    async def reply(self, msg: ParsedMessage, text: str) -> None:
        """Send *text* to the channel the message came from.

        Args:
            msg: The incoming message to reply to.
            text: The reply text.
        """
        self.driver.posts.create_post({"channel_id": msg.channel_id, "message": text})

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the bot. Blocks until interrupted (Ctrl+C) or the process receives SIGTERM.

        This method:

        1. Configures logging from :attr:`config`.
        2. Calls ``driver.login()`` and fetches the bot's own user ID.
        3. Awaits :meth:`on_start`.
        4. Starts the background session cleanup task.
        5. Opens the WebSocket listener.
        6. On shutdown: cancels background tasks and awaits :meth:`on_stop`.
        """
        self._setup_logging()
        logger.info("Bot starting up.")

        self.driver.login()
        me = self.driver.users.get_user("me")
        self._bot_id = me["id"]
        logger.info("Logged in as %s (id=%s).", me.get("username"), self._bot_id)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(self.on_start())
        loop.create_task(self._session_cleanup_loop())

        async def _ws_handler(raw_msg: str | dict) -> None:
            raw_str = raw_msg if isinstance(raw_msg, str) else json.dumps(raw_msg)
            msg = ParsedMessage.from_raw(raw_str)
            if msg is not None:
                await self._pipeline.run(msg, self._dispatch)

        try:
            logger.info("Opening WebSocket. Press Ctrl+C to stop.")
            self.driver.init_websocket(_ws_handler)
        except KeyboardInterrupt:
            logger.info("Interrupted. Shutting down.")
        finally:
            loop.run_until_complete(self.on_stop())
            loop.close()
            logger.info("Bot shut down cleanly.")

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _dispatch(self, msg: ParsedMessage) -> None:
        """Run the dispatcher; fall through to on_message if nothing matched."""
        matched = await self._dispatcher.dispatch(msg)
        if not matched:
            await self.on_message(msg)

    async def _session_cleanup_loop(self) -> None:
        """Background task: purge expired sessions on a fixed interval."""
        interval = self.config.session_cleanup_interval_seconds
        while True:
            await asyncio.sleep(interval)
            count = self.sessions.purge_expired()
            if count:
                logger.info("Session cleanup: removed %d expired session(s).", count)

    def _setup_logging(self) -> None:
        """Configure the root logger from :attr:`config`."""
        level = getattr(logging, self.config.log_level, logging.INFO)
        handlers: list[logging.Handler] = [logging.StreamHandler()]
        if self.config.log_file:
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    self.config.log_file,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=3,
                )
            )
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=handlers,
            force=True,
        )
        logger.debug("Logging configured — level=%s file=%s", self.config.log_level, self.config.log_file)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd mmbot_framework && uv run pytest tests/test_bot.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
cd mmbot_framework && uv run pytest -v
```

Expected: all tests across all test files PASS.

- [ ] **Step 6: Commit**

```bash
git add mmbot_framework/mmbot_framework/core/bot.py mmbot_framework/tests/test_bot.py
git commit -m "feat: add BaseBot with lifecycle hooks, command registration, and session cleanup"
```

---

## Task 10: Public API + Sub-module `__init__.py` Files + README

**Files:**
- Modify: `mmbot_framework/mmbot_framework/__init__.py`
- Modify: `mmbot_framework/mmbot_framework/config/__init__.py`
- Modify: `mmbot_framework/mmbot_framework/core/__init__.py`
- Modify: `mmbot_framework/mmbot_framework/routing/__init__.py`
- Modify: `mmbot_framework/mmbot_framework/middleware/__init__.py`
- Create: `mmbot_framework/README.md`

- [ ] **Step 1: Populate sub-module `__init__.py` files**

`mmbot_framework/mmbot_framework/config/__init__.py`:
```python
from mmbot_framework.config.loader import ConfigLoader
from mmbot_framework.config.schema import BotConfig, ConfigError

__all__ = ["BotConfig", "ConfigError", "ConfigLoader"]
```

`mmbot_framework/mmbot_framework/core/__init__.py`:
```python
from mmbot_framework.core.bot import BaseBot
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.core.session import Session, SessionManager

__all__ = ["BaseBot", "ParsedMessage", "Session", "SessionManager"]
```

`mmbot_framework/mmbot_framework/routing/__init__.py`:
```python
from mmbot_framework.routing.dispatcher import CommandDispatcher, command

__all__ = ["CommandDispatcher", "command"]
```

`mmbot_framework/mmbot_framework/middleware/__init__.py`:
```python
from mmbot_framework.middleware.pipeline import (
    IgnoreSelfMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
)

__all__ = ["IgnoreSelfMiddleware", "LoggingMiddleware", "MiddlewarePipeline"]
```

- [ ] **Step 2: Populate the top-level `mmbot_framework/mmbot_framework/__init__.py`**

```python
"""mmbot_framework — Shared framework for Mattermost bots.

Quick start
-----------
.. code-block:: python

    from mmbot_framework import BaseBot, BotConfig, ParsedMessage
    from mmbot_framework.config import ConfigLoader
    from mmbot_framework.routing import command
    from mmbot_framework.middleware import LoggingMiddleware, IgnoreSelfMiddleware

    config = ConfigLoader.auto_detect()   # reads .env / config.toml / config.json

    class MyBot(BaseBot):
        @command("!ping")
        async def ping(self, msg: ParsedMessage) -> None:
            await self.reply(msg, "pong")

        async def on_message(self, msg: ParsedMessage) -> None:
            await self.reply(msg, "Unknown command. Try !ping.")

    bot = MyBot(config)
    bot.add_middleware(IgnoreSelfMiddleware(bot))
    bot.add_middleware(LoggingMiddleware())
    bot.run()
"""

from mmbot_framework.config.loader import ConfigLoader
from mmbot_framework.config.schema import BotConfig, ConfigError
from mmbot_framework.core.bot import BaseBot
from mmbot_framework.core.message import ParsedMessage
from mmbot_framework.core.session import Session, SessionManager
from mmbot_framework.middleware.pipeline import (
    IgnoreSelfMiddleware,
    LoggingMiddleware,
    MiddlewarePipeline,
)
from mmbot_framework.routing.dispatcher import CommandDispatcher, command

__all__ = [
    "BaseBot",
    "BotConfig",
    "ConfigError",
    "ConfigLoader",
    "CommandDispatcher",
    "IgnoreSelfMiddleware",
    "LoggingMiddleware",
    "MiddlewarePipeline",
    "ParsedMessage",
    "Session",
    "SessionManager",
    "command",
]
```

- [ ] **Step 3: Verify imports work**

```bash
cd mmbot_framework && uv run python -c "
from mmbot_framework import (
    BaseBot, BotConfig, ConfigError, ConfigLoader,
    CommandDispatcher, IgnoreSelfMiddleware, LoggingMiddleware,
    MiddlewarePipeline, ParsedMessage, Session, SessionManager, command,
)
print('All imports OK')
"
```

Expected output: `All imports OK`

- [ ] **Step 4: Write `mmbot_framework/README.md`**

```markdown
# mmbot_framework

Shared Python framework for building Mattermost bots in this monorepo.

## Installation

Add to your bot's `pyproject.toml`:

```toml
[project]
dependencies = ["mmbot-framework"]

[tool.uv.sources]
mmbot-framework = { path = "../mmbot_framework" }
```

Then run `uv sync`.

## Configuration

The framework reads config from `.env`, `config.toml`, or `config.json`.
All formats map to the same fields:

| Field | Required | Default | Description |
|---|---|---|---|
| `url` | yes | — | Mattermost server URL |
| `token` | yes | — | Bot authentication token |
| `team_name` | yes | — | Mattermost team name |
| `scheme` | no | `https` | HTTP scheme |
| `port` | no | `443` | Server port |
| `log_level` | no | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `log_file` | no | `None` | Path for rotating log file. Omit for console-only logging. |
| `session_ttl_seconds` | no | `3600` | Seconds before an idle session expires (1 hour) |
| `session_cleanup_interval_seconds` | no | `300` | How often expired sessions are purged (5 minutes) |

**.env example:**
```
URL=https://mattermost.example.com
TOKEN=your-bot-token
TEAM_NAME=myteam
LOG_LEVEL=INFO
```

**config.toml example:**
```toml
url = "https://mattermost.example.com"
token = "your-bot-token"
team_name = "myteam"
log_level = "INFO"
```

**config.json example:**
```json
{
  "url": "https://mattermost.example.com",
  "token": "your-bot-token",
  "team_name": "myteam"
}
```

### Loading config

```python
from mmbot_framework.config import ConfigLoader

# Auto-detect: searches cwd for .env → config.toml → config.json
config = ConfigLoader.auto_detect()

# Explicit file
config = ConfigLoader.from_file("config.toml")
config = ConfigLoader.from_file(".env")
config = ConfigLoader.from_file("settings.json")
```

## Quick Start

### Class-based (recommended for multi-command bots)

```python
from mmbot_framework import BaseBot, ParsedMessage
from mmbot_framework.config import ConfigLoader
from mmbot_framework.routing import command
from mmbot_framework.middleware import LoggingMiddleware, IgnoreSelfMiddleware

config = ConfigLoader.auto_detect()

class MyBot(BaseBot):
    async def on_start(self) -> None:
        """Called after login, before the WebSocket opens."""
        print("Bot is ready!")

    async def on_stop(self) -> None:
        """Called on clean shutdown."""
        print("Bye!")

    @command("!ping")
    async def ping(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "pong")

    @command("!help")
    async def help(self, msg: ParsedMessage) -> None:
        await self.reply(msg, "Available commands: !ping, !help")

    async def on_message(self, msg: ParsedMessage) -> None:
        """Fallback for unrecognised messages."""
        await self.reply(msg, f"Unknown command: {msg.text}")

bot = MyBot(config)
bot.add_middleware(IgnoreSelfMiddleware(bot))
bot.add_middleware(LoggingMiddleware())
bot.run()
```

### Decorator-based (functional style)

```python
from mmbot_framework import BaseBot, ParsedMessage
from mmbot_framework.config import ConfigLoader

config = ConfigLoader.auto_detect()
bot = BaseBot(config)

@bot.command("!ping")
async def ping(msg: ParsedMessage) -> None:
    await bot.reply(msg, "pong")

@bot.default_handler
async def fallback(msg: ParsedMessage) -> None:
    await bot.reply(msg, "I don't know that command.")

bot.run()
```

## Middleware

Middleware is an async callable with the signature:

```python
async def my_middleware(msg: ParsedMessage, next: Callable) -> None:
    # pre-processing (runs before handlers)
    await next(msg)   # pass to next middleware / dispatcher
    # post-processing (optional, runs after handlers return)
```

Not calling `next` **drops** the message — nothing downstream runs.

```python
bot.add_middleware(IgnoreSelfMiddleware(bot))  # drop bot's own messages
bot.add_middleware(LoggingMiddleware())         # log every message at DEBUG
bot.add_middleware(my_rate_limiter)            # custom middleware
```

Middleware runs in the order it is added.

## Sessions

`BaseBot` exposes `self.sessions: SessionManager` for per-user conversation state.
Sessions expire after `config.session_ttl_seconds` seconds of inactivity.

```python
class MyBot(BaseBot):
    @command("!start")
    async def start(self, msg: ParsedMessage) -> None:
        session = self.sessions.get_or_create(msg.sender_id)
        session.data["step"] = "awaiting_input"
        await self.reply(msg, "What would you like to do?")

    @command("!cancel")
    async def cancel(self, msg: ParsedMessage) -> None:
        self.sessions.clear(msg.sender_id)
        await self.reply(msg, "Session cancelled.")

    async def on_message(self, msg: ParsedMessage) -> None:
        session = self.sessions.get(msg.sender_id)
        if session is None:
            # Session expired or never started
            await self.reply(msg, "No active session. Use !start to begin.")
            return
        # Handle multi-step flow using session.data
        step = session.data.get("step")
        ...
```

### SessionManager API

| Method | Description |
|---|---|
| `get(sender_id)` | Returns the live session or `None` if absent/expired. Updates `last_active`. |
| `get_or_create(sender_id)` | Returns live session or creates a fresh one. Clears expired sessions first. |
| `clear(sender_id)` | Explicitly deletes the session. Safe to call even if none exists. |
| `is_alive(sender_id)` | Returns `True` if a non-expired session exists. Does **not** update `last_active`. |

## ParsedMessage

All handlers receive a `ParsedMessage`:

```python
@dataclass
class ParsedMessage:
    sender_id: str       # Mattermost user ID
    sender_name: str     # Username (@ stripped)
    channel_id: str      # Channel ID
    channel_type: str    # "D" = DM, "O" = public, "P" = private group
    text: str            # Message body (whitespace-trimmed)
    file_ids: list[str]  # Attached file IDs (empty list if none)
    raw: dict            # Original WebSocket payload
```

## Running Tests

```bash
cd mmbot_framework
uv run pytest -v
```
```

- [ ] **Step 5: Run the full test suite one final time**

```bash
cd mmbot_framework && uv run pytest -v
```

Expected: all tests PASS, zero failures.

- [ ] **Step 6: Commit**

```bash
git add mmbot_framework/
git commit -m "feat: add public API exports and developer README for mmbot_framework"
```