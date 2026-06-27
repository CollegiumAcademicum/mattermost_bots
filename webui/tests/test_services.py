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
    @patch("broadcast.admin_dashboard.services.admin_client._call")
    def test_send_broadcast_success(self, mock_call):
        mock_call.return_value = {"sent": 2, "failed": 0, "errors": []}

        from broadcast.services.postbot_client import send_broadcast

        result = send_broadcast("Hello world", ["id1", "id2"], sender="alice")

        self.assertEqual(result["sent"], 2)
        mock_call.assert_called_once_with(
            "POST",
            "/api/broadcast",
            json={"message": "Hello world", "channel_ids": ["id1", "id2"], "sender": "alice"},
        )

    @patch("broadcast.admin_dashboard.services.admin_client._call")
    def test_send_broadcast_connection_error_raises(self, mock_call):
        mock_call.side_effect = requests.ConnectionError("unreachable")

        from broadcast.services.postbot_client import send_broadcast

        with self.assertRaises(requests.ConnectionError):
            send_broadcast("Hello", ["id1"])

    @patch("broadcast.admin_dashboard.services.admin_client._call")
    def test_send_broadcast_http_error_raises(self, mock_call):
        mock_call.side_effect = requests.HTTPError("500")

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
