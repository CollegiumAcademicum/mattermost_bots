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
