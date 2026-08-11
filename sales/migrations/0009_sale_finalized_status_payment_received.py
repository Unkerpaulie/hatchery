from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0008_sale_payment_method"),
    ]

    operations = [
        # Extend the status field to include the new "finalized" choice.
        # Existing rows are unaffected — their stored values remain valid.
        migrations.AlterField(
            model_name="sale",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending",   "Pending"),
                    ("finalized", "Finalized"),
                    ("closed",    "Closed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        # New nullable decimal: None = not yet collected (PENDING);
        # a value = amount actually received (FINALIZED or CLOSED).
        migrations.AddField(
            model_name="sale",
            name="payment_received",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                help_text="Amount actually collected. None while pending; set at finalization.",
                max_digits=10,
                null=True,
            ),
        ),
    ]
