"""Sales views: Customer CRUD (no delete), Sale lifecycle, SaleLine
add/delete, and Adjustment management.

All views require login. Business logic stays on models/forms (rules.md §8).
"""

import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import DecimalField, F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from inventory.models import Batch

from .forms import AdjustmentForm, CustomerForm, SaleForm, SaleLineForm
from .models import Adjustment, Customer, Sale, SaleLine


# ---------------------------------------------------------------------------
# Customer views  (no delete — enforced here and at admin level)
# ---------------------------------------------------------------------------

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = "sales/customer_list.html"
    context_object_name = "customers"


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "sales/customer_form.html"
    success_url = reverse_lazy("sales:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Customer created.")
        return super().form_valid(form)


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "sales/customer_form.html"
    context_object_name = "customer"
    success_url = reverse_lazy("sales:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Customer updated.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Sale views
# ---------------------------------------------------------------------------

def _sale_list_queryset():
    """Annotated Sale queryset used by both list and any future exports."""
    qty_sq = (
        SaleLine.objects.filter(sale=OuterRef("pk"))
        .values("sale").annotate(s=Sum("quantity")).values("s")
    )
    rev_sq = (
        SaleLine.objects.filter(sale=OuterRef("pk"))
        .values("sale").annotate(s=Sum(F("quantity") * F("unit_price"))).values("s")
    )
    zero_money = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=2))
    return Sale.objects.select_related("customer").annotate(
        total_quantity=Coalesce(Subquery(qty_sq, output_field=IntegerField()), 0),
        total_revenue=Coalesce(Subquery(rev_sq, output_field=DecimalField(max_digits=12, decimal_places=2)), zero_money),
    )


class SaleListView(LoginRequiredMixin, ListView):
    template_name = "sales/sale_list.html"
    context_object_name = "sales"

    def get_queryset(self):
        return _sale_list_queryset()


class SaleCreateView(LoginRequiredMixin, CreateView):
    model = Sale
    form_class = SaleForm
    template_name = "sales/sale_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Sale created. Now add chick line items below.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("sales:sale_detail", kwargs={"pk": self.object.pk})


class SaleDetailView(LoginRequiredMixin, DetailView):
    template_name = "sales/sale_detail.html"
    context_object_name = "sale"

    def get_queryset(self):
        return Sale.objects.select_related("customer").prefetch_related(
            "lines__batch__supplier"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["saleline_form"] = SaleLineForm()
        # JSON map of batch_id → available chicks for the JS available-count display.
        avail = {
            str(b.pk): b.chicks_available
            for b in Batch.objects.with_inventory().filter(chicks_available__gt=0)
        }
        ctx["batch_available_json"] = json.dumps(avail)
        return ctx


# ---------------------------------------------------------------------------
# Sale line views
# ---------------------------------------------------------------------------

class SaleLineCreateView(LoginRequiredMixin, CreateView):
    model = SaleLine
    form_class = SaleLineForm

    def get_sale(self):
        return get_object_or_404(Sale, pk=self.kwargs["sale_pk"])

    def form_valid(self, form):
        form.instance.sale = self.get_sale()
        messages.success(self.request, "Chick line added.")
        return super().form_valid(form)

    def form_invalid(self, form):
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return redirect("sales:sale_detail", pk=self.kwargs["sale_pk"])

    def get_success_url(self):
        return reverse("sales:sale_detail", kwargs={"pk": self.kwargs["sale_pk"]})


class SaleLineDeleteView(LoginRequiredMixin, View):
    """POST-only delete — confirmed via modal on the sale detail page."""

    def post(self, request, pk):
        line = get_object_or_404(SaleLine, pk=pk)
        sale_pk = line.sale_id
        line.delete()
        messages.success(request, "Line item removed.")
        return redirect("sales:sale_detail", pk=sale_pk)


# ---------------------------------------------------------------------------
# Adjustment views
# ---------------------------------------------------------------------------

class AdjustmentListView(LoginRequiredMixin, ListView):
    template_name = "sales/adjustment_list.html"
    context_object_name = "adjustments"

    def get_queryset(self):
        return Adjustment.objects.select_related("batch__supplier")


class AdjustmentCreateView(LoginRequiredMixin, CreateView):
    model = Adjustment
    form_class = AdjustmentForm
    template_name = "sales/adjustment_form.html"
    success_url = reverse_lazy("sales:adjustment_list")

    def form_valid(self, form):
        messages.success(self.request, "Adjustment recorded.")
        return super().form_valid(form)
