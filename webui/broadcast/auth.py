"""Custom LDAP authentication backend.

Maps a configured LDAP group (LDAP_ADMIN_GROUP_DN) to the Django group
"BotAdmins" on every successful LDAP login. Falls through to
ModelBackend for local accounts (Django's default multi-backend behaviour).
"""
import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django_auth_ldap.backend import LDAPBackend

logger = logging.getLogger(__name__)


class CustomLDAPBackend(LDAPBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None:
            self._sync_bot_admins_group(user)
        return user

    def _sync_bot_admins_group(self, user) -> None:
        """Add or remove user from BotAdmins based on their LDAP group membership."""
        admin_group_dn = getattr(settings, "LDAP_ADMIN_GROUP_DN", "")
        if not admin_group_dn:
            return
        try:
            ldap_groups: list[str] = user.ldap_user.attrs.get("memberOf", [])
            group, _ = Group.objects.get_or_create(name="BotAdmins")
            if admin_group_dn in ldap_groups:
                user.groups.add(group)
                logger.info(f"User {user.username!r} added to BotAdmins.")
            else:
                user.groups.remove(group)
        except Exception as exc:
            logger.error(
                f"Failed to sync BotAdmins group for {user.username!r}: {exc}"
            )
