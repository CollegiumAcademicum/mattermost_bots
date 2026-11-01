"""Test settings: skip LDAP imports, use in-memory DB."""
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]
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
            ],
        },
    }
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/broadcast/"
LOGOUT_REDIRECT_URL = "/logged-out/"
POSTBOT_API_URL = "http://postbot-test:8000"
POSTBOT_API_SECRET = "test-secret"
STATIC_URL = "static/"
STATIC_ROOT = "/tmp/staticfiles"

KEYCLOAK_REALM_URL = "https://kc.test/realms/test"
_oidc = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect"
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_oidc}/auth"
OIDC_OP_TOKEN_ENDPOINT = f"{_oidc}/token"
OIDC_OP_USER_ENDPOINT = f"{_oidc}/userinfo"
OIDC_OP_JWKS_ENDPOINT = f"{_oidc}/certs"
OIDC_OP_LOGOUT_ENDPOINT = f"{_oidc}/logout"
OIDC_OP_LOGOUT_URL_METHOD = "broadcast.auth.keycloak_logout_url"
OIDC_RP_CLIENT_ID = "postbot"
OIDC_RP_CLIENT_SECRET = "test-secret"
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_USE_PKCE = True
OIDC_STORE_ID_TOKEN = True
LOGIN_REDIRECT_URL_FAILURE = "/login/failed/"
LDAP_ADMIN_GROUP_DN = "cn=ag.it,cn=groups,dc=test"
