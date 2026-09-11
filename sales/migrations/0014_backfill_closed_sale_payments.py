"""Backfill cash received for historical invoices already marked closed."""

from django.db import migrations
from django.db.models import F, Sum


def backfill_closed_sale_payments(apps, schema_editor):
    """A closed historical sale represents a fully paid invoice.

    Payment tracking was introduced after existing invoices had already been
    closed, leaving payment_received null.  Populate only those unambiguous
    records; finalized sales retain their recorded partial-payment state.
    """
    Sale = apps.get_model("sales", "Sale")
    SaleLine = apps.get_model("sales", "SaleLine")

    for sale in Sale.objects.filter(status="closed", payment_received__isnull=True).iterator():
        total = SaleLine.objects.filter(sale_id=sale.pk).aggregate(
            total=Sum(F("quantity") * F("unit_price"))
        )["total"]
        Sale.objects.filter(pk=sale.pk).update(payment_received=total or 0)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0013_adjustment_target"),
    ]

    operations = [
        migrations.RunPython(backfill_closed_sale_payments, migrations.RunPython.noop),
    ]
