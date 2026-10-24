# =============================================================================
# Sutawane Classes Management Software - Production Dockerfile
# =============================================================================
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install essential system dependencies for image & document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Collect static files with WhiteNoise
RUN python manage.py collectstatic --noinput

# Ensure data and media directories exist
RUN mkdir -p /app/media /app/data /app/logs

EXPOSE 8000

# Run with Gunicorn WSGI production server
CMD ["gunicorn", "SUTAWANE_EDUCATION.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120"]
