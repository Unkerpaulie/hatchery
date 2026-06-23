"""Migration: batch model expansion for chick purchasing and full lifecycle.

Operations:
  1. RenameField quantity → initial_quantity
  2. Add purchased_as, age_at_purchase, day_1_date fields
  3. AlterField status — new choices (new/incubating/hatched/raising/grown) and default
  4. RunPython data migration — 'ready' → 'new', 'done' → 'hatched' for existing rows
"""

from django.db import migrations, models


def migrate_statuses(apps, schema_editor):
    """Rename existing status values to match the new vocabulary."""
    Batch = apps.get_model("inventory", "Batch")
    Batch.objects.filter(status="ready").update(status="new")
    Batch.objects.filter(status="done").update(status="hatched")


def reverse_statuses(apps, schema_editor):
    """Reverse the status rename (used when reversing this migration)."""
    Batch = apps.get_model("inventory", "Batch")
    Batch.objects.filter(status="new").update(status="ready")
    Batch.objects.filter(status="hatched").update(status="done")


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0006_alter_expense_category"),
    ]

    operations = [
        # 1. Rename quantity → initial_quantity (preserves data, no default needed).
        migrations.RenameField(
            model_name="batch",
            old_name="quantity",
            new_name="initial_quantity",
        ),

        # 2a. purchased_as — immutable origin field; default 'eggs' covers all
        #     existing rows (they were all egg batches).
        migrations.AddField(
            model_name="batch",
            name="purchased_as",
            field=models.CharField(
                choices=[("eggs", "Eggs"), ("chicks", "Chicks")],
                default="eggs",
                help_text="What was purchased: eggs for incubation, or chicks ready for sale.",
                max_length=6,
            ),
        ),

        # 2b. age_at_purchase — nullable; only populated for chick batches.
        migrations.AddField(
            model_name="batch",
            name="age_at_purchase",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Age of chicks in days at time of purchase. Required for chick batches.",
            ),
        ),

        # 2c. day_1_date — age anchor; null for existing rows (unknown hatch date).
        migrations.AddField(
            model_name="batch",
            name="day_1_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text=(
                    "The anchor date for age tracking (day 1). Set when the batch is "
                    "first HATCHED; back-calculated for purchased chick batches."
                ),
            ),
        ),

        # 3. Update status field: new choices + new default.
        #    The max_length stays at 16 (longest value 'incubating' = 10).
        migrations.AlterField(
            model_name="batch",
            name="status",
            field=models.CharField(
                choices=[
                    ("new",        "New"),
                    ("incubating", "Incubating"),
                    ("hatched",    "Hatched"),
                    ("raising",    "Raising"),
                    ("grown",      "Grown"),
                ],
                default="new",
                max_length=16,
            ),
        ),

        # 4. Data migration: rename existing status values.
        #    Must run AFTER the AlterField so the new choices are accepted.
        migrations.RunPython(migrate_statuses, reverse_code=reverse_statuses),
    ]
