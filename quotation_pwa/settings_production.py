"""
quotation_pwa/settings_production.py
====================================

The settings for the SERVER.  They start from your normal settings.py and change only what a public website needs:

    * the secret key, the allowed addresses and the secure cookies come from environment variables (never from the code)
    * sign-in for everybody (Django's LoginRequiredMiddleware) - a SWITCH: DJANGO_REQUIRE_LOGIN=false opens the app to everyone who has
      the address (for a test period); true (the default) makes everybody sign in
    * static files (icons ...) are served by WhiteNoise
    * the database is either the SQLite file on a persistent disk (SQLITE_PATH) or a Postgres database (DATABASE_URL)
    * on Render the website address is picked up by itself (RENDER_EXTERNAL_HOSTNAME)

Use it with:   DJANGO_SETTINGS_MODULE=quotation_pwa.settings_production
(the Dockerfile already does).  Your own settings.py is not changed, so  py manage.py runserver  keeps working as before.
"""
import os
import urllib.parse

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403   (everything from your normal settings)


def _env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _env_bool(name, default):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------------------------- secrets and addresses
DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a long random text (at least 32 characters).  "
                               "Make one with:  python -c \"import secrets; print(secrets.token_urlsafe(50))\"")

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS")

# the full address(es) with https://  -  needed so that forms (login, save) are accepted behind the proxy
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Render tells the app its own address (my-app.onrender.com): no need to type it anywhere
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host:
    if _render_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_render_host)
    if "https://" + _render_host not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append("https://" + _render_host)

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS to your website address, for example  quotes.example.com")

# ---------------------------------------------------------------------------------------------- HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")      # the proxy (Caddy / the platform) ends the HTTPS and says so
SECURE_SSL_REDIRECT = _env_bool("DJANGO_SSL_REDIRECT", True)
SECURE_REDIRECT_EXEMPT = [r"^offline/$"]                               # the platform's health check calls this page: never redirect it
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))   # raise (e.g. 31536000) once HTTPS works everywhere
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0

# ---------------------------------------------------------------------------------------------- sign-in for everything
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405


def _insert_after(anchor, new):
    if new in MIDDLEWARE:
        return
    if anchor not in MIDDLEWARE:
        raise ImproperlyConfigured("MIDDLEWARE of settings.py has no %s, so %s cannot be placed after it." % (anchor, new))
    MIDDLEWARE.insert(MIDDLEWARE.index(anchor) + 1, new)


REQUIRE_LOGIN = _env_bool("DJANGO_REQUIRE_LOGIN", True)     # true unless it is switched off on purpose
if REQUIRE_LOGIN:
    _insert_after("django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.auth.middleware.LoginRequiredMiddleware")
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "quotation_dashboard"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30          # stay signed in for 30 days on a phone

# ---------------------------------------------------------------------------------------------- static files
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    if "django.middleware.security.SecurityMiddleware" in MIDDLEWARE:
        MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    else:
        MIDDLEWARE.insert(0, "whitenoise.middleware.WhiteNoiseMiddleware")

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    **globals().get("STORAGES", {}),
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# ---------------------------------------------------------------------------------------------- database (SQLite on the persistent disk)
def _database_from_url(url):
    """postgresql://user:password@host:5432/name  ->  a Django DATABASES entry (what Render's "Internal Database URL" looks like)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("postgres", "postgresql"):
        raise ImproperlyConfigured("DATABASE_URL must start with postgres:// or postgresql://")
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ImproperlyConfigured("DATABASE_URL must look like postgresql://user:password@host:5432/databasename")
    entry = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": urllib.parse.unquote(parsed.path.lstrip("/")),
        "USER": urllib.parse.unquote(parsed.username or ""),
        "PASSWORD": urllib.parse.unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 60,
    }
    query = dict(urllib.parse.parse_qsl(parsed.query))
    if "sslmode" in query:
        entry["OPTIONS"] = {"sslmode": query["sslmode"]}
    return entry


if os.environ.get("DATABASE_URL"):                                      # Postgres (for example Render's free database)
    DATABASES = {"default": _database_from_url(os.environ["DATABASE_URL"])}
else:                                                                   # the SQLite file, on the persistent disk
    DATABASES = {"default": {**DATABASES["default"]}}  # noqa: F405
    if os.environ.get("SQLITE_PATH"):
        DATABASES["default"]["NAME"] = os.environ["SQLITE_PATH"]
    DATABASES["default"]["OPTIONS"] = {**DATABASES["default"].get("OPTIONS", {}), "timeout": 20}   # wait for a busy database instead of failing

# ---------------------------------------------------------------------------------------------- logs (the platform / docker shows them)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
