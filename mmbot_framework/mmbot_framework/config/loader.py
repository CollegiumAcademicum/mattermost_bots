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
