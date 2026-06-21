"""Custom login view — adds LDAP availability check to login page context."""
import logging

from django.conf import settings
from django.contrib.auth.views import LoginView

logger = logging.getLogger(__name__)


def _ldap_available() -> bool:
    """Return False if LDAP is configured but unreachable."""
    uri = getattr(settings, "AUTH_LDAP_SERVER_URI", None)
    if not uri:
        return True  # LDAP not configured — no warning needed
    try:
        import ldap as _ldap
        for opt, val in getattr(settings, "AUTH_LDAP_GLOBAL_OPTIONS", {}).items():
            _ldap.set_option(opt, val)
        conn = _ldap.initialize(uri)
        conn.set_option(_ldap.OPT_NETWORK_TIMEOUT, 2)
        conn.set_option(_ldap.OPT_TIMEOUT, 2)
        conn.simple_bind_s(
            getattr(settings, "AUTH_LDAP_BIND_DN", ""),
            getattr(settings, "AUTH_LDAP_BIND_PASSWORD", ""),
        )
        conn.unbind_s()
        return True
    except Exception as exc:
        logger.warning(f"LDAP unavailable: {exc}")
        return False


class LDAPAwareLoginView(LoginView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ldap_unavailable"] = not _ldap_available()
        return ctx
