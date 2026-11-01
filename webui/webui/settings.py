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
    "mozilla_django_oidc.middleware.SessionRefresh",
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
LOGOUT_REDIRECT_URL = "/logged-out/"
LOGIN_REDIRECT_URL_FAILURE = "/login/failed/"

# Login: Keycloak (OIDC), which federates the FreeIPA directory. Endpoints are
# the realm's standard Keycloak paths (see /.well-known/openid-configuration).
KEYCLOAK_REALM_URL = os.environ.get(
    "KEYCLOAK_REALM_URL", "https://id.ca-hd.de/realms/collegium"
).rstrip("/")
_oidc = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect"
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_oidc}/auth"
OIDC_OP_TOKEN_ENDPOINT = f"{_oidc}/token"
OIDC_OP_USER_ENDPOINT = f"{_oidc}/userinfo"
OIDC_OP_JWKS_ENDPOINT = f"{_oidc}/certs"
OIDC_OP_LOGOUT_ENDPOINT = f"{_oidc}/logout"
OIDC_OP_LOGOUT_URL_METHOD = "broadcast.auth.keycloak_logout_url"
OIDC_RP_CLIENT_ID = os.environ.get("OIDC_RP_CLIENT_ID", "postbot")
OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_RP_CLIENT_SECRET", "")
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_RP_SCOPES = "openid email profile"
OIDC_USE_PKCE = True
OIDC_STORE_ID_TOKEN = True  # id_token_hint for Keycloak logout
# SessionRefresh (MIDDLEWARE): after this long, the next page load silently
# re-checks with Keycloak, re-syncing BotAdmins; refused -> logged out.
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 15 * 60

# ModelBackend: local password accounts, usable through /admin/ only.
AUTHENTICATION_BACKENDS = [
    "broadcast.auth.KeycloakOIDCBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# DN of the group whose members become "BotAdmins" in Django (matched by cn).
LDAP_ADMIN_GROUP_DN = os.environ.get("LDAP_ADMIN_GROUP_DN", "")

# postbot HTTP API
POSTBOT_API_URL = os.environ.get("POSTBOT_API_URL", "http://localhost:8000")
POSTBOT_API_SECRET = os.environ.get("POSTBOT_API_SECRET", "")

# --- Production security settings ---
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "false").lower() == "true"

_https = os.environ.get("HTTPS_ENABLED", "false").lower() == "true"
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https

_csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

SECURE_REFERRER_POLICY = "same-origin"

# --- Logging: stdout only ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
