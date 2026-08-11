from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0007_adjustment_type_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cash",          "Cash"),
                    ("debit_card",    "Debit Card"),
                    ("credit_card",   "Credit Card"),
                    ("bank_transfer", "Bank Transfer"),
                ],
                default="",
                help_text="How the customer paid (recorded when the sale is closed).",
                max_length=16,
            ),
        ),
    ]
