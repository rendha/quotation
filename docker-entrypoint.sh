#!/bin/sh
# Starts the app.  A disk that the platform (Render) mounts belongs to root, but the app runs as the normal user "appuser":
# hand the data folder over first, then run the command as appuser.
set -e

DATA_DIR="${DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown -R appuser:appuser "$DATA_DIR"
    exec runuser -u appuser -- "$@"
fi

exec "$@"
