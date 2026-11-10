"""PI 360 settings. All environment-specific values come from environment
variables (see ../.env.example). Defaults are safe for local development only."""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
    SECRET_KEY = "insecure-local-development-key"  # noqa: S105

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# In development the browser talks to the Vite dev server (:5173), which proxies /api to
# Django; the browser's Origin is then the Vite origin, so trust it (DEBUG only).
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else "",
)

# Which deployment this is; feature flags can target environments (T-039).
APP_ENV = os.environ.get("APP_ENV", "development")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.api",
    "apps.platform",
    "apps.audit",
    "apps.configuration",
    "apps.identity",
    "apps.participants",
    "apps.employers",
    "apps.referrals",
    "apps.placements",
    "apps.intelligence",
    "apps.imports",
    "apps.dataquality",
    "apps.reporting",
]

MIDDLEWARE = [
    "apps.platform.observability.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.identity.middleware.SessionPolicyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgres://pi360:pi360@localhost:5432/pi360",
        conn_max_age=60,
    )
}

# Argon2 first (CMP-03).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Session cookie auth, no tokens in the browser (ADR-023).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Idle timeout: the cookie expires this long after the last request (SEC-11).
# Absolute timeout: a session ends this long after sign-in however active it is.
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_IDLE_SECONDS", 30 * 60))
SESSION_SAVE_EVERY_REQUEST = True
CSRF_FAILURE_VIEW = "apps.api.problems.csrf_failure"
SESSION_ABSOLUTE_SECONDS = int(os.environ.get("SESSION_ABSOLUTE_SECONDS", 8 * 60 * 60))
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", 0))

# Staff authentication (T-034, FR-01, SEC-10). Defaults follow ADR-018 while D-031 is open.
AUTH_MAX_FAILURES = int(os.environ.get("AUTH_MAX_FAILURES", 5))
AUTH_LOCKOUT_SECONDS = int(os.environ.get("AUTH_LOCKOUT_SECONDS", 15 * 60))
# MFA is required for superusers, Django staff and holders of these roles. Set
# AUTH_MFA_ALL_STAFF=1 if CAP-YEI decides every staff account needs it (D-031).
AUTH_MFA_ROLES = env_list("AUTH_MFA_ROLES", "Administrator")
AUTH_MFA_ALL_STAFF = env_bool("AUTH_MFA_ALL_STAFF", False)
AUTH_MFA_PENDING_SECONDS = 5 * 60
OTP_TOTP_ISSUER = "CAP-YEI PI 360"
PASSWORD_RESET_TIMEOUT = int(os.environ.get("PASSWORD_RESET_TIMEOUT", 60 * 60))
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
# Email is gated by D-016/D-042. Until a provider is chosen, messages go to the log.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "pi360@localhost")
# The Django admin signs in with a password only, so it stays off outside local development.
# Staff are managed through the application (T-036).
ENABLE_ADMIN = env_bool("DJANGO_ENABLE_ADMIN", DEBUG)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.authentication.SessionAuthentication401",
    ],
    # Closed by default (SEC-06): a view must declare required_permission, or say
    # explicitly that it is public or sign-in only.
    "DEFAULT_PERMISSION_CLASSES": ["apps.api.access.HasPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.problems.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("API_THROTTLE_ANON", "60/min"),
        "user": os.environ.get("API_THROTTLE_USER", "600/min"),
        "login": os.environ.get("API_THROTTLE_LOGIN", "10/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PI 360 API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Structured JSON logs with the request ID on every line (CMP-15).
# LOG_FORMAT=text gives plain lines for local reading.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.platform.observability.RequestIdFilter"}},
    "formatters": {
        "json": {"()": "apps.platform.observability.JsonFormatter"},
        "text": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": os.environ.get("LOG_FORMAT", "json"),
        }
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# True only when every request arrives through our own nginx (docker-compose, staging).
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", False)

APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-dev")
