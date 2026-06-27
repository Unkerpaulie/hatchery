"""Core views: dashboard landing page, auth endpoints, and shared view mixins.

The dashboard aggregates read-only summary data from the inventory and sales
apps. Cross-app imports are intentional here — core is the one place that
has permission to reach across domain boundaries for display purposes
(rules.md §3).
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin


class AuditMixin:
    """View mixin that stamps ``created_by`` and ``updated_by`` on any model
    that inherits from ``AuditedModel`` before the form saves.

    Place this before ``LoginRequiredMixin`` and the generic view base in the
    inheritance list so Python's MRO calls this ``form_valid`` after the
    concrete view's own ``form_valid`` (which sets domain-specific instance
    fields) but before ``CreateView``/``UpdateView``'s ``form_valid`` (which
    calls ``form.save()``).  That ordering guarantees the audit fields are
    written to the instance before the INSERT or UPDATE hits the database.

    ``created_by`` is only set when the instance has no pk yet (new record).
    ``updated_by`` is set on every save so it always reflects the most recent
    actor.
    """

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)
from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from inventory.models import Batch, Expense, Hatch
from sales.models import Adjustment, MeatSaleLine, SaleLine


class DashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard: four KPI cards and a 30-day hatch/sale activity chart."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── KPI: eggs currently incubating ───────────────────────────────
        # Fetch total egg quantity and total already hatched for all
        # INCUBATING batches separately (avoids aggregating over compound
        # annotations, which SQLite can handle inconsistently).
        incubating_agg = (
            Batch.objects.with_inventory()
            .filter(status=Batch.Status.INCUBATING)
            .aggregate(
                total_qty=Coalesce(Sum("initial_quantity"), Value(0)),
                total_hatched=Coalesce(Sum("hatched_count"), Value(0)),
            )
        )
        ctx["eggs_incubating"] = (
            incubating_agg["total_qty"] - incubating_agg["total_hatched"]
        )

        # ── KPI: chicks available ────────────────────────────────────────
        # Includes HATCHED batches (full pool) and INCUBATING batches that
        # have partial hatch records. The annotation returns 0 for all other
        # statuses, so summing the whole table is safe and filter-free.
        zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        ctx["chicks_available"] = (
            Batch.objects.with_inventory()
            .aggregate(s=Coalesce(Sum("chicks_available"), Value(0)))["s"]
        )

        # ── KPI: grown chickens available for meat sale ───────────────────
        # birds_count for GROWN batches = chick_pool - sold - adjusted,
        # i.e. the remaining birds that haven't been sold as meat yet.
        ctx["grown_available"] = (
            Batch.objects.with_inventory()
            .filter(status=Batch.Status.GROWN)
            .aggregate(s=Coalesce(Sum("birds_count"), Value(0)))["s"]
        )

        # ── KPI: total costs (batch egg costs + operating expenses) ──────
        zero = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2))
        batch_costs   = Batch.objects.aggregate(s=Coalesce(Sum("total_cost"), zero))["s"]
        expense_costs = Expense.objects.aggregate(s=Coalesce(Sum("amount"), zero))["s"]
        ctx["total_costs"] = batch_costs + expense_costs

        # ── KPI: revenue ─────────────────────────────────────────────────
        # Chick sales: only CLOSED sale lines count as realised revenue.
        chick_revenue = SaleLine.objects.filter(sale__status="closed").aggregate(
            s=Coalesce(Sum(F("quantity") * F("unit_price")), zero)
        )["s"]
        # Meat sales: SUM(weight_lb × price_per_lb) across all lines.
        # Django joins through the FK so this is a single query.
        meat_revenue = MeatSaleLine.objects.aggregate(
            s=Coalesce(Sum(F("weight_lb") * F("meat_sale__price_per_lb")), zero)
        )["s"]
        ctx["total_revenue"] = chick_revenue + meat_revenue

        # ── Chart: daily activity for the past 30 days ───────────────────
        today = timezone.localdate()
        cutoff = today - timedelta(days=29)

        hatch_map = {
            str(r["date"]): r["qty"]
            for r in (
                Hatch.objects.filter(date__gte=cutoff)
                .values("date")
                .annotate(qty=Sum("quantity"))
            )
        }
        # Chicks sold per day (closed chick-sale lines).
        chick_sale_map = {
            str(r["sale__date"]): r["qty"]
            for r in (
                SaleLine.objects.filter(sale__date__gte=cutoff, sale__status="closed")
                .values("sale__date")
                .annotate(qty=Sum("quantity"))
            )
        }
        # Meat chickens sold per day (one MeatSaleLine row = one bird).
        meat_sale_map = {
            str(r["meat_sale__date"]): r["qty"]
            for r in (
                MeatSaleLine.objects.filter(meat_sale__date__gte=cutoff)
                .values("meat_sale__date")
                .annotate(qty=Count("pk"))
            )
        }

        labels = [
            (today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)
        ]
        ctx["chart_json"] = json.dumps({
            "labels":     labels,
            "hatched":    [hatch_map.get(d, 0)      for d in labels],
            "chick_sold": [chick_sale_map.get(d, 0) for d in labels],
            "meat_sold":  [meat_sale_map.get(d, 0)  for d in labels],
        })

        return ctx
