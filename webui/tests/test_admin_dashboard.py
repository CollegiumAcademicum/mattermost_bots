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


class ConfigTemplateTest(TestCase):
    """Test that config.html template renders key content."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user("configadmin", password="pw")
        group = Group.objects.get_or_create(name="BotAdmins")[0]
        user.groups.add(group)
        self.client.login(username="configadmin", password="pw")

    def _get(self):
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   return_value=MOCK_CONFIG), \
             patch("broadcast.admin_dashboard.views.config.admin_client.get_channels",
                   return_value=MOCK_CHANNELS):
            return self.client.get("/admin-dashboard/config/")

    def test_config_shows_group_name(self):
        resp = self._get()
        self.assertContains(resp, "Alle")

    def test_config_shows_channel_display_name(self):
        resp = self._get()
        self.assertContains(resp, "Alle Bewohner")

    def test_config_shows_whitelist_section(self):
        cfg_with_whitelist = {
            **MOCK_CONFIG,
            "whitelist": {"alice": {"id": "user123", "aliases": []}},
        }
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   return_value=cfg_with_whitelist), \
             patch("broadcast.admin_dashboard.views.config.admin_client.get_channels",
                   return_value=MOCK_CHANNELS):
            resp = self.client.get("/admin-dashboard/config/")
        self.assertContains(resp, "alice")
        self.assertContains(resp, "user123")

    def test_config_shows_add_group_form(self):
        resp = self._get()
        self.assertContains(resp, "add_group")

    def test_config_empty_groups_shows_no_entries_message(self):
        empty_cfg = {"groups": {}, "private_groups": {}, "whitelist": {}}
        with patch("broadcast.admin_dashboard.views.config.admin_client.get_config",
                   return_value=empty_cfg), \
             patch("broadcast.admin_dashboard.views.config.admin_client.get_channels",
                   return_value={"individual_channels": []}):
            resp = self.client.get("/admin-dashboard/config/")
        self.assertContains(resp, "Keine Einträge")


MOCK_TASKS = {
    "tasks": [
        {
            "name": "example_task",
            "description": "Sends weekly digest",
            "last_run": "2026-06-21T02:00:00+00:00",
            "schedule": "0 9 * * 1",
        },
        {
            "name": "cleanup_old_logs",
            "description": "—",
            "last_run": None,
            "schedule": None,
        },
    ]
}


class AdminClientTasksTest(TestCase):
    @patch("broadcast.admin_dashboard.services.admin_client.requests.get")
    def test_get_tasks_calls_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TASKS
        mock_get.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.get_tasks()

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "/api/tasks" in call_url
        assert result == MOCK_TASKS

    @patch("broadcast.admin_dashboard.services.admin_client.requests.post")
    def test_run_task_calls_correct_url(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.run_task("example_task")

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/api/tasks/example_task/run" in call_url
        assert result == {"ok": True}

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_set_task_schedule_calls_correct_url(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        result = admin_client.set_task_schedule("example_task", "0 9 * * 1")

        mock_put.assert_called_once()
        call_url = mock_put.call_args[0][0]
        assert "/api/tasks/example_task/schedule" in call_url
        call_json = mock_put.call_args[1]["json"]
        assert call_json == {"cron": "0 9 * * 1"}
        assert result == {"ok": True}

    @patch("broadcast.admin_dashboard.services.admin_client.requests.put")
    def test_set_task_schedule_null_sends_none(self, mock_put):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_put.return_value = mock_resp

        from broadcast.admin_dashboard.services import admin_client
        admin_client.set_task_schedule("example_task", None)

        call_json = mock_put.call_args[1]["json"]
        assert call_json == {"cron": None}


class TasksViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("admin", password="pw")
        group = Group.objects.create(name="BotAdmins")
        self.user.groups.add(group)
        self.client.login(username="admin", password="pw")

    def test_tasks_get_renders_task_list(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            return_value=MOCK_TASKS,
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["tasks"]), 2)
        self.assertEqual(resp.context["tasks"][0]["name"], "example_task")

    def test_tasks_get_formats_last_run(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            return_value=MOCK_TASKS,
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        tasks_by_name = {t["name"]: t for t in resp.context["tasks"]}
        self.assertIn("2026", tasks_by_name["example_task"]["last_run_display"])
        self.assertEqual(tasks_by_name["cleanup_old_logs"]["last_run_display"], "Noch nie")

    def test_tasks_get_on_api_error_shows_empty_list(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.get_tasks",
            side_effect=Exception("connection refused"),
        ):
            resp = self.client.get("/admin-dashboard/tasks/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["tasks"], [])

    def test_tasks_post_run_calls_run_task_and_redirects(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.run_task",
            return_value={"ok": True},
        ) as mock_run:
            resp = self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "run", "name": "example_task"},
            )

        mock_run.assert_called_once_with("example_task")
        self.assertRedirects(resp, "/admin-dashboard/tasks/")

    def test_tasks_post_set_schedule_calls_set_schedule_and_redirects(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.set_task_schedule",
            return_value={"ok": True},
        ) as mock_set:
            resp = self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "set_schedule", "name": "example_task", "cron": "0 8 * * 1"},
            )

        mock_set.assert_called_once_with("example_task", "0 8 * * 1")
        self.assertRedirects(resp, "/admin-dashboard/tasks/")

    def test_tasks_post_set_schedule_empty_cron_sends_none(self):
        with patch(
            "broadcast.admin_dashboard.views.tasks.admin_client.set_task_schedule",
            return_value={"ok": True},
        ) as mock_set:
            self.client.post(
                "/admin-dashboard/tasks/",
                {"action": "set_schedule", "name": "example_task", "cron": ""},
            )

        mock_set.assert_called_once_with("example_task", None)
