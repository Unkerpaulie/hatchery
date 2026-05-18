"""Sales domain models: Customer, Sale (header), SaleLine, Adjustment.

A Sale groups one or more SaleLines, each tied to a specific source Batch
(rules.md \u00a77 \u2014 business logic lives on the models). Inventory invariants
(quantity must not exceed available chicks) are enforced in clean()
methods so they hold whether records come in via forms, admin, or shell.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Sum
from django.utils import timezone

from core.models import Party


class Customer(Party):
    """End buyer of chicks. Per project rules, customer records are never
    deleted from the UI; ``Sale.customer`` uses ``PROTECT`` so accidental
    deletion through the ORM or admin is also blocked.
    """

    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Sale(models.Model):
    """A sale event for a single customer on a single date. Composed of one
    or more SaleLines so chicks from multiple batches can be sold together.
    """

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.pk} \u2014 {self.customer} ({self.date})"

    @property
    def total_quantity(self) -> int:
        return self.lines.aggregate(s=Sum("quantity"))["s"] or 0

    @property
    def total_revenue(self) -> Decimal:
        agg = self.lines.aggregate(s=Sum(F("quantity") * F("unit_price")))["s"]
        return agg or Decimal("0")


class SaleLine(models.Model):
    """One line in a sale: a quantity drawn from a specific batch at a
    specific unit price. ``clean()`` guarantees the line never overdraws
    the batch's available chicks (accounting for the line's own prior
    contribution when editing).
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, related_name="sale_lines"
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} \u00d7 batch #{self.batch_id} @ {self.unit_price}"

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price

    def clean(self):
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if self.unit_price is None or self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})
        if self.batch_id is None:
            return

        # Available = current available + any quantity this line already
        # contributes (so editing a saved line uses the right ceiling).
        prior_quantity = 0
        if self.pk:
            prior_quantity = SaleLine.objects.filter(pk=self.pk).values_list(
                "quantity", flat=True
            ).first() or 0
        ceiling = self.batch.chicks_available + prior_quantity
        if self.quantity > ceiling:
            raise ValidationError({
                "quantity": (
                    f"Only {ceiling} chick(s) available in batch #{self.batch_id}."
                ),
            })


class Adjustment(models.Model):
    """Non-sale removal from inventory (personal use, gifts, mortality, etc.).
    Created from the Sales section per the PRD clarification.
    """

    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, related_name="adjustments"
    )
    date = models.DateField(default=timezone.localdate)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Adjustment {self.quantity} from batch #{self.batch_id} ({self.reason})"

    def clean(self):
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if not self.reason:
            raise ValidationError({"reason": "A reason is required."})
        if self.batch_id is None:
            return

        prior_quantity = 0
        if self.pk:
            prior_quantity = Adjustment.objects.filter(pk=self.pk).values_list(
                "quantity", flat=True
            ).first() or 0
        ceiling = self.batch.chicks_available + prior_quantity
        if self.quantity > ceiling:
            raise ValidationError({
                "quantity": (
                    f"Only {ceiling} chick(s) available in batch #{self.batch_id}."
                ),
            })
