"""Keycloak (OIDC) login, modelled on CArtei's app/auth.py.

Maps a configured group (LDAP_ADMIN_GROUP_DN, matched by cn against the Keycloak
"groups" claim) to the Django group "BotAdmins" on every login and silent re-check.
Local password accounts stay available through /admin/ (ModelBackend).
"""
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import Group, User
from django.core.exceptions import SuspiciousOperation
from django.shortcuts import redirect
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView

logger = logging.getLogger(__name__)


def _dn_to_cn(dn: str) -> str:
    for part in dn.split(","):
        if part.lower().startswith("cn="):
            return part[3:]
    return dn


def claim_group_names(claims) -> set[str]:
    """Lowercased group names from the "groups" claim; tolerates full paths ("/ag.it")."""
    return {g.rsplit("/", 1)[-1].lower() for g in claims.get("groups", [])}


def keycloak_logout_url(request) -> str:
    """End the Keycloak session too, else the next login signs straight back in."""
    id_token = request.session.get("oidc_id_token")
    if not id_token:  # local account (/admin/): no Keycloak session to end
        return settings.LOGOUT_REDIRECT_URL
    params = {
        "id_token_hint": id_token,
        "post_logout_redirect_uri": request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL),
    }
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"


class KeycloakCallbackView(OIDCAuthenticationCallbackView):
    """OIDC callback, also hit by SessionRefresh's silent re-check every
    OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS, which re-syncs the BotAdmins group."""

    def get(self, request):
        if request.GET.get("error") in ("login_required", "interaction_required"):
            # Silent re-check found no Keycloak session (idle/expired): log in
            # interactively and come back to the page instead of the error page.
            next_url = request.session.get("oidc_login_next") or "/"
            auth.logout(request)
            return redirect(f"{reverse('login')}?{urlencode({'next': next_url})}")
        return super().get(request)

    def login_failure(self):
        # A failed re-check must end the session: the library would leave it alive
        # and bounce on every page load.
        if self.request.user.is_authenticated:
            auth.logout(self.request)
        return super().login_failure()


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    def verify_claims(self, claims):
        return bool(claims.get("preferred_username"))

    def get_or_create_user(self, access_token, id_token, payload):
        claims = self.get_userinfo(access_token, id_token, payload)
        if not self.verify_claims(claims):
            raise SuspiciousOperation("Claims verification failed: no preferred_username")
        username = claims["preferred_username"]
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User(username=username)
            user.set_unusable_password()
        elif user.has_usable_password():
            # Accounts from the former LDAP login have no usable password, so only
            # local accounts land here; a matching uid must not take them over.
            raise SuspiciousOperation(f"{username!r} is a local password account")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email = claims.get("email", "")
        user.save()
        self._sync_bot_admins_group(user, claim_group_names(claims))
        return user

    def _sync_bot_admins_group(self, user, group_names: set[str]) -> None:
        """Add or remove user from BotAdmins based on their Keycloak group membership."""
        admin_group_dn = getattr(settings, "LDAP_ADMIN_GROUP_DN", "")
        if not admin_group_dn:
            return
        group, _ = Group.objects.get_or_create(name="BotAdmins")
        if _dn_to_cn(admin_group_dn).lower() in group_names:
            user.groups.add(group)
        else:
            user.groups.remove(group)
