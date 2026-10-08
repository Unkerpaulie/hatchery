"""Step 3 of 3: drop the old CharField and rename the FK into its place.

After this migration ``Expense.category`` is a ForeignKey to ExpenseCategory
(database column ``category_id``) holding the data converted in 0013.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0013_seed_expense_categories'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='expense',
            name='category',
        ),
        migrations.RenameField(
            model_name='expense',
            old_name='category_new',
            new_name='category',
        ),
    ]
