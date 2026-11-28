"""
Shared Django base settings for Sutawane Classes Management Software.
Environment-specific overrides live in development.py and production.py.
"""

import os
import sys
from pathlib import Path
import dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env if present
dotenv.load_dotenv(BASE_DIR / '.env')

# Add apps directory to sys.path
if str(BASE_DIR / 'apps') not in sys.path:
    sys.path.insert(0, str(BASE_DIR / 'apps'))


def env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variable safely."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('true', '1', 'yes', 'on')


def parse_csv_env(name: str, default: str = '') -> list[str]:
    """Parse comma-separated environment variable into stripped non-empty entries."""
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


def build_caches(default_backend: str = 'locmem') -> dict:
    """Configure Redis, FileBasedCache, or LocMemCache for the current environment."""
    redis_url = os.getenv('REDIS_URL') or os.getenv('CACHE_URL')
    cache_choice = os.getenv('DJANGO_CACHE_BACKEND', '').strip().lower() or default_backend

    if redis_url:
        return {
            'default': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': redis_url,
                'TIMEOUT': 300,
                'KEY_PREFIX': 'sutawane',
                'OPTIONS': {
                    'socket_connect_timeout': 3,
                    'socket_timeout': 3,
                },
            }
        }

    if cache_choice == 'filebased':
        cache_dir = Path(os.getenv('DJANGO_CACHE_DIR') or (BASE_DIR / 'cache_storage'))
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return {
            'default': {
                'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
                'LOCATION': str(cache_dir),
                'TIMEOUT': 300,
                'KEY_PREFIX': 'sutawane',
                'OPTIONS': {
                    'MAX_ENTRIES': 10000,
                    'CULL_FREQUENCY': 3,
                },
            }
        }

    return {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'sutawane-classes-cache',
            'TIMEOUT': 300,
            'KEY_PREFIX': 'sutawane',
            'OPTIONS': {
                'MAX_ENTRIES': 5000,
                'CULL_FREQUENCY': 3,
            },
        }
    }


def ensure_storage_directories(media_root: Path, backups_dir: Path, logs_dir: Path) -> None:
    """Create media, backup, and log directories if filesystem permissions allow."""
    for directory in (
        media_root,
        media_root / 'photos',
        media_root / 'attachments',
        backups_dir,
        logs_dir,
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def build_logging(logs_dir: Path, level: str = 'INFO', max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5) -> dict:
    """Build structured console + rotating file logging configuration."""
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '[{asctime}] {levelname} [{name}] {message}',
                'style': '{',
            },
            'simple': {
                'format': '[{asctime}] {levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(logs_dir / 'sutawane_system.log'),
                'maxBytes': max_bytes,
                'backupCount': backup_count,
                'formatter': 'verbose',
                'encoding': 'utf-8',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['console', 'file'],
                'level': level,
                'propagate': True,
            },
            'MyApp': {
                'handlers': ['console', 'file'],
                'level': level,
                'propagate': True,
            },
        },
    }


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'MyApp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'MyApp.middleware.SoftwareLicenseAndAuthMiddleware',
]

ROOT_URLCONF = 'SUTAWANE_EDUCATION.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'MyApp' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'MyApp.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'SUTAWANE_EDUCATION.wsgi.application'
ASGI_APPLICATION = 'SUTAWANE_EDUCATION.asgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files (WhiteNoise compressed assets)
STATIC_URL = '/static/'
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
WHITENOISE_MAX_AGE = int(os.getenv('WHITENOISE_MAX_AGE', 31536000))
WHITENOISE_IMMUTABLE_FILE_TEST = lambda path, url: True

MEDIA_URL = '/media/'

# Shared Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = os.getenv('DJANGO_X_FRAME_OPTIONS', 'SAMEORIGIN')
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Email Configuration (Developer OTP & System Alerts)
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'prameshwar4378@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', 'pkppqklbhjjtbont')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '"Sutawane Software Support" <prameshwar4378@gmail.com>')
SERVER_EMAIL = os.getenv('SERVER_EMAIL', 'prameshwar4378@gmail.com')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '15'))
