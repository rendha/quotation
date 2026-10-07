#!/bin/sh
# Starts the app:  0. waits for the database   1. updates the database tables   2. loads the first-time data ONCE   3. runs the web server.
#
# First-time data = seed/seed.json (your rate sheet, panels, structure settings ...).  It is loaded only when the file exists AND the
# database has no products yet, so a restart or an update never overwrites what you changed later.
set -e

SEED_FILE="${SEED_FILE:-/app/seed/seed.json}"

# A new database needs a few minutes to start, and a sleeping free service wakes up before its database is ready sometimes: wait for it
# (up to 36 tries, 5 seconds apart = 3 minutes) instead of failing at the first "Connection refused".  A SQLite file answers at once.
CHECK_DATABASE='import django; django.setup(); from django.db import connection; connection.ensure_connection()'
tries=0
until python -c "$CHECK_DATABASE" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge "${DB_WAIT_TRIES:-36}" ]; then
        echo "The database did not answer after $tries tries.  Is it 'Available' in the dashboard?  Is DATABASE_URL the Internal URL of THAT database?"
        python -c "$CHECK_DATABASE" || true                      # once more, this time showing the real error
        exit 1
    fi
    echo "Waiting for the database ($tries) ..."
    sleep "${DB_WAIT_SECONDS:-5}"
done
echo "The database answers."

python manage.py migrate --noinput

if [ -f "$SEED_FILE" ]; then
    status=0
    python manage.py shell -c "import sys; from quotations.models import Product; sys.exit(0 if Product.objects.exists() else 1)" >/dev/null 2>&1 || status=$?
    case "$status" in
        0) echo "The database already has data: the first-time data is NOT loaded." ;;
        1) echo "Empty database: loading the first-time data from $SEED_FILE"
           python manage.py loaddata "$SEED_FILE" ;;
        *) echo "Could not check the database (code $status): the first-time data is NOT loaded." ;;
    esac
fi

exec gunicorn quotation_pwa.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --timeout 120 --access-logfile -
