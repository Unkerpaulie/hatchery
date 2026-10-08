"""Step 2 of 3: one-time data migration — seed categories and convert expenses.

Creates one ExpenseCategory row for each of the 14 hard-coded categories that
existed before this feature (using their display labels, so the client sees
exactly the names she already knows), then points every existing expense at the
matching row via the temporary ``category_new`` FK.

Why a migration rather than a standalone script: Django records applied
migrations per database, so this runs exactly once on each database and is
guaranteed to complete before the old CharField is dropped in 0014. A separate
manual script would leave a window where production expenses have no category
if it were run late or forgotten.

Only runs when the database already has expenses, i.e. when it is *converting*
an existing install. Fresh databases (new installs, test databases, and the
SQLite file built by ``export_sqlite_snapshot``, which replays migrations and
then loads production rows into it) are left empty. Seeding those would put
stale default categories in the snapshot that clash with production's real,
possibly renamed or deleted, categories.

Legacy slugs not in the list below (e.g. from older choice lists) get a
category created from the slug itself, so no expense is ever left uncategorized
by the conversion.

Reversible: the reverse step writes slugs back into the CharField. Custom
categories the client created after migrating collapse to "other" on reverse,
since the old column can only hold the original 14 values.
"""

from django.db import migrations

# (slug, label) pairs exactly as defined by Expense.Category before this change.
LEGACY_CATEGORIES = [
    ("cleaning", "Cleaning"),
    ("customs_excise", "Customs & Excise"),
    ("electricity", "Electricity"),
    ("equipment", "Equipment"),
    ("feed", "Feed"),
    ("labor", "Labor"),
    ("maintenance", "Maintenance"),
    ("medicine", "Medicine"),
    ("packaging", "Packaging"),
    ("phone", "Phone"),
    ("service_charges", "Service Charges"),
    ("supplies", "Supplies"),
    ("transport", "Transport"),
    ("other", "Other"),
]


def _get_or_create(ExpenseCategory, name):
    """Case-insensitive get-or-create, mirroring the model's unique constraint."""
    return (
        ExpenseCategory.objects.filter(name__iexact=name).first()
        or ExpenseCategory.objects.create(name=name)
    )


def seed_and_convert(apps, schema_editor):
    ExpenseCategory = apps.get_model("inventory", "ExpenseCategory")
    Expense = apps.get_model("inventory", "Expense")

    if not Expense.objects.exists():
        return  # fresh database: nothing to convert, start with no categories

    category_by_slug = {
        slug: _get_or_create(ExpenseCategory, label)
        for slug, label in LEGACY_CATEGORIES
    }

    # Any slug in use that isn't one of the 14 (defensive; choices were only
    # enforced at the form level, never by the database).
    in_use = set(Expense.objects.order_by().values_list("category", flat=True).distinct())
    for slug in in_use - set(category_by_slug):
        if slug:
            label = slug.replace("_", " ").strip().title()
            category_by_slug[slug] = _get_or_create(ExpenseCategory, label)

    for slug, category in category_by_slug.items():
        Expense.objects.filter(category=slug).update(category_new=category)


def restore_slugs(apps, schema_editor):
    ExpenseCategory = apps.get_model("inventory", "ExpenseCategory")
    Expense = apps.get_model("inventory", "Expense")

    slug_by_label = {label.lower(): slug for slug, label in LEGACY_CATEGORIES}
    for category in ExpenseCategory.objects.all():
        slug = slug_by_label.get(category.name.lower(), "other")
        Expense.objects.filter(category_new=category).update(category=slug)
    # The old column was NOT NULL, so uncategorized expenses fall back to "other".
    Expense.objects.filter(category_new__isnull=True).update(category="other")


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0012_expensecategory_expense_category_new'),
    ]

    operations = [
        migrations.RunPython(seed_and_convert, restore_slugs),
    ]
