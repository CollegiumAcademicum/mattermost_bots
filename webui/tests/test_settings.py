"""Tests for env-var-driven security settings in webui/settings.py.

These tests reload webui.settings directly (bypassing Django's settings proxy
and settings_test.py) to verify that env vars produce the correct module-level
values. dotenv.load_dotenv is patched out so the local .env file doesn't
interfere.
"""
import importlib
import os
import sys
from unittest.mock import patch


def _load(env: dict) -> object:
    """Reload webui.settings with the given env vars patched in."""
    mod_name = "webui.settings"
    sys.modules.pop(mod_name, None)
    base_env = {
        "DJANGO_SECRET_KEY": "a" * 50,
        "DEBUG": "false",
    }
    base_env.update(env)
    with patch.dict(os.environ, base_env, clear=False), patch("dotenv.load_dotenv"):
        return importlib.import_module(mod_name)


def test_proxy_ssl_header_always_set():
    m = _load({})
    assert m.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_use_x_forwarded_host_always_true():
    m = _load({})
    assert m.USE_X_FORWARDED_HOST is True


def test_secure_ssl_redirect_default_false():
    m = _load({})
    assert m.SECURE_SSL_REDIRECT is False


def test_secure_ssl_redirect_can_be_enabled():
    m = _load({"SECURE_SSL_REDIRECT": "true"})
    assert m.SECURE_SSL_REDIRECT is True


def test_https_disabled_by_default():
    m = _load({})
    assert m.SESSION_COOKIE_SECURE is False
    assert m.CSRF_COOKIE_SECURE is False


def test_https_enabled_sets_secure_cookies():
    m = _load({"HTTPS_ENABLED": "true"})
    assert m.SESSION_COOKIE_SECURE is True
    assert m.CSRF_COOKIE_SECURE is True


def test_csrf_trusted_origins_empty_by_default():
    m = _load({})
    assert m.CSRF_TRUSTED_ORIGINS == []


def test_csrf_trusted_origins_parsed_from_env():
    m = _load({"CSRF_TRUSTED_ORIGINS": "https://a.example.com,https://b.example.com"})
    assert m.CSRF_TRUSTED_ORIGINS == ["https://a.example.com", "https://b.example.com"]


def test_hsts_disabled_by_default():
    m = _load({})
    assert m.SECURE_HSTS_SECONDS == 0
    assert m.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
    assert m.SECURE_HSTS_PRELOAD is False


def test_hsts_set_from_env():
    m = _load({"SECURE_HSTS_SECONDS": "31536000"})
    assert m.SECURE_HSTS_SECONDS == 31536000
    assert m.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert m.SECURE_HSTS_PRELOAD is True


def test_referrer_policy_is_same_origin():
    m = _load({})
    assert m.SECURE_REFERRER_POLICY == "same-origin"


def test_logging_has_console_handler():
    m = _load({})
    assert "console" in m.LOGGING["handlers"]
    assert m.LOGGING["handlers"]["console"]["class"] == "logging.StreamHandler"


def test_logging_django_logger_at_warning():
    m = _load({})
    assert m.LOGGING["loggers"]["django"]["level"] == "WARNING"
    assert "console" in m.LOGGING["loggers"]["django"]["handlers"]


def test_logging_request_logger_at_error_no_propagate():
    m = _load({})
    req = m.LOGGING["loggers"]["django.request"]
    assert req["level"] == "ERROR"
    assert req["propagate"] is False
