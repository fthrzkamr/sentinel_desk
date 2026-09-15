from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(PROJECT_ROOT / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

DJANGO_APPS = [
    "daphne",  # must stay first: makes `runserver` ASGI/WebSocket-aware
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "channels",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.devices",
    "apps.monitoring",
    "apps.locations",
    "apps.software",
    "apps.alerts",
    "apps.audit",
    "apps.livescreen",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL")
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Asia/Jakarta")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis / Channels ---
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# --- Celery ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

CELERY_BEAT_SCHEDULE = {
    "mark-stale-devices-offline": {
        "task": "apps.monitoring.tasks.mark_stale_devices_offline",
        "schedule": 20.0,
    },
    "prune-old-metrics": {
        "task": "apps.monitoring.tasks.prune_old_metrics",
        "schedule": 3600.0,
    },
}

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "config.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "agent": "120/min",
        # Baseline ceiling for every authenticated endpoint that doesn't
        # declare its own throttle_scope (Alerts, Users, Audit Logs, etc.) —
        # ScopedRateThrottle silently skips any view without a scope, so
        # without this those endpoints had no rate limit at all.
        "user": "300/min",
    },
    "DATETIME_FORMAT": "iso-8601",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_CREDENTIALS = True

# --- Security headers (safe defaults, tightened further in production.py) ---
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- SentinelDesk domain settings ---
DEVICE_OFFLINE_THRESHOLD_SECONDS = env.int("DEVICE_OFFLINE_THRESHOLD_SECONDS", default=60)
DEFAULT_MONITOR_INTERVAL_SECONDS = env.int("DEFAULT_MONITOR_INTERVAL_SECONDS", default=15)
ENROLLMENT_TOKEN_TTL_MINUTES = env.int("ENROLLMENT_TOKEN_TTL_MINUTES", default=60)
DEVICE_METRIC_RETENTION_DAYS = env.int("DEVICE_METRIC_RETENTION_DAYS", default=7)

# Device status thresholds — CRITICAL takes priority over WARNING when both match.
CPU_WARNING_PERCENT = env.float("CPU_WARNING_PERCENT", default=80)
CPU_CRITICAL_PERCENT = env.float("CPU_CRITICAL_PERCENT", default=95)
RAM_WARNING_PERCENT = env.float("RAM_WARNING_PERCENT", default=80)
RAM_CRITICAL_PERCENT = env.float("RAM_CRITICAL_PERCENT", default=95)
DISK_WARNING_PERCENT = env.float("DISK_WARNING_PERCENT", default=85)
DISK_CRITICAL_PERCENT = env.float("DISK_CRITICAL_PERCENT", default=95)
BATTERY_CRITICAL_PERCENT = env.float("BATTERY_CRITICAL_PERCENT", default=10)

# --- Location (Phase 5) ---
# Free-tier lookup, city-level accuracy only — see apps/locations/services.py.
IP_GEOLOCATION_API_URL = env("IP_GEOLOCATION_API_URL", default="http://ip-api.com/json/")
IP_GEOLOCATION_TIMEOUT_SECONDS = env.float("IP_GEOLOCATION_TIMEOUT_SECONDS", default=5)
