"""
Local development settings for Sutawane Classes Management Software.
Uses SQLite (db.sqlite3), relaxed local HTTP security, and local directories.
"""

import os
from pathlib import Path

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, build_caches, build_logging, ensure_storage_directories, env_bool, parse_csv_env

ENVIRONMENT = 'development'

DEBUG = env_bool('DJANGO_DEBUG', default=True)

SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-lpe15v1#%e4koyiyw7z@fz6@o3fx0q)s2zc^49q$sc-l!=86y%',
)

ALLOWED_HOSTS = parse_csv_env('DJANGO_ALLOWED_HOSTS', '*') or ['*']

csrf_origins = parse_csv_env('DJANGO_CSRF_TRUSTED_ORIGINS', '')
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = csrf_origins

# Local Development Database: SQLite 3
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

# Local Cache
CACHES = build_caches(default_backend='locmem')

# Local Storage Directories
_env_media = os.getenv('DJANGO_MEDIA_ROOT')
if _env_media and (os.name != 'nt' or (os.path.isabs(_env_media) and Path(_env_media).parent.exists())):
    MEDIA_ROOT = Path(_env_media)
else:
    MEDIA_ROOT = BASE_DIR / 'media'

_env_backups = os.getenv('DJANGO_BACKUPS_DIR')
if _env_backups and (os.name != 'nt' or (os.path.isabs(_env_backups) and Path(_env_backups).parent.exists())):
    BACKUPS_DIR = Path(_env_backups)
else:
    BACKUPS_DIR = BASE_DIR / 'data' / 'backups'

LOGS_DIR = Path(os.getenv('DJANGO_LOGS_DIR') or (BASE_DIR / 'logs'))

ensure_storage_directories(MEDIA_ROOT, BACKUPS_DIR, LOGS_DIR)

# HTTPS disabled for local dev
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

LOGGING = build_logging(LOGS_DIR, level=os.getenv('DJANGO_LOG_LEVEL', 'INFO'))
