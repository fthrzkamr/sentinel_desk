from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = False

# Off by default: the nginx shipped in nginx/conf.d only listens on plain
# HTTP 80 right now (no domain/certificate exists to terminate TLS with —
# see nginx/conf.d/default.conf). Forcing SECURE_SSL_REDIRECT on without TLS
# actually present would redirect every request in an infinite loop instead
# of hardening anything. Once a real domain + certificate are added to
# nginx (uncomment the 443 block, point it at the cert), set
# DJANGO_HTTPS_ENABLED=true in .env.prod to turn all of this on for real.
HTTPS_ENABLED = env.bool("DJANGO_HTTPS_ENABLED", default=False)
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
if HTTPS_ENABLED:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Daphne only ever sees plain HTTP from the nginx reverse proxy in front of
# it (TLS, once configured, terminates at nginx) — without this, Django
# can't tell the original request was HTTPS and SECURE_SSL_REDIRECT loops.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
# Needed alongside the two settings above whenever the admin/browsable-API's
# session-and-cookie based forms (not the JWT API the SPA uses) are reached
# over HTTPS from these origins — Django checks this independently of CORS.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# Serves collected static files (Django admin's own CSS/JS) directly from
# the Daphne process — no separate static-file volume/service to keep in
# sync with the app container.
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Opt-in — a no-op until a real SENTRY_DSN exists (no deployment target yet).
SENTRY_DSN = env("SENTRY_DSN", default=None)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
    )
