"""Inventory domain models: Supplier, Batch, Hatch.

The Batch model encapsulates the egg-to-chick lifecycle and the running
chick-inventory math. State transitions (begin incubation, mark complete)
live on the model itself per rules.md \u00a77.
"""

from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import DecimalField, F, IntegerField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.functional import cached_property

from core.models import Party


class Supplier(Party):
    """Egg supplier. ``business_name`` is the primary identifier; the
    contact person is captured separately because Party.name does not apply.
    """

    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["business_name"]

    def __str__(self):
        return self.business_name


class BatchQuerySet(models.QuerySet):
    """Querysets returning batches with inventory totals attached.

    Uses correlated subqueries (rather than ``annotate(Sum())`` on multiple
    reverse relations) to avoid the classic Django join-multiplication
    bug when summing across more than one related manager.
    """

    def with_inventory(self):
        SaleLine = apps.get_model("sales", "SaleLine")
        Adjustment = apps.get_model("sales", "Adjustment")

        def _sum_sq(model, field="quantity"):
            return (
                model.objects.filter(batch=OuterRef("pk"))
                .values("batch")
                .annotate(s=Sum(field))
                .values("s")
            )

        revenue_sq = (
            SaleLine.objects.filter(batch=OuterRef("pk"))
            .values("batch")
            .annotate(s=Sum(F("quantity") * F("unit_price")))
            .values("s")
        )

        zero_int = models.Value(0, output_field=IntegerField())
        zero_money = models.Value(
            Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2)
        )

        return self.annotate(
            hatched_count=Coalesce(Subquery(_sum_sq(Hatch), output_field=IntegerField()), zero_int),
            sold_count=Coalesce(Subquery(_sum_sq(SaleLine), output_field=IntegerField()), zero_int),
            adjusted_count=Coalesce(Subquery(_sum_sq(Adjustment), output_field=IntegerField()), zero_int),
            revenue=Coalesce(
                Subquery(revenue_sq, output_field=DecimalField(max_digits=12, decimal_places=2)),
                zero_money,
            ),
        ).annotate(
            chicks_available=F("hatched_count") - F("sold_count") - F("adjusted_count"),
        )


class Batch(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        INCUBATING = "incubating", "Incubating"
        DONE = "done", "Done"

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
    )
    purchase_date = models.DateField()
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(help_text="Number of eggs in this batch.")
    incubation_start_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BatchQuerySet.as_manager()

    class Meta:
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"Batch #{self.pk} ({self.get_status_display()})"

    # ---- state transitions -------------------------------------------------

    def begin_incubation(self, when=None):
        """Move the batch from READY to INCUBATING and record the start date."""
        if self.status != self.Status.READY:
            raise ValidationError("Only batches in 'ready' status can begin incubation.")
        self.incubation_start_date = when or timezone.localdate()
        self.status = self.Status.INCUBATING
        self.save(update_fields=["incubation_start_date", "status", "updated_at"])

    def complete(self):
        """Mark the batch as DONE. Failed count is implicit (quantity \u2212 hatched)."""
        if self.status != self.Status.INCUBATING:
            raise ValidationError("Only batches in 'incubating' status can be completed.")
        self.status = self.Status.DONE
        self.save(update_fields=["status", "updated_at"])

    # ---- single-instance computed properties ---------------------------------
    #
    # These are declared as ``cached_property`` so they play nicely with
    # BatchQuerySet.with_inventory(): when Django sets the annotation value via
    # setattr(), it writes directly to instance.__dict__ (non-data descriptor),
    # and subsequent attribute access returns that value without hitting the DB.
    # On un-annotated instances the descriptor computes from the DB on first
    # access and caches in __dict__ for the remainder of the request.

    @cached_property
    def hatched_count(self) -> int:
        return self.hatches.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def sold_count(self) -> int:
        return self.sale_lines.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def adjusted_count(self) -> int:
        return self.adjustments.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def chicks_available(self) -> int:
        return self.hatched_count - self.sold_count - self.adjusted_count

    @cached_property
    def revenue(self) -> Decimal:
        agg = self.sale_lines.aggregate(s=Sum(F("quantity") * F("unit_price")))["s"]
        return agg or Decimal("0")

    @property
    def failed_count(self) -> int:
        """Eggs that never hatched. Only meaningful once status is DONE."""
        return max(self.quantity - self.hatched_count, 0)

    @property
    def success_rate(self) -> float:
        if not self.quantity:
            return 0.0
        return self.hatched_count / self.quantity

    @property
    def profit(self) -> Decimal:
        return self.revenue - self.total_cost


class Hatch(models.Model):
    """A daily hatch record on a batch. Quantities aggregate per day in the UI."""

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="hatches")
    date = models.DateField(default=timezone.localdate)
    quantity = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Hatch {self.quantity} on {self.date} (batch #{self.batch_id})"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Hatch quantity must be greater than zero."})
        if self.batch_id and self.batch.status != Batch.Status.INCUBATING:
            raise ValidationError(
                "Hatch records can only be added while the batch is incubating."
            )


class Expense(models.Model):
    """An operating expense not tied to a specific batch (feed, electricity,
    supplies, labour, etc.). Batch egg-purchase costs are captured on
    ``Batch.total_cost``; this model covers all other running costs so the
    dashboard can show a meaningful total-cost figure.
    """

    class Category(models.TextChoices):
        FEED        = "feed",        "Feed"
        ELECTRICITY = "electricity", "Electricity"
        SUPPLIES    = "supplies",    "Supplies"
        LABOR       = "labor",       "Labor"
        OTHER       = "other",       "Other"

    date        = models.DateField(default=timezone.localdate)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    category    = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=200)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_category_display()} — ${self.amount} ({self.date})"

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
