"""Management command: normalise_phones

Strips all non-digit characters from every phone field on Customer and
Supplier records, fixing any historical entries that were saved with a
leading '+', spaces, dashes, or other formatting characters.

Canonical stored format is digits only, e.g. 18687654321.

Each phone field on each object is checked and saved independently — a
fix to phone_1 never touches phone_2 or phone_3.

Usage:
    python manage.py normalise_phones            # dry run (no DB changes)
    python manage.py normalise_phones --apply    # write changes to database
"""

import re

from django.core.management.base import BaseCommand

from inventory.models import Supplier
from sales.models import Customer


def _digits_only(value: str) -> str:
    """Return only the digit characters from *value*."""
    return re.sub(r"\D", "", value or "")


PHONE_FIELDS = ("phone_1", "phone_2", "phone_3")


class Command(BaseCommand):
    help = "Normalise phone numbers to digits-only format across all Customer and Supplier records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to the database. Without this flag the command runs as a dry run.",
        )

    def handle(self, *args, **options):
        apply   = options["apply"]
        dry_run = not apply
        self.stdout.write(self.style.SUCCESS(f"Customers: {Customer.objects.count()}; Suppliers: {Supplier.objects.count()}"))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — no changes will be written. Pass --apply to commit.\n"
            ))

        total_fixed = 0

        for model in (Customer, Supplier):
            model_name = model.__name__
            objects    = model.objects.all().order_by("pk")
            self.stdout.write(f"\n{model_name} ({objects.count()} records)")

            for obj in objects:
                for field in PHONE_FIELDS:
                    original = getattr(obj, field) or ""

                    # Skip blank fields — nothing to fix.
                    if not original:
                        continue

                    cleaned = _digits_only(original)

                    # Skip fields that are already clean.
                    if original == cleaned:
                        continue

                    # Report the change.
                    self.stdout.write(
                        f"  {model_name} #{obj.pk} | {field}: "
                        f"{original!r}  →  {cleaned!r}"
                    )

                    if apply:
                        setattr(obj, field, cleaned)
                        obj.save(update_fields=[field])

                    total_fixed += 1

        # Summary
        self.stdout.write("")
        if total_fixed == 0:
            self.stdout.write(self.style.SUCCESS("All phone numbers are already clean. Nothing to do."))
        elif dry_run:
            self.stdout.write(self.style.WARNING(
                f"{total_fixed} field(s) would be updated. Run with --apply to commit."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"{total_fixed} field(s) updated successfully."
            ))
