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
from django.utils.functional import cached_property

from core.models import AuditedModel, Party


class Customer(Party, AuditedModel):
    """End buyer of chicks. Per project rules, customer records are never
    deleted from the UI; ``Sale.customer`` uses ``PROTECT`` so accidental
    deletion through the ORM or admin is also blocked.
    """

    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Sale(AuditedModel):
    """A sale event for a single customer on a single date. Composed of one
    or more SaleLines so chicks from multiple batches can be sold together.

    Status lifecycle: PENDING (draft) → CLOSED (inventory committed)
                                      → CANCELLED (no inventory effect).
    Only CLOSED sales deduct from chick inventory.
    """

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        FINALIZED = "finalized", "Finalized"
        CLOSED    = "closed",    "Closed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        CASH          = "cash",          "Cash"
        DEBIT_CARD    = "debit_card",    "Debit Card"
        CREDIT_CARD   = "credit_card",   "Credit Card"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        BANK_DEPOSIT  = "bank_deposit", "Bank Deposit"

    customer         = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    date             = models.DateField(default=timezone.localdate)
    notes            = models.TextField(blank=True)
    status           = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payment_method   = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        blank=True,
        default="",
        help_text="How the customer paid (recorded when the sale is finalized or closed).",
    )
    payment_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Amount actually collected. None while pending; set at finalization.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Sale #{self.pk} \u2014 {self.customer} ({self.date})"

    @cached_property
    def total_quantity(self) -> int:
        return self.lines.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def total_revenue(self) -> Decimal:
        agg = self.lines.aggregate(s=Sum(F("quantity") * F("unit_price")))["s"]
        return agg or Decimal("0")

    @cached_property
    def balance(self) -> Decimal:
        """Outstanding amount owed. Zero for fully-paid or pending sales.
        Never stored — always derived from total_revenue and payment_received.
        """
        if self.payment_received is None:
            return Decimal("0")
        return max(self.total_revenue - self.payment_received, Decimal("0"))


class SaleLine(AuditedModel):
    """One line in a sale: a quantity drawn from a specific batch at a
    specific unit price.

    Inventory ceiling validation is only enforced for CLOSED sales (the
    point at which inventory is actually committed). While a sale is PENDING
    the line is a draft and the ceiling is not checked here — it is
    validated instead by SaleCloseView before the status transition.
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.CASCADE, related_name="sale_lines"
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

        # Only enforce the inventory ceiling once the sale is FINALIZED or CLOSED.
        # For PENDING sales the line is a draft; SaleFinalizeView validates
        # the ceiling for all lines before committing the status change.
        if self.sale_id:
            sale_status = Sale.objects.filter(pk=self.sale_id).values_list(
                "status", flat=True
            ).first()
            if sale_status not in (Sale.Status.FINALIZED, Sale.Status.CLOSED):
                return

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


class MeatSale(AuditedModel):
    """A daily meat-chicken sales session: one batch, one price, N individual birds.

    Each bird sold is recorded as a MeatSaleLine with its weight. The session
    is created atomically — lines are bulk-inserted immediately after the
    MeatSale row is saved in MeatSaleCreateView.

    Unlike chick sales there are no customers, invoices, or status lifecycle.
    A MeatSale is committed the moment it is saved.
    """

    batch       = models.ForeignKey(
        "inventory.Batch", on_delete=models.PROTECT, related_name="meat_sales"
    )
    date        = models.DateField(default=timezone.localdate)
    price_per_lb = models.DecimalField(max_digits=8, decimal_places=2)
    notes       = models.TextField(blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Meat Sale #{self.pk} — Batch #{self.batch_id} ({self.date})"

    @cached_property
    def chicken_count(self) -> int:
        """Number of individual birds sold. Iterates in Python so it benefits
        from prefetch_related('lines') when called on a queryset result."""
        return len(self.lines.all())

    @cached_property
    def total_weight(self) -> Decimal:
        """Sum of all bird weights. Iterates in Python so it benefits from
        prefetch_related('lines') when called on a queryset result."""
        return sum((line.weight_lb for line in self.lines.all()), Decimal("0"))

    @cached_property
    def total_revenue(self) -> Decimal:
        return self.total_weight * self.price_per_lb


class MeatSaleLine(models.Model):
    """One bird in a MeatSale: its weight in pounds.

    Lines are always created in bulk alongside their parent MeatSale and are
    never edited individually. No audit fields — attribution lives on the
    parent MeatSale record.
    """

    meat_sale = models.ForeignKey(MeatSale, on_delete=models.CASCADE, related_name="lines")
    weight_lb = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.weight_lb} lb (MeatSale #{self.meat_sale_id})"

    @property
    def sale_price(self):
        """Sale price for this individual bird (weight × price_per_lb)."""
        return self.weight_lb * self.meat_sale.price_per_lb


class Adjustment(AuditedModel):
    """Non-sale removal from inventory (death, donation, personal use, etc.).
    Created from the Sales section per the PRD clarification.
    """

    class AdjustmentType(models.TextChoices):
        DEATH        = "death",        "Death"
        DONATION     = "donation",     "Donation"
        PERSONAL_USE = "personal_use", "Personal Use"
        DAMAGED      = "damaged",      "Damaged"

    batch = models.ForeignKey(
        "inventory.Batch", on_delete=models.CASCADE, related_name="adjustments"
    )
    date = models.DateField(default=timezone.localdate)
    quantity = models.PositiveIntegerField()
    adjustment_type = models.CharField(
        max_length=20,
        choices=AdjustmentType.choices,
        default=AdjustmentType.DEATH,
        help_text="Category of inventory adjustment.",
    )
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
        ceiling = self.batch.adjustment_ceiling + prior_quantity
        if self.quantity > ceiling:
            raise ValidationError({
                "quantity": (
                    f"Only {ceiling} available to adjust in batch #{self.batch_id}."
                ),
            })
