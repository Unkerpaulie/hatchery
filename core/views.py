"""Core views: dashboard landing page and auth endpoints wiring."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    """Placeholder dashboard. Phase 5 fills in KPI cards and the chart."""

    template_name = "core/dashboard.html"
