"""
python manage.py backup_database

Makes a dated copy of the SQLite database in the "backups" folder next to it (or in BACKUP_DIR) and keeps the newest 14.
Run it every day (see DEPLOY.md) and copy the files off the server now and then.
"""
import os
import pathlib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from quotations.backup import KEEP, backup_sqlite


class Command(BaseCommand):
    help = "Make a safe, dated copy of the SQLite database."

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if "sqlite" not in database["ENGINE"]:
            raise CommandError("backup_database only works with SQLite; use your database's own backup tool.")
        source = pathlib.Path(str(database["NAME"]))
        folder = pathlib.Path(os.environ.get("BACKUP_DIR") or source.parent / "backups")
        target = backup_sqlite(source, folder)
        self.stdout.write(self.style.SUCCESS("Backup written: %s  (the newest %d are kept)" % (target, KEEP)))
