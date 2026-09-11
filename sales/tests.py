"""Tests for cash-revenue allocation across chick-sale batches."""

import datetime
from decimal import Decimal

from django.test import TestCase

from inventory.models import Batch

from .models import Customer, Sale, SaleLine


class CashRevenueTests(TestCase):

    def make_batch(self):
        return Batch.objects.create(
            purchase_date=datetime.date(2026, 1, 1),
            purchased_as=Batch.PurchasedAs.CHICKS,
            age_at_purchase=0,
            initial_quantity=100,
            total_cost=Decimal("100.00"),
        )

    def test_cash_payment_is_prorated_between_batches(self):
        first_batch = self.make_batch()
        second_batch = self.make_batch()
        sale = Sale.objects.create(
            customer=Customer.objects.create(name="Customer"),
            status=Sale.Status.FINALIZED,
            payment_received=Decimal("50.00"),
        )
        SaleLine.objects.create(sale=sale, batch=first_batch, quantity=4, unit_price=Decimal("10.00"))
        SaleLine.objects.create(sale=sale, batch=second_batch, quantity=6, unit_price=Decimal("10.00"))

        batches = {
            batch.pk: batch
            for batch in Batch.objects.with_inventory().filter(pk__in=[first_batch.pk, second_batch.pk])
        }

        self.assertEqual(batches[first_batch.pk].revenue, Decimal("20.00"))
        self.assertEqual(batches[second_batch.pk].revenue, Decimal("30.00"))
