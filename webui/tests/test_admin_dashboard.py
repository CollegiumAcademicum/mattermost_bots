"""Tests for admin_dashboard views and require_bot_admin decorator."""
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group


MOCK_HISTORY = {
    "total": 2,
    "page": 1,
    "per_page": 20,
    "results": [
        {"id": 2, "timestamp": "2026-06-20T10:00:00", "sender_name": "alice",
         "message_content": "Hello world", "target_channels": ["ch1"], "file_ids": []},
        {"id": 1, "timestamp": "2026-06-19T09:00:00", "sender_name": "bob",
         "message_content": "Hi there", "target_channels": ["ch2"], "file_ids": []},
    ],
}

MOCK_CONFIG = {
    "groups": {"Alle": {"channels": ["abc123"], "aliases": []}},
    "private_groups": {},
    "whitelist": {},
}

MOCK_CHANNELS = {"individual_channels": [{"id": "abc123", "display_name": "Alle Bewohner"}]}


class RequireBotAdminTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", password="pw")
        self.admin_group = Group.objects.create(name="BotAdmins")

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_non_admin_gets_403(self):
        self.client.login(username="testuser", password="pw")
        resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 403)

    def test_bot_admin_gets_200(self):
        self.user.groups.add(self.admin_group)
        self.client.login(username="testuser", password="pw")
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 200)


class HistoryViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("admin", password="pw")
        group = Group.objects.create(name="BotAdmins")
        self.user.groups.add(group)
        self.client.login(username="admin", password="pw")

    def test_history_renders_results(self):
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 2)
        self.assertEqual(len(resp.context["results"]), 2)

    def test_history_passes_page_param(self):
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY) as mock_get:
            self.client.get("/admin-dashboard/history/?page=3")
        mock_get.assert_called_once_with(page=3, per_page=20)


class ConfigViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("admin", password="pw")
        group = Group.objects.create(name="BotAdmins")
        self.user.groups.add(group)
        self.client.login(username="admin", password="pw")

    def test_config_get_renders(self):
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   return_value=MOCK_CONFIG), \
             patch("broadcast.admin_dashboard.views.config.admin_client.get_channels",
                   return_value=MOCK_CHANNELS):
            resp = self.client.get("/admin-dashboard/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.context["sections"])

    def test_config_post_calls_put_config(self):
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   return_value=MOCK_CONFIG) as mock_get_cfg, \
             patch("broadcast.admin_dashboard.views.config.admin_client.put_config") as mock_put:
            resp = self.client.post("/admin-dashboard/config/", {
                "action": "delete_group",
                "section": "groups",
                "name": "Alle",
            })
        self.assertEqual(resp.status_code, 302)
        mock_put.assert_called_once()

    def test_config_post_api_error_shows_message(self):
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   side_effect=Exception("connection refused")):
            resp = self.client.post("/admin-dashboard/config/", {
                "action": "delete_group",
                "section": "groups",
                "name": "Alle",
            })
        self.assertEqual(resp.status_code, 302)


class HistoryTemplateTest(TestCase):
    """Test that history.html template renders key content."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user("admin2", password="pw")
        group = Group.objects.get_or_create(name="BotAdmins")[0]
        user.groups.add(group)
        self.client.login(username="admin2", password="pw")

    def test_history_shows_sender_name(self):
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertContains(resp, "alice")
        self.assertContains(resp, "bob")

    def test_history_shows_message_preview(self):
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertContains(resp, "Hello world")

    def test_history_shows_target_channel(self):
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=MOCK_HISTORY):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertContains(resp, "ch1")

    def test_history_empty_state(self):
        empty = {"total": 0, "page": 1, "per_page": 20, "results": []}
        with patch("broadcast.admin_dashboard.views.history.admin_client.get_history",
                   return_value=empty):
            resp = self.client.get("/admin-dashboard/history/")
        self.assertContains(resp, "Noch keine Broadcasts")
