"""Tests for inventory models: Batch lifecycle, age tracking, inventory math."""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Batch, Hatch, Supplier


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
