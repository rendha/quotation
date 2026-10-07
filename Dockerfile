# One image for the server.  Build:  docker build -t dehlsen .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=quotation_pwa.settings_production

# The Linux libraries WeasyPrint needs to draw the PDFs (from the WeasyPrint installation guide for Debian).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt = your own  pip freeze  (see DEPLOY.md);  requirements-deploy.txt = what the server adds
COPY requirements.txt requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-deploy.txt

COPY . .

# Gather the static files (icons ...) once, at build time.  The settings need a key and an address to load: throw-away ones, used here only.
RUN DJANGO_SECRET_KEY=build-only-key-build-only-key-build-only-key DJANGO_ALLOWED_HOSTS=localhost python manage.py collectstatic --noinput

# the database lives in /data (a volume or the platform's disk); the app itself runs as a normal user.
# The start-up script hands /data to that user first (a disk mounted by Render belongs to root), then starts the app as appuser.
RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser /data /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh
ENV SQLITE_PATH=/data/db.sqlite3 \
    WEB_CONCURRENCY=1
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]

# update the database tables, then start the web server.  gunicorn reads the number of workers from WEB_CONCURRENCY
# (1 fits a small server; PDFs can take a few seconds, hence the long timeout)
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn quotation_pwa.wsgi:application --bind 0.0.0.0:${PORT:-8000} --timeout 120 --access-logfile -"]
