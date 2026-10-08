"""Tests for inventory models: Batch lifecycle, age tracking, inventory math."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from sales.models import Adjustment

from .forms import ExpenseCategoryForm, ExpenseForm
from .models import Batch, Expense, ExpenseCategory, Hatch, Supplier


def make_batch(**kwargs):
    """Factory: minimal valid egg batch. Override any field via kwargs."""
    defaults = dict(
        purchase_date=datetime.date(2024, 1, 1),
        purchased_as=Batch.PurchasedAs.EGGS,
        initial_quantity=100,
        total_cost="500.00",
    )
    defaults.update(kwargs)
    return Batch.objects.create(**defaults)


def make_chick_batch(**kwargs):
    """Factory: minimal valid chick batch."""
    defaults = dict(
        purchase_date=datetime.date(2024, 1, 10),
        purchased_as=Batch.PurchasedAs.CHICKS,
        initial_quantity=50,
        age_at_purchase=4,
        total_cost="300.00",
    )
    defaults.update(kwargs)
    return Batch.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Egg batch lifecycle
# ---------------------------------------------------------------------------

class EggBatchLifecycleTests(TestCase):

    def test_new_batch_has_new_status(self):
        batch = make_batch()
        self.assertEqual(batch.status, Batch.Status.NEW)

    def test_begin_incubation_transitions_to_incubating(self):
        batch = make_batch()
        batch.begin_incubation()
        self.assertEqual(batch.status, Batch.Status.INCUBATING)
        self.assertIsNotNone(batch.incubation_start_date)

    def test_begin_incubation_rejected_if_not_new(self):
        batch = make_batch()
        batch.begin_incubation()
        with self.assertRaises(ValidationError):
            batch.begin_incubation()

    def test_mark_hatched_sets_status_and_day_1_date(self):
        batch = make_batch()
        batch.begin_incubation()
        batch.mark_hatched()
        self.assertEqual(batch.status, Batch.Status.HATCHED)
        self.assertEqual(batch.day_1_date, timezone.localdate())

    def test_mark_hatched_rejected_if_not_incubating(self):
        batch = make_batch()
        with self.assertRaises(ValidationError):
            batch.mark_hatched()

    def test_begin_raising_from_hatched(self):
        batch = make_batch()
        batch.begin_incubation()
        batch.mark_hatched()
        batch.begin_raising()
        self.assertEqual(batch.status, Batch.Status.RAISING)

    def test_begin_raising_rejected_if_not_hatched(self):
        batch = make_batch()
        with self.assertRaises(ValidationError):
            batch.begin_raising()

    def test_mark_grown_from_raising(self):
        batch = make_batch()
        batch.begin_incubation()
        batch.mark_hatched()
        batch.begin_raising()
        batch.mark_grown()
        self.assertEqual(batch.status, Batch.Status.GROWN)

    def test_chick_batch_cannot_begin_incubation(self):
        batch = make_chick_batch()
        with self.assertRaises(ValidationError):
            batch.begin_incubation()

    def test_failed_count(self):
        batch = make_batch()
        batch.begin_incubation()
        Hatch.objects.create(batch=batch, date=datetime.date(2024, 1, 21), quantity=80)
        batch.mark_hatched()
        self.assertEqual(batch.failed_count, 20)  # 100 eggs − 80 hatched

    def test_success_rate(self):
        batch = make_batch()
        batch.begin_incubation()
        Hatch.objects.create(batch=batch, date=datetime.date(2024, 1, 21), quantity=90)
        batch.mark_hatched()
        self.assertAlmostEqual(batch.success_rate, 0.9)

    def test_egg_and_chick_losses_stay_separate_during_incubation(self):
        batch = make_batch(initial_quantity=1000)
        batch.begin_incubation()
        Adjustment.objects.create(
            batch=batch,
            quantity=150,
            adjustment_target=Adjustment.AdjustmentTarget.EGG,
            reason="Broken eggs",
        )
        batch = Batch.objects.with_inventory().get(pk=batch.pk)
        self.assertEqual(batch.eggs_remaining, 850)
        self.assertEqual(batch.chicks_available, 0)

        Hatch.objects.create(batch=batch, quantity=600)
        batch = Batch.objects.with_inventory().get(pk=batch.pk)
        self.assertEqual(batch.eggs_remaining, 250)
        self.assertEqual(batch.chicks_available, 600)

        Hatch.objects.create(batch=batch, quantity=100)
        Adjustment.objects.create(
            batch=batch,
            quantity=25,
            adjustment_target=Adjustment.AdjustmentTarget.EGG,
            reason="Broken eggs",
        )
        Adjustment.objects.create(
            batch=batch,
            quantity=25,
            adjustment_target=Adjustment.AdjustmentTarget.CHICK,
            reason="Chick mortality",
        )
        batch = Batch.objects.with_inventory().get(pk=batch.pk)
        self.assertEqual(batch.eggs_remaining, 125)
        self.assertEqual(batch.chicks_available, 675)

    def test_complete_incubation_only_records_unhatched_eggs_as_failed(self):
        batch = make_batch(initial_quantity=100)
        batch.begin_incubation()
        Hatch.objects.create(batch=batch, quantity=80)
        Adjustment.objects.create(
            batch=batch,
            quantity=10,
            adjustment_target=Adjustment.AdjustmentTarget.EGG,
            reason="Broken eggs",
        )

        batch.mark_hatched()

        failure = batch.adjustments.get(reason="Failed to hatch")
        self.assertEqual(failure.quantity, 10)
        self.assertEqual(failure.adjustment_target, Adjustment.AdjustmentTarget.EGG)
        batch = Batch.objects.with_inventory().get(pk=batch.pk)
        self.assertEqual(batch.chicks_available, 80)

    def test_hatch_validation_respects_prior_egg_losses(self):
        batch = make_batch(initial_quantity=100)
        batch.begin_incubation()
        Adjustment.objects.create(
            batch=batch,
            quantity=10,
            adjustment_target=Adjustment.AdjustmentTarget.EGG,
            reason="Broken eggs",
        )
        hatch = Hatch(batch=batch, quantity=91)

        with self.assertRaises(ValidationError):
            hatch.full_clean()


# ---------------------------------------------------------------------------
# Chick batch — purchase and auto-configuration
# ---------------------------------------------------------------------------

class ChickBatchTests(TestCase):

    def test_chick_batch_starts_hatched(self):
        batch = make_chick_batch()
        self.assertEqual(batch.status, Batch.Status.HATCHED)

    def test_chick_batch_day_1_date_back_calculated(self):
        batch = make_chick_batch(purchase_date=datetime.date(2024, 1, 10), age_at_purchase=4)
        self.assertEqual(batch.day_1_date, datetime.date(2024, 1, 6))

    def test_chick_batch_zero_age_at_purchase(self):
        batch = make_chick_batch(purchase_date=datetime.date(2024, 1, 10), age_at_purchase=0)
        self.assertEqual(batch.day_1_date, datetime.date(2024, 1, 10))

    def test_chick_batch_requires_age_at_purchase(self):
        batch = Batch(
            purchase_date=datetime.date(2024, 1, 10),
            purchased_as=Batch.PurchasedAs.CHICKS,
            initial_quantity=50,
            total_cost="300.00",
        )
        with self.assertRaises(ValidationError):
            batch.clean()

    def test_failed_count_zero_for_chick_batch(self):
        batch = make_chick_batch()
        self.assertEqual(batch.failed_count, 0)


# ---------------------------------------------------------------------------
# Age tracking
# ---------------------------------------------------------------------------

class AgeTrackingTests(TestCase):

    def test_age_zero_before_hatched(self):
        batch = make_batch()
        self.assertEqual(batch.current_age_days, 0)
        self.assertEqual(batch.current_age_display, "—")

    def test_age_display_after_hatching(self):
        batch = make_batch()
        batch.begin_incubation()
        batch.mark_hatched()
        # day_1_date = today, so age = 0 days = "0d"
        self.assertEqual(batch.current_age_days, 0)
        self.assertIn("d", batch.current_age_display)

    def test_chick_batch_age_from_purchase(self):
        # Bought 4-day-old chicks. day_1_date = purchase_date - 4.
        # Age on purchase day = 4 days.
        batch = make_chick_batch(
            purchase_date=timezone.localdate(),
            age_at_purchase=4,
        )
        self.assertEqual(batch.current_age_days, 4)

    def test_age_display_weeks_and_days(self):
        batch = make_chick_batch(
            purchase_date=timezone.localdate() - datetime.timedelta(days=3),
            age_at_purchase=10,
        )
        # day_1_date = today - 3 - 10 = today - 13; current_age = 13 days = 1w 6d
        self.assertEqual(batch.current_age_days, 13)
        self.assertEqual(batch.current_age_display, "1w 6d")


class BatchProfitTests(TestCase):

    def test_profit_includes_expenses_attributed_to_the_batch(self):
        batch = make_chick_batch(total_cost="300.00")
        Expense.objects.create(
            batch=batch,
            amount="25.50",
            category=ExpenseCategory.objects.create(name="Feed"),
            description="Starter feed",
        )
        batch.refresh_from_db()

        self.assertEqual(batch.expense_total, Decimal("25.50"))
        self.assertEqual(batch.profit, Decimal("-325.50"))


# ---------------------------------------------------------------------------
# Expense categories
# ---------------------------------------------------------------------------

class ExpenseCategoryModelTests(TestCase):

    def test_ordering_is_alphabetical_ignoring_case(self):
        for name in ["banana", "Cherry", "apple"]:
            ExpenseCategory.objects.create(name=name)
        names = list(ExpenseCategory.objects.values_list("name", flat=True))
        self.assertEqual(names, ["apple", "banana", "Cherry"])

    def test_other_has_no_special_position(self):
        for name in ["Phone", "Other", "Medicine", "Packaging"]:
            ExpenseCategory.objects.create(name=name)
        names = list(ExpenseCategory.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Medicine", "Other", "Packaging", "Phone"])

    def test_database_rejects_names_differing_only_by_case(self):
        ExpenseCategory.objects.create(name="Salaries")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpenseCategory.objects.create(name="salaries")

    def test_full_clean_rejects_names_differing_only_by_case(self):
        ExpenseCategory.objects.create(name="Salaries")
        with self.assertRaises(ValidationError):
            ExpenseCategory(name="SALARIES").full_clean()

    def test_deleting_a_category_keeps_its_expenses_uncategorized(self):
        category = ExpenseCategory.objects.create(name="Feed")
        expense = Expense.objects.create(amount="10.00", category=category, description="Starter")

        category.delete()

        expense.refresh_from_db()
        self.assertIsNone(expense.category)
        self.assertEqual(Expense.objects.count(), 1)

    def test_expense_validation_requires_a_category(self):
        expense = Expense(amount="10.00", description="No category")
        with self.assertRaises(ValidationError) as ctx:
            expense.full_clean()
        self.assertIn("category", ctx.exception.message_dict)

    def test_str_of_uncategorized_expense(self):
        expense = Expense.objects.create(amount="10.00", description="Orphan")
        self.assertIn("Uncategorized", str(expense))


class ExpenseCategoryFormTests(TestCase):

    def test_rejects_name_that_differs_only_by_case(self):
        ExpenseCategory.objects.create(name="Salaries")
        form = ExpenseCategoryForm({"name": "salaries"})
        self.assertFalse(form.is_valid())
        self.assertIn("already exists", form.errors["name"][0])

    def test_allows_changing_the_case_of_its_own_name(self):
        category = ExpenseCategory.objects.create(name="salaries")
        form = ExpenseCategoryForm({"name": "Salaries"}, instance=category)
        self.assertTrue(form.is_valid(), form.errors)

    def test_strips_surrounding_whitespace(self):
        form = ExpenseCategoryForm({"name": "  Feed  "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "Feed")

    def test_rejects_blank_name(self):
        self.assertFalse(ExpenseCategoryForm({"name": "   "}).is_valid())


class ExpenseFormCategoryTests(TestCase):
    """The expense form must keep requiring a category."""

    def _data(self, **extra):
        return {"date": "2026-01-15", "amount": "5.00", "description": "Test", **extra}

    def test_category_is_required(self):
        form = ExpenseForm(self._data())
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_valid_with_a_category(self):
        category = ExpenseCategory.objects.create(name="Feed")
        form = ExpenseForm(self._data(category=category.pk))
        self.assertTrue(form.is_valid(), form.errors)

    def test_category_choices_are_alphabetical(self):
        for name in ["banana", "Cherry", "apple"]:
            ExpenseCategory.objects.create(name=name)
        labels = [label for value, label in ExpenseForm().fields["category"].choices if value]
        self.assertEqual(labels, ["apple", "banana", "Cherry"])


# Production settings redirect plain-HTTP requests to https, which would turn
# every test-client request into a 301 when this suite runs under prod.py.
@override_settings(SECURE_SSL_REDIRECT=False)
class ExpenseCategoryViewTests(TestCase):
    """POST-only endpoints behind the Settings page."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("tester", password="pw")

    def setUp(self):
        self.client.force_login(self.user)

    def messages_for(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def post(self, name, url_name="expense_category_create", **url_kwargs):
        return self.client.post(
            reverse(f"inventory:{url_name}", kwargs=url_kwargs), {"name": name}
        )

    def assert_back_on_settings(self, response):
        self.assertRedirects(response, reverse("core:settings"), fetch_redirect_response=False)

    def test_create_adds_category_and_stamps_creator(self):
        response = self.post("Feed")
        self.assert_back_on_settings(response)
        category = ExpenseCategory.objects.get()
        self.assertEqual(category.name, "Feed")
        self.assertEqual(category.created_by, self.user)
        self.assertIn("added", self.messages_for(response)[0])

    def test_create_rejects_duplicate_ignoring_case(self):
        ExpenseCategory.objects.create(name="Salaries")
        response = self.post("salaries")
        self.assert_back_on_settings(response)
        self.assertEqual(ExpenseCategory.objects.count(), 1)
        self.assertIn("already exists", self.messages_for(response)[0])

    def test_create_rejects_blank_name(self):
        response = self.post("   ")
        self.assert_back_on_settings(response)
        self.assertEqual(ExpenseCategory.objects.count(), 0)
        self.assertIn("not saved", self.messages_for(response)[0])

    def test_update_renames_category_and_stamps_editor(self):
        category = ExpenseCategory.objects.create(name="Fead")
        response = self.post("Feed", "expense_category_update", pk=category.pk)
        self.assert_back_on_settings(response)
        category.refresh_from_db()
        self.assertEqual(category.name, "Feed")
        self.assertEqual(category.updated_by, self.user)

    def test_update_rejects_another_categorys_name(self):
        ExpenseCategory.objects.create(name="Feed")
        other = ExpenseCategory.objects.create(name="Medicine")
        response = self.post("FEED", "expense_category_update", pk=other.pk)
        self.assert_back_on_settings(response)
        other.refresh_from_db()
        self.assertEqual(other.name, "Medicine")
        self.assertIn("already exists", self.messages_for(response)[0])

    def test_update_may_change_case_of_own_name(self):
        category = ExpenseCategory.objects.create(name="salaries")
        self.post("Salaries", "expense_category_update", pk=category.pk)
        category.refresh_from_db()
        self.assertEqual(category.name, "Salaries")

    def test_delete_keeps_expenses_and_reports_how_many_were_affected(self):
        category = ExpenseCategory.objects.create(name="Feed")
        for i in range(2):
            Expense.objects.create(amount="5.00", category=category, description=f"e{i}")

        response = self.client.post(
            reverse("inventory:expense_category_delete", kwargs={"pk": category.pk})
        )

        self.assert_back_on_settings(response)
        self.assertFalse(ExpenseCategory.objects.exists())
        self.assertEqual(Expense.objects.filter(category__isnull=True).count(), 2)
        self.assertIn("2 expenses are now uncategorized", self.messages_for(response)[0])

    def test_delete_message_is_singular_for_one_expense(self):
        category = ExpenseCategory.objects.create(name="Feed")
        Expense.objects.create(amount="5.00", category=category, description="only")
        response = self.client.post(
            reverse("inventory:expense_category_delete", kwargs={"pk": category.pk})
        )
        self.assertIn("1 expense is now uncategorized", self.messages_for(response)[0])

    def test_delete_of_unused_category_mentions_no_expenses(self):
        category = ExpenseCategory.objects.create(name="Unused")
        response = self.client.post(
            reverse("inventory:expense_category_delete", kwargs={"pk": category.pk})
        )
        self.assertNotIn("uncategorized", self.messages_for(response)[0])

    def test_anonymous_users_cannot_modify_categories(self):
        self.client.logout()
        response = self.post("Sneaky")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)
        self.assertFalse(ExpenseCategory.objects.exists())

    def test_endpoints_do_not_accept_get(self):
        response = self.client.get(reverse("inventory:expense_category_create"))
        self.assertEqual(response.status_code, 405)


@override_settings(SECURE_SSL_REDIRECT=False)
class UncategorizedExpenseDisplayTests(TestCase):
    """Expenses orphaned by a category deletion still render everywhere."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("tester", password="pw"))

    def test_expense_list_shows_category_name_or_uncategorized(self):
        feed = ExpenseCategory.objects.create(name="Feed")
        Expense.objects.create(amount="5.00", category=feed, description="categorized one")
        Expense.objects.create(amount="6.00", description="orphaned one")

        response = self.client.get(reverse("inventory:expense_list"))

        self.assertContains(response, ">Feed</td>")
        self.assertContains(response, "Uncategorized")

    def test_batch_detail_and_expense_delete_pages_render_uncategorized(self):
        batch = make_chick_batch()
        expense = Expense.objects.create(batch=batch, amount="6.00", description="orphaned")

        detail = self.client.get(reverse("inventory:batch_detail", kwargs={"pk": batch.pk}))
        confirm = self.client.get(reverse("inventory:expense_delete", kwargs={"pk": expense.pk}))

        self.assertContains(detail, "Uncategorized")
        self.assertContains(confirm, "Uncategorized")


class ExpenseCategoryMigrationTests(TransactionTestCase):
    """Data migration 0013: legacy category slugs become real category rows.

    Rolls the inventory app back to its pre-feature state (0011), inserts
    expenses the way the old code stored them (a slug in a CharField), then
    migrates forward and checks what the client would see.
    """

    before = [("inventory", "0011_alter_expense_category")]
    after = [("inventory", "0014_remove_expense_category_rename_category_new")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        self.old_apps = executor.loader.project_state(self.before).apps

    def tearDown(self):
        # Leave the test database fully migrated for whatever runs next.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        return executor.loader.project_state(self.after).apps

    def make_old_expense(self, slug, description="x"):
        return self.old_apps.get_model("inventory", "Expense").objects.create(
            amount=Decimal("10.00"), category=slug, description=description
        )

    def test_existing_install_gets_all_original_categories_and_links(self):
        self.make_old_expense("feed", "bag of feed")
        self.make_old_expense("customs_excise", "duty")

        new_apps = self.migrate_forward()
        Category = new_apps.get_model("inventory", "ExpenseCategory")
        Expense = new_apps.get_model("inventory", "Expense")

        self.assertEqual(
            set(Category.objects.values_list("name", flat=True)),
            {
                "Cleaning", "Customs & Excise", "Electricity", "Equipment", "Feed",
                "Labor", "Maintenance", "Medicine", "Packaging", "Phone",
                "Service Charges", "Supplies", "Transport", "Other",
            },
        )
        self.assertEqual(Expense.objects.get(description="bag of feed").category.name, "Feed")
        self.assertEqual(Expense.objects.get(description="duty").category.name, "Customs & Excise")

    def test_unknown_legacy_slug_still_gets_a_category(self):
        self.make_old_expense("old_slug_value", "legacy row")

        new_apps = self.migrate_forward()
        Expense = new_apps.get_model("inventory", "Expense")

        self.assertEqual(Expense.objects.get(description="legacy row").category.name, "Old Slug Value")

    def test_fresh_database_is_not_seeded(self):
        new_apps = self.migrate_forward()
        self.assertEqual(new_apps.get_model("inventory", "ExpenseCategory").objects.count(), 0)

    def test_reverse_restores_slugs_with_custom_categories_collapsing_to_other(self):
        self.make_old_expense("feed", "bag of feed")
        new_apps = self.migrate_forward()
        Category = new_apps.get_model("inventory", "ExpenseCategory")
        Expense = new_apps.get_model("inventory", "Expense")
        Expense.objects.create(
            amount=Decimal("3.00"), description="custom", category=Category.objects.create(name="Salaries")
        )
        Expense.objects.create(amount=Decimal("4.00"), description="orphan")

        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps.get_model("inventory", "Expense")

        self.assertEqual(old.objects.get(description="bag of feed").category, "feed")
        self.assertEqual(old.objects.get(description="custom").category, "other")
        self.assertEqual(old.objects.get(description="orphan").category, "other")
