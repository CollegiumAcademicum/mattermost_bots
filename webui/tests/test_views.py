"""Django test-client tests for broadcast views."""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

MOCK_CHANNELS = {
    "groups": {
        "Group A": [
            {"id": "id1", "display_name": "Channel One", "channel_name": "channel-one"}
        ],
    },
    "private_groups": {},
    "individual_channels": [
        {"id": "id1", "display_name": "Channel One", "channel_name": "channel-one"},
        {"id": "id2", "display_name": "Channel Two", "channel_name": "channel-two"},
    ],
}


class ComposeViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_get_renders_channel_groups(self, _):
        resp = self.client.get(reverse("broadcast:compose"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Group A")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_valid_redirects_to_confirm(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello world", "groups": ["Group A"]},
        )
        self.assertRedirects(resp, reverse("broadcast:confirm"), fetch_redirect_response=False)

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_stores_selections_in_session(self, _):
        self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello", "groups": ["Group A"]},
        )
        session = self.client.session
        self.assertEqual(session["broadcast_message"], "Hello")
        self.assertEqual(session["broadcast_groups"], ["Group A"])

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_stores_uploaded_attachments_in_session(self, _):
        upload = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello", "groups": ["Group A"], "attachments": [upload]},
        )
        attachments = self.client.session["broadcast_attachments"]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["name"], "test.txt")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_empty_message_shows_error(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"groups": ["Group A"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Message cannot be empty")

    @patch("broadcast.views.compose.get_channels", return_value=MOCK_CHANNELS)
    def test_post_no_channel_selection_shows_error(self, _):
        resp = self.client.post(
            reverse("broadcast:compose"),
            {"message": "Hello"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Select at least one")

    def test_get_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("broadcast:compose"))
        self.assertRedirects(resp, "/login/?next=/broadcast/", fetch_redirect_response=False)


class ConfirmViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")
        session = self.client.session
        session["broadcast_message"] = "Hello world"
        session["broadcast_groups"] = ["Group A"]
        session["broadcast_individual"] = []
        session.save()

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    def test_get_shows_message_and_channels(self, _):
        resp = self.client.get(reverse("broadcast:confirm"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hello world")
        self.assertContains(resp, "Channel One")

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    @patch(
        "broadcast.views.confirm.send_broadcast",
        return_value={"sent": 1, "failed": 0, "errors": []},
    )
    def test_post_send_calls_postbot_and_redirects(self, mock_send, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "send"})
        self.assertRedirects(resp, reverse("broadcast:result"))
        mock_send.assert_called_once_with("Hello world", ["id1"], sender="testuser", attachments=[])

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    @patch(
        "broadcast.views.confirm.send_broadcast",
        return_value={"sent": 1, "failed": 0, "errors": []},
    )
    def test_post_send_includes_attachments(self, mock_send, _):
        session = self.client.session
        session["broadcast_attachments"] = [{"name": "a.txt", "path": "/tmp/a.txt", "content_type": "text/plain"}]
        session.save()
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "send"})
        self.assertRedirects(resp, reverse("broadcast:result"))
        mock_send.assert_called_once_with(
            "Hello world",
            ["id1"],
            sender="testuser",
            attachments=[{"name": "a.txt", "path": "/tmp/a.txt", "content_type": "text/plain"}],
        )

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    def test_post_back_redirects_to_compose(self, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "back"})
        self.assertRedirects(resp, reverse("broadcast:compose"))

    @patch("broadcast.views.confirm.get_channels", return_value=MOCK_CHANNELS)
    @patch(
        "broadcast.views.confirm.send_broadcast",
        side_effect=__import__("requests").ConnectionError("unreachable"),
    )
    def test_post_send_postbot_unreachable_shows_error(self, mock_send, _):
        resp = self.client.post(reverse("broadcast:confirm"), {"action": "send"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "unreachable")

    def test_get_without_session_redirects_to_compose(self):
        session = self.client.session
        del session["broadcast_message"]
        session.save()
        resp = self.client.get(reverse("broadcast:confirm"))
        self.assertRedirects(resp, reverse("broadcast:compose"))


class ResultViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="password")
        self.client.login(username="testuser", password="password")
        session = self.client.session
        session["broadcast_result"] = {"sent": 3, "failed": 0, "errors": []}
        session.save()

    def test_get_shows_sent_count(self):
        resp = self.client.get(reverse("broadcast:result"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "3")

    def test_get_clears_result_from_session(self):
        self.client.get(reverse("broadcast:result"))
        self.assertNotIn("broadcast_result", self.client.session)

    def test_get_without_session_redirects_to_compose(self):
        session = self.client.session
        del session["broadcast_result"]
        session.save()
        resp = self.client.get(reverse("broadcast:result"))
        self.assertRedirects(resp, reverse("broadcast:compose"))


class HealthCheckTest(TestCase):
    def test_health_returns_200_and_ok(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_health_requires_no_authentication(self):
        unauthenticated = Client()
        resp = unauthenticated.get("/health/")
        self.assertEqual(resp.status_code, 200)
