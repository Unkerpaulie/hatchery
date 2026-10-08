"""Step 1 of 3: create ExpenseCategory and a temporary FK on Expense.

The old ``Expense.category`` CharField stays untouched for now. A temporary
nullable FK (``category_new``) sits beside it so migration 0013 can copy each
expense's string value across to a real category row. Migration 0014 then drops
the CharField and renames the FK into place.

Kept as three separate migrations on purpose: PostgreSQL refuses to alter a
table in the same transaction that already modified its rows ("pending trigger
events"), so schema and data changes must not share a migration.
"""

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0011_alter_expense_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpenseCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL, verbose_name='Last updated by')),
            ],
            options={
                'verbose_name_plural': 'expense categories',
                'ordering': [django.db.models.functions.text.Lower('name')],
            },
        ),
        migrations.AddConstraint(
            model_name='expensecategory',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='uniq_expense_category_name_ci', violation_error_message='A category with this name already exists.'),
        ),
        migrations.AddField(
            model_name='expense',
            name='category_new',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expenses', to='inventory.expensecategory'),
        ),
    ]
