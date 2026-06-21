"""Tests for admin_client."""
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import TestCase, override_settings


@override_settings(
    POSTBOT_API_URL="http://postbot:8000",
    POSTBOT_API_SECRET="test-secret",
)
class AdminClientTest(TestCase):
    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_history_returns_parsed_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total": 5,
            "page": 1,
            "per_page": 20,
            "results": [
                {
                    "id": 1,
                    "message": "Test broadcast",
                    "sender": "alice",
                    "timestamp": "2026-06-21T10:00:00Z",
                }
            ],
        }
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import get_history

        result = get_history()

        self.assertEqual(result["total"], 5)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["per_page"], 20)
        self.assertIn("Authorization", mock_get.call_args[1]["headers"])
        self.assertIn("Bearer test-secret", mock_get.call_args[1]["headers"]["Authorization"])

    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_history_passes_page_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total": 5,
            "page": 2,
            "per_page": 5,
            "results": [],
        }
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import get_history

        result = get_history(page=2, per_page=5)

        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["params"]["page"], 2)
        self.assertEqual(call_kwargs["params"]["per_page"], 5)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["per_page"], 5)

    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_history_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import get_history

        with self.assertRaises(requests.HTTPError):
            get_history()

    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_config_returns_parsed_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "groups": {"G1": [{"id": "id1", "display_name": "Group 1"}]},
            "private_groups": {},
            "whitelist": [],
        }
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import get_config

        result = get_config()

        self.assertIn("groups", result)
        self.assertIn("private_groups", result)
        self.assertIn("whitelist", result)
        self.assertIn("Bearer test-secret", mock_get.call_args[1]["headers"]["Authorization"])

    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_config_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import get_config

        with self.assertRaises(requests.HTTPError):
            get_config()

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_put_config_sends_payload(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import put_config

        config = {
            "groups": {"G1": [{"id": "id1", "display_name": "Group 1"}]},
            "private_groups": {},
            "whitelist": [],
        }
        result = put_config(config)

        self.assertEqual(result["ok"], True)
        call_kwargs = mock_put.call_args[1]
        self.assertEqual(call_kwargs["json"], config)
        self.assertIn("Bearer test-secret", call_kwargs["headers"]["Authorization"])

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_put_config_raises_on_http_error(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services.admin_client import put_config

        with self.assertRaises(requests.HTTPError):
            put_config({"groups": {}})
