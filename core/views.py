"""Core views: dashboard landing page and auth endpoints wiring.

The dashboard aggregates read-only summary data from the inventory and sales
apps. Cross-app imports are intentional here — core is the one place that
has permission to reach across domain boundaries for display purposes
(rules.md §3).
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView

from inventory.models import Batch, Hatch
from sales.models import Adjustment, SaleLine


class DashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard: four KPI cards and a 30-day hatch/sale activity chart."""

    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── KPI: batch counts ────────────────────────────────────────────
        ctx["active_batches"] = Batch.objects.filter(
            status=Batch.Status.INCUBATING
        ).count()

        # ── KPI: inventory totals ────────────────────────────────────────
        # Use three separate top-level aggregates so we can both display
        # total_hatched as its own card and derive chicks_available without
        # aggregating over a compound annotation (which SQLite doesn't
        # always handle cleanly).
        total_hatched = (
            Hatch.objects.aggregate(s=Coalesce(Sum("quantity"), Value(0)))["s"]
        )
        total_sold = (
            SaleLine.objects.aggregate(s=Coalesce(Sum("quantity"), Value(0)))["s"]
        )
        total_adjusted = (
            Adjustment.objects.aggregate(s=Coalesce(Sum("quantity"), Value(0)))["s"]
        )

        ctx["total_hatched"] = total_hatched
        ctx["chicks_available"] = total_hatched - total_sold - total_adjusted

        # ── KPI: revenue ─────────────────────────────────────────────────
        zero = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2))
        ctx["total_revenue"] = SaleLine.objects.aggregate(
            s=Coalesce(Sum(F("quantity") * F("unit_price")), zero)
        )["s"]

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
        sale_map = {
            str(r["sale__date"]): r["qty"]
            for r in (
                SaleLine.objects.filter(sale__date__gte=cutoff)
                .values("sale__date")
                .annotate(qty=Sum("quantity"))
            )
        }

        labels = [
            (today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)
        ]
        ctx["chart_json"] = json.dumps({
            "labels": labels,
            "hatched": [hatch_map.get(d, 0) for d in labels],
            "sold":    [sale_map.get(d, 0)  for d in labels],
        })

        return ctx
