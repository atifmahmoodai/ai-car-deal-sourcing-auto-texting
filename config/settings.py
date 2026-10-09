import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.getenv("ENVIRONMENT") == "production"
SECRET_KEY = os.getenv(
    "SECRET_KEY", "development-only-scoutdesk-key-not-for-deployment"
)
if PRODUCTION and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith("development")):
    raise RuntimeError(
        "Production requires an independent SECRET_KEY of at least 50 characters."
    )
DEBUG = not PRODUCTION
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "http://127.0.0.1:8092").rstrip("/")
if PRODUCTION and (not PUBLIC_ORIGIN.startswith("https://") or "*" in ALLOWED_HOSTS):
    raise RuntimeError("Configure HTTPS PUBLIC_ORIGIN and explicit ALLOWED_HOSTS.")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "scout",
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
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "data.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
if os.getenv("DATABASE_URL"):
    u = urlsplit(os.environ["DATABASE_URL"])
    if u.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("Use PostgreSQL DATABASE_URL.")
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": u.path.lstrip("/"),
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname,
        "PORT": u.port or 5432,
        "CONN_MAX_AGE": 60,
    }
if PRODUCTION and DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    raise RuntimeError("Production requires PostgreSQL.")
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 14},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 28800
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
CSRF_TRUSTED_ORIGINS = [PUBLIC_ORIGIN]
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
# Host-only HSTS: subdomain/preload policy requires domain-owner approval.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
if os.getenv("TRUST_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
OUTBOUND_ENABLED = os.getenv("OUTBOUND_ENABLED") == "1"
DEALER_NAME = os.getenv("DEALER_NAME", "Example Dealership")
HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN", "")
HUBSPOT_PIPELINE = os.getenv("HUBSPOT_PIPELINE", "")
HUBSPOT_STAGES = dict(
    x.split("=", 1) for x in os.getenv("HUBSPOT_STAGES", "").split(",") if "=" in x
)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
FEED_HOSTS = set(filter(None, os.getenv("FEED_HOSTS", "").split(",")))
HUBSPOT_CURRENCY = os.getenv("HUBSPOT_CURRENCY", "USD")
MIDDLEWARE.append("scout.middleware.SecurityHeaders")

INSTANCE_ID = os.getenv("INSTANCE_ID", "development-scout")
if PRODUCTION:
    import uuid

    try:
        uuid.UUID(INSTANCE_ID)
    except ValueError:
        raise RuntimeError(
            "Set a permanent, unique INSTANCE_ID UUID for CRM identities."
        )
