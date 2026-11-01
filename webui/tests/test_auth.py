from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import SuspiciousOperation
from django.test import Client, RequestFactory


def backend():
    from broadcast.auth import KeycloakOIDCBackend
    return KeycloakOIDCBackend()


def claims(username="alice", groups=(), **extra):
    return {"preferred_username": username, "groups": list(groups), "given_name": "Alice",
            "family_name": "A", "email": "a@ca.de", **extra}


def login(c):
    with patch("broadcast.auth.KeycloakOIDCBackend.get_userinfo", return_value=c):
        return backend().get_or_create_user("at", "it", {})


def is_bot_admin(user):
    return user.groups.filter(name="BotAdmins").exists()


@pytest.mark.django_db
def test_first_login_creates_user_with_claims_and_no_password():
    user = login(claims())
    assert (user.username, user.first_name, user.last_name, user.email) == ("alice", "Alice", "A", "a@ca.de")
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_existing_ldap_user_is_reused():
    existing = User(username="alice")
    existing.set_unusable_password()
    existing.save()
    assert login(claims()).pk == existing.pk


@pytest.mark.django_db
def test_login_without_username_is_refused():
    with pytest.raises(SuspiciousOperation):
        login({"email": "a@ca.de"})


@pytest.mark.django_db
def test_sso_cannot_take_over_local_password_account():
    User.objects.create_superuser(username="admin", password="pw")
    with pytest.raises(SuspiciousOperation):
        login(claims(username="admin"))


@pytest.mark.django_db
def test_admin_group_grants_bot_admins():
    assert is_bot_admin(login(claims(groups=["ag.it"])))


@pytest.mark.django_db
def test_admin_group_accepts_full_path_and_case():
    assert is_bot_admin(login(claims(groups=["/AG.IT"])))


@pytest.mark.django_db
def test_leaving_admin_group_revokes_bot_admins():
    assert is_bot_admin(login(claims(groups=["ag.it"])))
    assert not is_bot_admin(login(claims(groups=["ag.kueche"])))


@pytest.mark.django_db
def test_unset_admin_group_leaves_memberships_alone(settings):
    user = login(claims(groups=["ag.it"]))
    settings.LDAP_ADMIN_GROUP_DN = ""
    login(claims(groups=[]))
    assert is_bot_admin(user)
    assert Group.objects.filter(name="BotAdmins").count() == 1


def test_logout_url_ends_keycloak_session():
    from broadcast.auth import keycloak_logout_url
    request = RequestFactory().post("/logout/")
    request.session = {"oidc_id_token": "tok"}
    url = keycloak_logout_url(request)
    assert url.startswith("https://kc.test/realms/test/protocol/openid-connect/logout?")
    assert "id_token_hint=tok" in url
    assert "post_logout_redirect_uri=http%3A%2F%2Ftestserver%2Flogged-out%2F" in url


def test_logout_url_without_keycloak_session():
    from broadcast.auth import keycloak_logout_url
    request = RequestFactory().post("/logout/")
    request.session = {}
    assert keycloak_logout_url(request) == "/logged-out/"


@pytest.mark.django_db
def test_login_redirects_to_keycloak():
    resp = Client().get("/login/")
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://kc.test/realms/test/protocol/openid-connect/auth?")
    assert "code_challenge=" in resp["Location"]


@pytest.mark.django_db
def test_expired_silent_recheck_sends_user_to_login():
    client = Client()
    session = client.session
    session["oidc_login_next"] = "/broadcast/"
    session.save()
    resp = client.get("/oidc/callback/", {"error": "login_required"})
    assert resp.status_code == 302
    assert resp["Location"] == "/login/?next=%2Fbroadcast%2F"


@pytest.mark.django_db
def test_failed_recheck_ends_session():
    client = Client()
    client.force_login(User.objects.create_user("alice"))
    resp = client.get("/oidc/callback/", {"error": "access_denied"})
    assert resp["Location"] == "/login/failed/"
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("path", ["/login/failed/", "/logged-out/"])
def test_status_pages_render_without_login(path):
    resp = Client().get(path)
    assert resp.status_code == 200
    assert b'href="/login/"' in resp.content
