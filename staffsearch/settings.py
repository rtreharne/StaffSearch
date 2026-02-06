import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if "staffsearch.uniwebprod.co.uk" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("staffsearch.uniwebprod.co.uk")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "directory",
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

ROOT_URLCONF = "staffsearch.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "directory" / "templates"],
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

WSGI_APPLICATION = "staffsearch.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/staffsearch")
parsed_db = urlparse(DATABASE_URL)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed_db.path.lstrip("/"),
        "USER": parsed_db.username,
        "PASSWORD": parsed_db.password,
        "HOST": parsed_db.hostname,
        "PORT": parsed_db.port or "5432",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# CSRF
CSRF_TRUSTED_ORIGINS = [
    "https://staffsearch.uniwebprod.co.uk",
    "https://staffsearch.uniwebdev.co.uk",
]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow embedding in iframes (e.g., for /embed/).
X_FRAME_OPTIONS = "ALLOWALL"

# Auth
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/admin-dashboard/"
LOGOUT_REDIRECT_URL = "/"

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# Crawler
CRAWL_SEED_URL = os.getenv("CRAWL_SEED_URL", "https://liverpool.ac.uk/")
CRAWL_SEED_URLS = [u.strip() for u in os.getenv("CRAWL_SEED_URLS", "").split(",") if u.strip()]
CRAWL_RATE_LIMIT = float(os.getenv("CRAWL_RATE_LIMIT", "1.0"))
CRAWL_MAX_DEPTH = int(os.getenv("CRAWL_MAX_DEPTH", "6"))
CRAWL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "4"))
CRAWL_ALLOWLIST_DOMAIN = os.getenv("CRAWL_ALLOWLIST_DOMAIN", "liverpool.ac.uk")
CRAWL_KEEP_PATH_REGEX = os.getenv("CRAWL_KEEP_PATH_REGEX", r"^/people/[^/]+/?$")

# Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BEAT_SCHEDULE = {
    "weekly-crawl": {
        "task": "directory.tasks.run_weekly_crawl",
        "schedule": 60 * 60 * 24 * 7,
    }
}
