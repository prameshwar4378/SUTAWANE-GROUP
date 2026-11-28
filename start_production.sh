#!/bin/bash
set -e
export DJANGO_ENV=${DJANGO_ENV:-production}
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-SUTAWANE_EDUCATION.settings.production}
echo "============================================================"
echo "  SUTAWANE CLASSES MANAGEMENT SOFTWARE - PRODUCTION SERVER"
echo "============================================================"
echo "1. Applying database migrations..."
python manage.py migrate --noinput

echo "2. Collecting and compressing static assets..."
python manage.py collectstatic --noinput

echo "3. Starting Gunicorn WSGI server..."
exec gunicorn SUTAWANE_EDUCATION.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 3 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
