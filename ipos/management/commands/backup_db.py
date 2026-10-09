"""
Dump the database to backups/ with pg_dump, keeping the newest N dumps.

    python manage.py backup_db
    python manage.py backup_db --keep 30 --dir D:/ipo-backups

Restore one into an empty database with:

    pg_restore --clean --if-exists -d ipo_tracker backups/ipo_tracker-20261009-0800.dump

PANs in the dump are encrypted with FIELD_ENCRYPTION_KEY from .env. A dump
without that key is unreadable, so keep a copy of the key somewhere safe,
but not next to the dumps: a leaked backup folder should not hold both.

pg_dump must be on PATH, or set PG_DUMP to its full path (on Windows,
e.g. C:/Program Files/PostgreSQL/16/bin/pg_dump.exe).
"""

import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Back up the database with pg_dump and prune old backups."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(Path(settings.BASE_DIR) / "backups"),
                            help="Folder for the dumps (default: backups/ in the repo).")
        parser.add_argument("--keep", type=int, default=14, help="How many dumps to keep (default 14).")

    def handle(self, *args, **options):
        if options["keep"] < 1:
            raise CommandError("--keep must be at least 1.")
        pg_dump = os.environ.get("PG_DUMP") or shutil.which("pg_dump")
        if not pg_dump:
            raise CommandError("pg_dump not found. Add PostgreSQL's bin folder to PATH or set PG_DUMP.")

        db = connection.settings_dict
        folder = Path(options["dir"])
        folder.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        target = folder / f"{db['NAME']}-{stamp}.dump"
        partial = target.with_suffix(".partial")

        cmd = [pg_dump, "--format=custom", "--no-owner", f"--file={partial}",
               f"--host={db.get('HOST') or 'localhost'}", f"--port={db.get('PORT') or 5432}",
               f"--username={db['USER']}", db["NAME"]]
        # Password via the environment, never the command line (visible in
        # the process list).
        env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            partial.unlink(missing_ok=True)
            raise CommandError(f"pg_dump failed: {result.stderr.strip()}")
        # Renamed only once complete, so a crash never leaves a dump that
        # looks good and isn't — and never prunes a good one in its favour.
        partial.replace(target)

        dumps = sorted(folder.glob(f"{db['NAME']}-*.dump"))
        for old in dumps[:-options["keep"]]:
            old.unlink()
        size_kb = target.stat().st_size // 1024
        self.stdout.write(self.style.SUCCESS(
            f"Backed up to {target} ({size_kb} KB). Keeping {min(len(dumps), options['keep'])} dump(s)."
        ))
