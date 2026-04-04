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
