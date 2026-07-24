"""Inventory domain models: Supplier, Batch, Hatch.

The Batch model encapsulates the egg-to-chick lifecycle and the running
chick-inventory math. State transitions (begin incubation, mark complete)
live on the model itself per rules.md \u00a77.
"""

from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Count, DecimalField, F, IntegerField, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.functional import cached_property

from core.models import AuditedModel, Party


class Supplier(Party, AuditedModel):
    """Egg supplier. ``business_name`` is the primary identifier; the
    contact person is captured separately because Party.name does not apply.
    """

    business_name = models.CharField(max_length=200)
    contact_name  = models.CharField(max_length=200, blank=True)
    website       = models.URLField(blank=True)

    class Meta:
        ordering = ["business_name"]

    def __str__(self):
        return self.business_name


class BatchQuerySet(models.QuerySet):
    """Querysets returning batches with inventory totals attached.

    Uses correlated subqueries (rather than ``annotate(Sum())`` on multiple
    reverse relations) to avoid the classic Django join-multiplication
    bug when summing across more than one related manager.

    Annotation chain (order matters — later annotations reference earlier ones):
      1. hatched_count, sold_count, adjusted_count, revenue  (raw subquery totals)
      2. chick_pool   — effective chick supply depending on purchased_as
      3. chicks_available — pool minus deductions; 0 when status is not HATCHED
    """

    def with_inventory(self):
        SaleLine    = apps.get_model("sales", "SaleLine")
        Adjustment  = apps.get_model("sales", "Adjustment")
        MeatSaleLine = apps.get_model("sales", "MeatSaleLine")

        def _sum_sq(model, field="quantity", extra_filter=None):
            qs = model.objects.filter(batch=OuterRef("pk"))
            if extra_filter:
                qs = qs.filter(**extra_filter)
            return qs.values("batch").annotate(s=Sum(field)).values("s")

        # Only CLOSED sales commit chick inventory.
        closed_filter = {"sale__status": "closed"}

        revenue_sq = (
            SaleLine.objects.filter(batch=OuterRef("pk"), sale__status="closed")
            .values("batch")
            .annotate(s=Sum(F("quantity") * F("unit_price")))
            .values("s")
        )

        # Each MeatSaleLine row = one chicken sold. Count rows per batch via
        # the MeatSale FK (MeatSaleLine → MeatSale → Batch).
        meat_sold_sq = (
            MeatSaleLine.objects.filter(meat_sale__batch=OuterRef("pk"))
            .values("meat_sale__batch_id")
            .annotate(s=Count("pk"))
            .values("s")
        )

        zero_int   = Value(0, output_field=IntegerField())
        zero_money = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2))

        return (
            self.annotate(
                hatched_count=Coalesce(Subquery(_sum_sq(Hatch), output_field=IntegerField()), zero_int),
                sold_count=Coalesce(Subquery(_sum_sq(SaleLine, extra_filter=closed_filter), output_field=IntegerField()), zero_int),
                adjusted_count=Coalesce(Subquery(_sum_sq(Adjustment), output_field=IntegerField()), zero_int),
                meat_sold_count=Coalesce(Subquery(meat_sold_sq, output_field=IntegerField()), zero_int),
                revenue=Coalesce(
                    Subquery(revenue_sq, output_field=DecimalField(max_digits=12, decimal_places=2)),
                    zero_money,
                ),
            )
            .annotate(
                # chick_pool: total chicks produced/purchased for this batch.
                # Egg batches: use the sum of actual hatch records (some eggs fail).
                # Chick batches: use initial_quantity (all chicks arrived on day 1).
                chick_pool=Case(
                    When(purchased_as="eggs",   then=F("hatched_count")),
                    When(purchased_as="chicks", then=F("initial_quantity")),
                    default=zero_int,
                    output_field=IntegerField(),
                ),
            )
            .annotate(
                # 3rd pass: eggs_remaining and birds_count.
                # eggs_remaining: unhatched eggs during INCUBATING; zero otherwise.
                eggs_remaining=Case(
                    When(status="incubating", then=F("initial_quantity") - F("hatched_count")),
                    default=zero_int,
                    output_field=IntegerField(),
                ),
                # birds_count: total living inventory in the batch at any moment.
                # Uniform formula across all lifecycle phases:
                #   initial_quantity − all_adjustments − chick_sales − meat_sales
                # For egg batches the failed-egg Adjustment auto-created by mark_hatched()
                # is what makes this formula correct post-HATCHED (see Batch.mark_hatched).
                birds_count=F("initial_quantity") - F("adjusted_count") - F("sold_count") - F("meat_sold_count"),
            )
            .annotate(
                # 4th pass: sale-availability and adjustment ceiling.
                # Both reference birds_count and eggs_remaining from the 3rd pass.
                #
                # chicks_available: subset of birds_count available for chick sale.
                #   INCUBATING → birds_count − eggs_remaining = only the hatched portion.
                #   HATCHED    → birds_count − 0 = birds_count (all live birds are chicks).
                #   RAISING/GROWN/NEW → 0 (not on the chick market).
                chicks_available=Case(
                    When(
                        status__in=["hatched", "incubating"],
                        then=F("birds_count") - F("eggs_remaining"),
                    ),
                    default=zero_int,
                    output_field=IntegerField(),
                ),
                # adjustment_ceiling: maximum adjustable quantity.
                #   = chicks_available for INCUBATING/HATCHED (adjustments affect live birds,
                #     not unhatched eggs — those are captured by the mark_hatched auto-adjustment).
                #   = birds_count for NEW/RAISING/GROWN (eggs_remaining is 0 in those phases).
                adjustment_ceiling=F("birds_count") - F("eggs_remaining"),
            )
        )


class Batch(AuditedModel):
    """A purchase batch of eggs or chicks, tracked from acquisition through sale.

    The lifecycle differs by purchase type:
      eggs   → NEW → INCUBATING → HATCHED → RAISING → GROWN
      chicks → HATCHED (immediately) → RAISING → GROWN

    ``purchased_as`` is immutable after creation — it preserves the historical
    origin and governs which pool calculation ``with_inventory()`` uses.
    ``status`` reflects the current phase. ``day_1_date`` is the anchor for
    age tracking and is set once: on HATCHED transition for egg batches, or
    back-calculated from purchase info for chick batches.
    """

    class Status(models.TextChoices):
        NEW        = "new",        "New"
        INCUBATING = "incubating", "Incubating"
        HATCHED    = "hatched",    "Hatched"
        RAISING    = "raising",    "Raising"
        GROWN      = "grown",      "Grown"

    class PurchasedAs(models.TextChoices):
        EGGS   = "eggs",   "Eggs"
        CHICKS = "chicks", "Chicks"

    # ---- immutable purchase record -----------------------------------------
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
    )
    purchase_date     = models.DateField()
    purchased_as      = models.CharField(
        max_length=6, choices=PurchasedAs.choices, default=PurchasedAs.EGGS,
        help_text="What was purchased: eggs for incubation, or chicks ready for sale.",
    )
    initial_quantity  = models.PositiveIntegerField(
        help_text="Number of eggs or chicks at the time of purchase. Does not change."
    )
    total_cost        = models.DecimalField(max_digits=10, decimal_places=2)
    age_at_purchase   = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Age of chicks in days at time of purchase. Required for chick batches.",
    )
    breed             = models.CharField(max_length=100, blank=True)

    # ---- mutable lifecycle fields ------------------------------------------
    status                = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    incubation_start_date = models.DateField(null=True, blank=True)
    day_1_date            = models.DateField(
        null=True, blank=True,
        help_text="The anchor date for age tracking (day 1). Set when the batch is "
                  "first HATCHED; back-calculated for purchased chick batches.",
    )
    age_end_date = models.DateField(
        null=True, blank=True,
        help_text="Date when aging stopped (set when batch is marked GROWN). "
                  "Age freezes at this point rather than continuing to increment.",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BatchQuerySet.as_manager()

    class Meta:
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"Batch #{self.pk} ({self.get_status_display()})"

    # ---- save override -----------------------------------------------------

    def clean(self):
        """Validate and auto-configure chick batches.

        For chick batches:
        - age_at_purchase is required.
        - status is forced to HATCHED here (before save) so that form validation
          doesn't see a NEW status that was never meant to persist.
        - day_1_date is back-calculated from purchase_date and age_at_purchase.
        """
        if self.purchased_as == self.PurchasedAs.CHICKS:
            if self.age_at_purchase is None:
                raise ValidationError(
                    {"age_at_purchase": "Age at purchase is required for chick batches."}
                )
            # Set status early so model-level guards don't fire on a transient default.
            if self.status in (self.Status.NEW, self.Status.INCUBATING):
                self.status = self.Status.HATCHED
            # Always recompute day_1_date so edits to age_at_purchase propagate.
            if self.purchase_date is not None:
                age = self.age_at_purchase or 0
                self.day_1_date = self.purchase_date - timedelta(days=age)

    def save(self, *args, **kwargs):
        """Ensure clean() side-effects are applied even on direct saves
        that bypass form validation (e.g. management commands, tests).
        """
        if self.purchased_as == self.PurchasedAs.CHICKS:
            if self.status in (self.Status.NEW, self.Status.INCUBATING):
                self.status = self.Status.HATCHED
            if self.purchase_date is not None:
                age = self.age_at_purchase or 0
                self.day_1_date = self.purchase_date - timedelta(days=age)
        super().save(*args, **kwargs)

    # ---- state transitions -------------------------------------------------

    def begin_incubation(self, when=None, updated_by=None):
        """NEW → INCUBATING. Records the start date. Egg batches only.

        ``updated_by`` should be ``request.user`` from the calling view.
        """
        if self.purchased_as != self.PurchasedAs.EGGS:
            raise ValidationError("Only egg batches can be incubated.")
        if self.status != self.Status.NEW:
            raise ValidationError("Only batches in 'new' status can begin incubation.")
        self.incubation_start_date = when or timezone.localdate()
        self.status = self.Status.INCUBATING
        self.updated_by = updated_by
        self.save(update_fields=["incubation_start_date", "status", "updated_at", "updated_by"])

    def mark_hatched(self, updated_by=None):
        """INCUBATING → HATCHED. Sets day_1_date to today — day 1 of chick age.

        Also auto-creates an Adjustment for any eggs that failed to hatch.  This
        makes birds_count continuous across the transition: every inventory reduction
        now flows through the adjustment system, including incubation failures, so
        loss reporting works uniformly across all batch types and lifecycle phases.

        ``updated_by`` should be ``request.user`` from the calling view.
        """
        if self.status != self.Status.INCUBATING:
            raise ValidationError("Only batches in 'incubating' status can be marked as hatched.")

        # Capture before the status change so failed_count is still computable.
        failed = self.initial_quantity - self.hatched_count

        self.status = self.Status.HATCHED
        self.day_1_date = timezone.localdate()
        self.updated_by = updated_by
        self.save(update_fields=["status", "day_1_date", "updated_at", "updated_by"])

        if failed > 0:
            # Lazy import avoids a circular-dependency between inventory and sales.
            from sales.models import Adjustment  # noqa: PLC0415
            Adjustment.objects.create(
                batch=self,
                date=timezone.localdate(),
                quantity=failed,
                reason="Failed to hatch",
                created_by=updated_by,
                updated_by=updated_by,
            )

    def begin_raising(self, updated_by=None):
        """HATCHED → RAISING. Commits all remaining chicks to growing for meat.

        Once raising begins the batch is no longer available for chick sale.
        ``updated_by`` should be ``request.user`` from the calling view.
        """
        if self.status != self.Status.HATCHED:
            raise ValidationError("Only batches in 'hatched' status can begin raising.")
        self.status = self.Status.RAISING
        self.updated_by = updated_by
        self.save(update_fields=["status", "updated_at", "updated_by"])

    def mark_grown(self, updated_by=None):
        """RAISING → GROWN. Chickens are now fully grown and ready for meat sale.

        Sets ``age_end_date`` to today so the batch's age freezes at this point
        rather than continuing to increment daily.

        ``updated_by`` should be ``request.user`` from the calling view.
        """
        if self.status != self.Status.RAISING:
            raise ValidationError("Only batches in 'raising' status can be marked as grown.")
        self.status = self.Status.GROWN
        self.age_end_date = timezone.localdate()
        self.updated_by = updated_by
        self.save(update_fields=["status", "age_end_date", "updated_at", "updated_by"])

    # ---- single-instance computed properties --------------------------------
    #
    # Declared as ``cached_property`` so they play nicely with
    # BatchQuerySet.with_inventory(): when Django sets the annotation value via
    # setattr(), it writes directly to instance.__dict__ (non-data descriptor),
    # bypassing the descriptor on subsequent access. On un-annotated instances
    # the descriptor computes from the DB on first access and caches the result.

    @cached_property
    def hatched_count(self) -> int:
        """Sum of all Hatch records. Meaningful for egg batches only."""
        return self.hatches.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def sold_count(self) -> int:
        return self.sale_lines.filter(sale__status="closed").aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def adjusted_count(self) -> int:
        return self.adjustments.aggregate(s=Sum("quantity"))["s"] or 0

    @cached_property
    def chick_pool(self) -> int:
        """Total chick supply for this batch (mirrors with_inventory annotation).

        Egg batches: actual hatched count (some eggs may fail).
        Chick batches: initial_quantity (all chicks arrived on purchase day).
        """
        if self.purchased_as == self.PurchasedAs.EGGS:
            return self.hatched_count
        return self.initial_quantity

    @cached_property
    def eggs_remaining(self) -> int:
        """Eggs still unhatched during INCUBATING phase. Zero for all other statuses."""
        if self.status != self.Status.INCUBATING:
            return 0
        return self.initial_quantity - self.hatched_count

    @cached_property
    def meat_sold_count(self) -> int:
        """Count of individual chickens sold as meat from this batch.

        Each MeatSaleLine row represents one bird. We traverse through MeatSale
        because MeatSaleLine has no direct FK to Batch.
        """
        from sales.models import MeatSaleLine  # lazy import — avoids circular dependency
        return MeatSaleLine.objects.filter(meat_sale__batch_id=self.pk).count()

    @cached_property
    def birds_count(self) -> int:
        """Total living inventory in the batch at any moment (mirrors with_inventory annotation).

        Uniform formula for every lifecycle phase:
            initial_quantity − all_adjustments − chick_sales − meat_sales

        For egg batches the failed-egg Adjustment auto-created by mark_hatched() is
        what makes this formula correct post-HATCHED; without it the result would
        be initial_quantity instead of hatched_count as the effective base.
        """
        return self.initial_quantity - self.adjusted_count - self.sold_count - self.meat_sold_count

    @cached_property
    def chicks_available(self) -> int:
        """Chicks available for sale: the subset of birds_count on the chick market.

        INCUBATING → birds_count − eggs_remaining (only the hatched portion).
        HATCHED    → birds_count (eggs_remaining is zero; all remaining birds are chicks).
        All other statuses → 0 (not on the chick market).
        """
        if self.status not in (self.Status.HATCHED, self.Status.INCUBATING):
            return 0
        return self.birds_count - self.eggs_remaining

    @cached_property
    def adjustment_ceiling(self) -> int:
        """Maximum adjustable quantity: birds_count minus any unhatched eggs.

        During INCUBATING, only live hatched chicks can be adjusted (unhatched egg
        failures are captured by the mark_hatched auto-adjustment, not individually).
        For all other phases eggs_remaining is 0, so this equals birds_count.
        """
        return self.birds_count - self.eggs_remaining

    @cached_property
    def revenue(self) -> Decimal:
        agg = self.sale_lines.filter(sale__status="closed").aggregate(
            s=Sum(F("quantity") * F("unit_price"))
        )["s"]
        return agg or Decimal("0")

    # ---- age tracking ------------------------------------------------------

    @property
    def current_age_days(self) -> int:
        """Days since day_1_date. Returns 0 when not yet hatched.

        If ``age_end_date`` is set (batch is GROWN), the age is calculated
        up to that date rather than today — effectively freezing the age.
        """
        if not self.day_1_date:
            return 0
        end = self.age_end_date or timezone.localdate()
        return (end - self.day_1_date).days

    @property
    def current_age_display(self) -> str:
        """Human-readable age: '—' before hatching, 'Xw Yd' after.

        Once the batch is GROWN the age is frozen at the value it had on
        the ``age_end_date``.
        """
        if self.status in (self.Status.NEW, self.Status.INCUBATING):
            return "—"
        days = self.current_age_days
        weeks, remainder = divmod(days, 7)
        if weeks == 0:
            return f"{remainder}d"
        return f"{weeks}w {remainder}d"

    # ---- egg-batch specific ------------------------------------------------

    @property
    def failed_count(self) -> int:
        """Eggs that never hatched. Meaningful for egg batches once HATCHED."""
        if self.purchased_as != self.PurchasedAs.EGGS:
            return 0
        return max(self.initial_quantity - self.hatched_count, 0)

    @property
    def success_rate(self) -> float:
        if self.purchased_as != self.PurchasedAs.EGGS or not self.initial_quantity:
            return 0.0
        return self.hatched_count / self.initial_quantity

    @property
    def profit(self) -> Decimal:
        return self.revenue - self.total_cost


class Hatch(AuditedModel):
    """A daily hatch record on an egg batch. Quantities aggregate per day in the UI."""

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="hatches")
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
        if self.batch_id:
            if self.batch.status != Batch.Status.INCUBATING:
                raise ValidationError(
                    "Hatch records can only be added while the batch is incubating."
                )
            # Quantity cannot exceed the eggs still unhatched.
            # Exclude self when editing so the current record's saved value
            # doesn't count against the limit.
            existing_qs = Hatch.objects.filter(batch_id=self.batch_id)
            if self.pk:
                existing_qs = existing_qs.exclude(pk=self.pk)
            already_hatched = existing_qs.aggregate(s=Sum("quantity"))["s"] or 0
            eggs_remaining = self.batch.initial_quantity - already_hatched
            if self.quantity > eggs_remaining:
                raise ValidationError({
                    "quantity": (
                        f"Only {eggs_remaining} egg(s) remaining — "
                        f"cannot record {self.quantity} hatch(es)."
                    )
                })


class Expense(AuditedModel):
    """An operating expense, optionally attributed to a specific batch and/or supplier.

    Batch egg-purchase costs are captured on ``Batch.total_cost``; this model
    covers all other running costs (feed, medicine, labour, etc.) and supports
    per-batch profitability tracking when a batch is specified.
    """

    class Category(models.TextChoices):
        CLEANING   = "cleaning",   "Cleaning"
        CUSTOMS_EXCISE = "customs_excise", "Customs & Excise"
        ELECTRICITY = "electricity", "Electricity"
        EQUIPMENT   = "equipment",   "Equipment"
        FEED        = "feed",        "Feed"
        LABOR       = "labor",       "Labor"
        MAINTENANCE  = "maintenance",  "Maintenance"
        MEDICINE    = "medicine",    "Medicine"
        PACKAGING   = "packaging",   "Packaging"
        PHONE       = "phone",       "Phone"
        SERVICE_CHARGES = "service_charges", "Service Charges"
        SUPPLIES    = "supplies",    "Supplies"
        TRANSPORT   = "transport",   "Transport"
        OTHER       = "other",       "Other"

    batch    = models.ForeignKey(
        "Batch",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="expenses",
        help_text="Batch this expense is attributed to, if applicable.",
    )
    supplier = models.ForeignKey(
        "Supplier",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="expenses",
        help_text="Supplier this expense is attributed to, if applicable.",
    )
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
