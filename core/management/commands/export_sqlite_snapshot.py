"""Create a portable SQLite snapshot of the source database.

Dumps all LOCAL_APPS data (plus auth users) from the running database into a
fully-migrated SQLite file that can be downloaded and used locally for
debugging and development without needing a live database connection.

GENERIC UTILITY — designed to work in any Django project that follows the
BASE_DIR / PROJECT_ROOT layout convention (BASE_DIR = repo root containing
manage.py; PROJECT_ROOT = BASE_DIR.parent, the outer container folder).

Usage on the server
-------------------
    # dry run — see what would be exported and where
    python manage.py export_sqlite_snapshot

    # create the snapshot (defaults to PROJECT_ROOT/snapshot.sqlite3)
    python manage.py export_sqlite_snapshot --apply

    # custom output path (must be outside the repo)
    python manage.py export_sqlite_snapshot --apply --output /tmp/dev.sqlite3

    # overwrite an existing snapshot
    python manage.py export_sqlite_snapshot --apply --overwrite

Using the snapshot locally
--------------------------
Point your local dev settings at the file:

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": "/path/to/snapshot.sqlite3",
        }
    }

Then run the dev server as normal. No migrations needed — the schema is
already embedded in the snapshot.

What is included
----------------
All apps listed in settings.LOCAL_APPS (your project's own apps), plus auth
user accounts. This captures all business data while excluding
environment-specific noise (sessions, admin logs, content types, permissions).

What is excluded
----------------
- django.contrib.sessions          — session tokens are environment-specific
- django.contrib.admin (LogEntry)  — admin audit log, not business data
- django.contrib.contenttypes      — auto-rebuilt by migrate
- django.contrib.auth (except User) — permissions/groups are env-specific
"""

import tempfile
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections


def _get_local_app_labels() -> list[str]:
    """Return the app labels for this project's own apps (settings.LOCAL_APPS).

    Falls back to all installed non-Django apps if LOCAL_APPS is not defined,
    which makes the command usable in projects that don't separate DJANGO_APPS
    from LOCAL_APPS in their settings.
    """
    if hasattr(settings, "LOCAL_APPS"):
        # Strip any dotted module paths to bare app labels, e.g.
        # "myproject.inventory" → "inventory"
        return [label.rsplit(".", 1)[-1] for label in settings.LOCAL_APPS]

    # Fallback: every installed app that isn't a django.* or third-party one.
    # We identify "local" by checking whether the app's module path starts
    # with "django." — crude but workable as a generic fallback.
    return [
        app_config.label
        for app_config in django_apps.get_app_configs()
        if not app_config.name.startswith("django.")
    ]


class Command(BaseCommand):
    help = (
        "Export all local app data and user accounts to a migrated SQLite "
        "snapshot in PROJECT_ROOT (the folder above BASE_DIR). "
        "Useful for replicating production issues locally. "
        "Run without --apply for a dry run."
    )

    def add_arguments(self, parser):
        repo_root    = Path(settings.BASE_DIR).resolve()
        project_root = Path(getattr(settings, "PROJECT_ROOT", repo_root.parent)).resolve()
        default_out  = project_root / "snapshot.sqlite3"

        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually create the snapshot. Without this flag the command is a dry run.",
        )
        parser.add_argument(
            "--output",
            type=Path,
            default=default_out,
            help=f"SQLite file to create. Defaults to {default_out}.",
        )
        parser.add_argument(
            "--source",
            default="default",
            help="Django database alias to export (default: 'default').",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace an existing snapshot at the output path.",
        )

    def handle(self, *args, **options):
        repo_root    = Path(settings.BASE_DIR).resolve()
        project_root = Path(getattr(settings, "PROJECT_ROOT", repo_root.parent)).resolve()
        output_path  = options["output"].expanduser().resolve()
        source_alias = options["source"]
        apply        = options["apply"]

        # ── Validate the source alias ────────────────────────────────────
        if source_alias not in connections.databases:
            raise CommandError(
                f"Database alias '{source_alias}' is not configured. "
                f"Available: {', '.join(connections.databases.keys())}"
            )

        # ── Validate the output path ─────────────────────────────────────
        # The only hard rule: keep it outside the repo so it can't be
        # accidentally committed.
        def _is_inside(child: Path, parent: Path) -> bool:
            try:
                child.relative_to(parent)
                return True
            except ValueError:
                return False

        if _is_inside(output_path, repo_root):
            raise CommandError(
                f"Output path '{output_path}' is inside the Git repository "
                f"at '{repo_root}'.\n"
                "Choose any path outside the repo, e.g.:\n"
                f"    --output {project_root / 'snapshot.sqlite3'}"
            )

        if output_path.suffix.lower() not in {".sqlite3", ".sqlite", ".db"}:
            raise CommandError(
                "Output filename must end in .sqlite3, .sqlite, or .db."
            )

        if output_path.exists() and not options["overwrite"]:
            raise CommandError(
                f"'{output_path}' already exists. "
                "Re-run with --overwrite to replace it, or choose a different path."
            )

        # ── Collect the app labels to dump ───────────────────────────────
        local_labels = _get_local_app_labels()
        user_label   = get_user_model()._meta.label  # e.g. "auth.User"
        dump_targets = local_labels + [user_label]

        # ── Dry run report ───────────────────────────────────────────────
        self.stdout.write("\nExport plan")
        self.stdout.write(f"  Source database : {source_alias}")
        self.stdout.write(f"  Output file     : {output_path}")
        self.stdout.write(f"  Apps to dump    : {', '.join(local_labels)}")
        self.stdout.write(f"  Plus            : {user_label}")

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "\nDry run — no files written. Re-run with --apply to create the snapshot."
                )
            )
            return

        # ── Check for existing file ──────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()

        # ── Register a temporary dynamic DB alias for the SQLite target ──
        target_alias = "_snapshot_tmp_"
        if target_alias in connections.databases:
            raise CommandError(
                f"Temporary alias '{target_alias}' is already registered. "
                "A previous interrupted export may not have cleaned up. "
                "Restart the Django process and try again."
            )

        snapshot_config = connections.databases[source_alias].copy()
        snapshot_config.update({
            "ENGINE":   "django.db.backends.sqlite3",
            "NAME":     str(output_path),
            "USER":     "",
            "PASSWORD": "",
            "HOST":     "",
            "PORT":     "",
            "OPTIONS":  {},
        })
        connections.databases[target_alias] = snapshot_config

        fixture_path = None
        success      = False

        try:
            # Step 1: replay all migrations into the fresh SQLite file so the
            # schema is identical to what's in the source database.
            self.stdout.write("\n  [1/3] Building schema from migrations...")
            call_command(
                "migrate",
                database=target_alias,
                interactive=False,
                verbosity=0,
            )

            # Step 2: dump all target data from the source DB to a temporary
            # JSON fixture. Using the system temp directory keeps the file
            # well away from the repo regardless of where the command is run.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="snapshot_fixture_",
                delete=False,
            ) as fh:
                fixture_path = Path(fh.name)
                self.stdout.write(
                    f"  [2/3] Dumping data from '{source_alias}'..."
                )
                call_command(
                    "dumpdata",
                    *dump_targets,
                    database=source_alias,
                    indent=2,
                    stdout=fh,
                    verbosity=0,
                )

            # Guard against a silent empty dump (wrong alias, permissions, etc.)
            size = fixture_path.stat().st_size
            if size < 10:
                raise CommandError(
                    f"dumpdata produced an empty fixture ({size} bytes). "
                    f"Check that '{source_alias}' is correctly configured and "
                    "contains data."
                )

            # Step 3: load the fixture into the SQLite snapshot.
            self.stdout.write("  [3/3] Loading data into the snapshot...")
            call_command(
                "loaddata",
                str(fixture_path),
                database=target_alias,
                verbosity=0,
            )

            success = True

        finally:
            # Always clean up the dynamic alias and the temp fixture, even on error.
            connections[target_alias].close()
            del connections.databases[target_alias]

            if fixture_path and fixture_path.exists():
                fixture_path.unlink()

            if not success and output_path.exists():
                output_path.unlink()
                self.stdout.write(
                    self.style.WARNING(
                        "\nPartial snapshot deleted — see error above."
                    )
                )

        # ── Success summary ───────────────────────────────────────────────
        size_mb = output_path.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"\nSnapshot created ({size_mb:.2f} MB): {output_path}"
        ))
        self.stdout.write(
            f"\nTo use locally, set in your dev settings:\n"
            f'    DATABASES = {{"default": {{"ENGINE": "django.db.backends.sqlite3", '
            f'"NAME": "{output_path}"}}}}'
        )
