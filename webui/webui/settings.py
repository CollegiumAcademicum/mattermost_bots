"""Django settings for webui."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load shared .env from the repo root (parent of webui/).
# Already-set environment variables take precedence (override=False).
load_dotenv(BASE_DIR.parent / ".env", override=False)

_INSECURE_KEY = "insecure-dev-key-do-not-use-in-production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _INSECURE_KEY)
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

if not DEBUG and SECRET_KEY == _INSECURE_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable must be set in production (DEBUG=False)."
    )
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "broadcast",
    "broadcast.admin_dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "webui.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "broadcast.context_processors.bot_admin",
            ],
        },
    }
]

WSGI_APPLICATION = "webui.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "webui.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/broadcast/"
LOGOUT_REDIRECT_URL = "/login/"

# LDAP — configured via environment variables.
try:
    import ldap
    from django_auth_ldap.config import LDAPSearch

    AUTH_LDAP_SERVER_URI = os.environ.get("LDAP_SERVER_URI", "ldap://localhost")
    AUTH_LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
    AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        os.environ.get("LDAP_USER_SEARCH_BASE", "dc=example,dc=com"),
        ldap.SCOPE_SUBTREE,
        "(uid=%(user)s)",
    )
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }

    # OPT_REFERRALS=0 is required for FreeIPA (prevents chasing referrals).
    AUTH_LDAP_GLOBAL_OPTIONS = {ldap.OPT_REFERRALS: 0}
    _ca_cert = os.environ.get("LDAP_CA_CERT_PATH", "")
    if _ca_cert:
        try:
            # Probe whether OPT_X_TLS_CACERTFILE is supported (fails on macOS).
            ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, _ca_cert)
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_CACERTFILE] = _ca_cert
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_DEMAND
        except ValueError:
            # macOS Secure Transport: cert pinning not supported via python-ldap.
            # Disable verification so TLS still works (dev only).
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_NEVER
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_NEWCTX] = 0

    AUTHENTICATION_BACKENDS = [
        "broadcast.auth.CustomLDAPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]
except ImportError:
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
    ]

# DN of the LDAP group whose members become "BotAdmins" in Django.
LDAP_ADMIN_GROUP_DN = os.environ.get("LDAP_ADMIN_GROUP_DN", "")

# postbot HTTP API
POSTBOT_API_URL = os.environ.get("POSTBOT_API_URL", "http://localhost:8000")
POSTBOT_API_SECRET = os.environ.get("POSTBOT_API_SECRET", "")
