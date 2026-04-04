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
