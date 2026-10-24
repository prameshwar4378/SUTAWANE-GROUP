@echo off
title Sutawane Classes - Production Server
echo ============================================================
echo   SUTAWANE CLASSES MANAGEMENT SOFTWARE - PRODUCTION SERVER
echo ============================================================
echo.
echo 1. Checking database migrations...
python manage.py migrate --noinput

echo 2. Collecting and compressing static assets...
python manage.py collectstatic --noinput

echo 3. Starting high-performance production server (Waitress)...
echo    Access URL: http://127.0.0.1:8000/
echo    Press Ctrl+C to stop the server.
echo.
python -m waitress --port=8000 --threads=4 SUTAWANE_EDUCATION.wsgi:application
pause
