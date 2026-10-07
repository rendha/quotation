"""
quotations/backup.py - a safe copy of the SQLite database (it is made while the app is running).

    python manage.py backup_database                 -> <folder of the database>/backups/db-2026-10-06_1830.sqlite3
The newest 14 copies are kept.  Copy them OFF the server as well (a backup on the same disk is lost with the disk).
"""
import datetime
import pathlib
import sqlite3

KEEP = 14
PATTERN = "db-*.sqlite3"


def backup_sqlite(source, folder, keep=KEEP, now=None):
    """Copy the database at `source` into `folder`; delete the oldest copies beyond `keep`.  -> the path of the new copy."""
    source, folder = pathlib.Path(source), pathlib.Path(folder)
    if not source.exists():
        raise FileNotFoundError("There is no database at %s" % source)
    folder.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    target = folder / ("db-%s.sqlite3" % stamp)

    reader = sqlite3.connect(str(source))
    writer = sqlite3.connect(str(target))
    try:
        reader.backup(writer)               # SQLite's own online backup: consistent even while the app writes
    finally:
        writer.close()
        reader.close()

    for old in sorted(folder.glob(PATTERN))[:-keep] if keep > 0 else []:
        old.unlink()
    return target
