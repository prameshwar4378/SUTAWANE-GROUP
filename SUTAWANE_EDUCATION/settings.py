"""
Django settings for SUTAWANE_EDUCATION project.
Production-ready configuration with WhiteNoise static compression, environment
variable overrides, security headers, and structured logging.
"""

import os
import sys
from pathlib import Path
import dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
dotenv.load_dotenv(BASE_DIR / '.env')

# Add apps directory to sys.path
sys.path.insert(0, str(BASE_DIR / 'apps'))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-lpe15v1#%e4koyiyw7z@fz6@o3fx0q)s2zc^49q$sc-l!=86y%'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

# Allowed Hosts configuration
allowed_hosts_raw = os.getenv('DJANGO_ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw.split(',') if h.strip()]

# CSRF Trusted Origins for reverse proxies (Render, Railway, Nginx, HTTPS domains)
csrf_origins_raw = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '')
if csrf_origins_raw:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins_raw.split(',') if o.strip()]


# Application definition

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

# -----------------------------------------------------------------------------
# Production Caching Architecture (Redis / File-Based / LocMem)
# -----------------------------------------------------------------------------
# Supports Redis (REDIS_URL or CACHE_URL), FileBasedCache, or high-capacity LocMemCache.
REDIS_URL = os.getenv('REDIS_URL') or os.getenv('CACHE_URL')
CACHE_BACKEND_CHOICE = os.getenv('DJANGO_CACHE_BACKEND', '').lower()

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,
            'KEY_PREFIX': 'sutawane',
            'OPTIONS': {
                'socket_connect_timeout': 3,
                'socket_timeout': 3,
            }
        }
    }
elif CACHE_BACKEND_CHOICE == 'filebased':
    CACHE_DIR = BASE_DIR / 'cache_storage'
    try:
        CACHE_DIR.mkdir(exist_ok=True)
    except Exception:
        pass
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': str(CACHE_DIR),
            'TIMEOUT': 300,
            'KEY_PREFIX': 'sutawane',
            'OPTIONS': {
                'MAX_ENTRIES': 10000,
                'CULL_FREQUENCY': 3,
            }
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'sutawane-classes-cache',
            'TIMEOUT': 300,
            'KEY_PREFIX': 'sutawane',
            'OPTIONS': {
                'MAX_ENTRIES': 5000,
                'CULL_FREQUENCY': 3,
            }
        }
    }

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


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images) with WhiteNoise compression
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Security Headers & Hardening
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = os.getenv('DJANGO_X_FRAME_OPTIONS', 'SAMEORIGIN')

# HTTPS / SSL Hardening (Enabled when DJANGO_SECURE_SSL=True in production environment)
SECURE_SSL = os.getenv('DJANGO_SECURE_SSL', 'False').lower() in ('true', '1', 'yes')
if SECURE_SSL:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Email Configuration (Google SMTP for Developer OTP & System Alerts)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'prameshwar4378@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', 'pkppqklbhjjtbont')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', '"Sutawane Software Support" <prameshwar4378@gmail.com>')
SERVER_EMAIL = os.getenv('SERVER_EMAIL', 'prameshwar4378@gmail.com')
EMAIL_TIMEOUT = 15


# Production Structured Logging
LOGS_DIR = BASE_DIR / 'logs'
try:
    LOGS_DIR.mkdir(exist_ok=True)
except Exception:
    pass

LOGGING = {
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
            'filename': str(LOGS_DIR / 'sutawane_system.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'MyApp': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
