from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0012_alter_adjustment_adjustment_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="adjustment",
            name="adjustment_target",
            field=models.CharField(
                blank=True,
                choices=[("egg", "Egg"), ("chick", "Chick")],
                default="",
                help_text="Egg or chick? Only required for INCUBATING batches.",
                max_length=5,
            ),
        ),
    ]
