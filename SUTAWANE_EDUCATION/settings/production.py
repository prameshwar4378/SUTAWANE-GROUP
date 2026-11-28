"""
Production settings for Sutawane Classes Management Software.
Uses PostgreSQL, multi-worker safe caching, external VPS storage paths,
and production HTTPS / reverse-proxy security hardening.
"""

import os
from pathlib import Path
import dotenv
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, build_caches, build_logging, ensure_storage_directories, env_bool, parse_csv_env

# Allow an optional dedicated .env.production to override .env in production
_prod_env_file = BASE_DIR / '.env.production'
if _prod_env_file.exists():
    dotenv.load_dotenv(_prod_env_file, override=True)

ENVIRONMENT = 'production'

# Never default DEBUG to True in production
DEBUG = env_bool('DJANGO_DEBUG', default=False)

# Production Secret Key (must be explicitly configured)
_prod_secret = os.getenv('DJANGO_SECRET_KEY', '').strip()
_placeholder_secrets = {
    'change-this-to-a-strong-random-secret-key-in-production',
    'replace-with-strong-random-secret-key',
}
if not _prod_secret or _prod_secret in _placeholder_secrets:
    raise ImproperlyConfigured(
        "Production requires a strong DJANGO_SECRET_KEY in environment or .env/.env.production."
    )
SECRET_KEY = _prod_secret

# Production Hosts & CSRF Trusted Origins (domain + VPS IP)
_default_prod_hosts = [
    'portal.sutawanegroup.com',
    'sutawanegroup.com',
    'www.sutawanegroup.com',
    '173.249.33.152',
    '127.0.0.1',
    'localhost',
]
ALLOWED_HOSTS = parse_csv_env('DJANGO_ALLOWED_HOSTS', '') or _default_prod_hosts

_default_prod_origins = [
    'https://portal.sutawanegroup.com',
    'https://sutawanegroup.com',
    'https://www.sutawanegroup.com',
    'http://173.249.33.152:8080',
    'http://127.0.0.1:8080',
]
CSRF_TRUSTED_ORIGINS = parse_csv_env('DJANGO_CSRF_TRUSTED_ORIGINS', '') or _default_prod_origins

# Production Database: PostgreSQL
_db_password = os.getenv('DB_PASSWORD', '').strip()
if not _db_password:
    raise ImproperlyConfigured(
        "Production requires DB_PASSWORD for PostgreSQL in environment or .env/.env.production."
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'sutawane_db'),
        'USER': os.getenv('DB_USER', 'sutawane_user'),
        'PASSWORD': _db_password,
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '10')),
            'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
        },
    }
}

# Multi-worker safe caching (Redis if configured, otherwise FileBasedCache shared across Gunicorn workers)
CACHES = build_caches(default_backend='filebased')

# External Production Storage Paths (survive code pulls and redeployments)
_default_prod_media = Path('/home/sutawane/media')
_default_prod_backups = Path('/home/sutawane/backup_zip')
_default_prod_logs = Path('/home/sutawane/logs')

_env_media = os.getenv('DJANGO_MEDIA_ROOT')
if _env_media:
    MEDIA_ROOT = Path(_env_media)
elif _default_prod_media.exists() or (os.name != 'nt' and Path('/home/sutawane').exists()):
    MEDIA_ROOT = _default_prod_media
else:
    MEDIA_ROOT = BASE_DIR / 'media'

_env_backups = os.getenv('DJANGO_BACKUPS_DIR')
if _env_backups:
    BACKUPS_DIR = Path(_env_backups)
elif _default_prod_backups.exists() or (os.name != 'nt' and Path('/home/sutawane').exists()):
    BACKUPS_DIR = _default_prod_backups
else:
    BACKUPS_DIR = BASE_DIR / 'data' / 'backups'

_env_logs = os.getenv('DJANGO_LOGS_DIR')
if _env_logs:
    LOGS_DIR = Path(_env_logs)
elif _default_prod_logs.exists() or (os.name != 'nt' and Path('/home/sutawane').exists()):
    LOGS_DIR = _default_prod_logs
else:
    LOGS_DIR = BASE_DIR / 'logs'

ensure_storage_directories(MEDIA_ROOT, BACKUPS_DIR, LOGS_DIR)

# Reverse Proxy & HTTPS Security Hardening
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

SECURE_SSL = env_bool('DJANGO_SECURE_SSL', default=False)
if SECURE_SSL:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', default=True)
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', default=True)
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0

# Production Rotating File Logging (10 MB x 10 files)
LOGGING = build_logging(
    LOGS_DIR,
    level=os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    max_bytes=10 * 1024 * 1024,
    backup_count=10,
)
