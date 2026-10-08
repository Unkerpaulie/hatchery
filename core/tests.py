"""Tests for core views: the Settings page."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from inventory.models import Expense, ExpenseCategory


# Production settings redirect plain-HTTP requests to https, which would turn
# every test-client request into a 301 when this suite runs under prod.py.
@override_settings(SECURE_SSL_REDIRECT=False)
class SettingsViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("tester", password="pw")

    def test_requires_login(self):
        url = reverse("core:settings")
        response = self.client.get(url)
        self.assertRedirects(
            response, f"{reverse('core:login')}?next={url}", fetch_redirect_response=False
        )

    def test_lists_categories_alphabetically_with_expense_counts(self):
        # Created deliberately out of order (and mixed case) so the test can
        # only pass if the view really sorts, not if rows happen to come back
        # in insertion order.
        zebra = ExpenseCategory.objects.create(name="Zebra")
        ExpenseCategory.objects.create(name="apple")
        mango = ExpenseCategory.objects.create(name="Mango")
        for i in range(2):
            Expense.objects.create(amount="5.00", category=mango, description=f"e{i}")
        Expense.objects.create(amount="5.00", category=zebra, description="z")

        self.client.force_login(self.user)
        response = self.client.get(reverse("core:settings"))

        self.assertEqual(response.status_code, 200)
        categories = list(response.context["categories"])
        self.assertEqual([c.name for c in categories], ["apple", "Mango", "Zebra"])
        self.assertEqual([c.expense_count for c in categories], [0, 2, 1])

    def test_page_wires_up_add_edit_and_delete_endpoints(self):
        category = ExpenseCategory.objects.create(name="Feed")
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:settings"))

        self.assertContains(response, "Manage Expense Categories")
        self.assertContains(response, reverse("inventory:expense_category_create"))
        self.assertContains(response, reverse("inventory:expense_category_update", kwargs={"pk": category.pk}))
        self.assertContains(response, reverse("inventory:expense_category_delete", kwargs={"pk": category.pk}))

    def test_empty_state_message(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:settings"))
        self.assertContains(response, "No expense categories yet")

    def test_user_menu_links_to_settings(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, f'href="{reverse("core:settings")}"')
