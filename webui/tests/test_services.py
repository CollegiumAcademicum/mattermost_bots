"""Tests for postbot_client and channel_service."""
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import TestCase, override_settings


@override_settings(
    POSTBOT_API_URL="http://postbot:8000",
    POSTBOT_API_SECRET="test-secret",
)
class PostbotClientTest(TestCase):
    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"sent": 2, "failed": 0, "errors": []}
        mock_post.return_value = mock_resp

        from broadcast.services.postbot_client import send_broadcast

        result = send_broadcast("Hello world", ["id1", "id2"], sender="alice")

        self.assertEqual(result["sent"], 2)
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["message"], "Hello world")
        self.assertEqual(call_kwargs["json"]["channel_ids"], ["id1", "id2"])
        self.assertEqual(call_kwargs["json"]["sender"], "alice")
        self.assertIn("Bearer test-secret", call_kwargs["headers"]["Authorization"])

    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_connection_error_raises(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("unreachable")

        from broadcast.services.postbot_client import send_broadcast

        with self.assertRaises(requests.ConnectionError):
            send_broadcast("Hello", ["id1"])

    @patch("broadcast.services.postbot_client.requests.post")
    def test_send_broadcast_http_error_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        from broadcast.services.postbot_client import send_broadcast

        with self.assertRaises(requests.HTTPError):
            send_broadcast("Hello", ["id1"])


@override_settings(
    POSTBOT_API_URL="http://postbot:8000",
    POSTBOT_API_SECRET="test-secret",
)
class ChannelServiceTest(TestCase):
    def setUp(self):
        # Reset module-level cache between tests.
        import broadcast.services.channel_service as cs
        cs._cache = {}
        cs._cache_time = 0.0

    @patch("broadcast.services.channel_service.requests.get")
    def test_get_channels_fetches_and_caches(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "groups": {"G": [{"id": "id1", "display_name": "D", "channel_name": "d"}]},
            "private_groups": {},
            "individual_channels": [],
        }
        mock_get.return_value = mock_resp

        from broadcast.services.channel_service import get_channels

        result1 = get_channels()
        result2 = get_channels()  # Should use cache

        self.assertIn("G", result1["groups"])
        self.assertEqual(mock_get.call_count, 1)  # fetched only once

    @patch("broadcast.services.channel_service.requests.get")
    def test_get_channels_returns_stale_cache_on_error(self, mock_get):
        import broadcast.services.channel_service as cs

        # Pre-populate cache.
        cs._cache = {"groups": {"Old": []}, "private_groups": {}, "individual_channels": []}
        cs._cache_time = 0.0  # expired

        mock_get.side_effect = requests.ConnectionError("unreachable")

        from broadcast.services.channel_service import get_channels

        result = get_channels()
        self.assertIn("Old", result["groups"])  # stale cache returned
