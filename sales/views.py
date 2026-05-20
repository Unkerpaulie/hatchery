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


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = "sales/customer_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = self.object

        # Evaluate once into a list so we can iterate twice without a second query.
        sales = list(
            _sale_list_queryset()
            .filter(customer=customer)
            .order_by("-date", "-id")
        )
        ctx["sales"] = sales
        ctx["grand_total_quantity"] = sum(s.total_quantity for s in sales)
        ctx["grand_total_revenue"]  = sum(s.total_revenue  for s in sales)

        # Phone entries for the contact card — same pattern as supplier_detail.
        ctx["phone_entries"] = [
            (customer.phone_1, "Phone 1", customer.get_phone_1_type_display(), customer.phone_1_whatsapp, customer.phone_1_wa_url),
            (customer.phone_2, "Phone 2", customer.get_phone_2_type_display(), customer.phone_2_whatsapp, customer.phone_2_wa_url),
            (customer.phone_3, "Phone 3", customer.get_phone_3_type_display(), customer.phone_3_whatsapp, customer.phone_3_wa_url),
        ]
        return ctx


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
        sale = self.object
        ctx["saleline_form"] = SaleLineForm()

        # JSON map of batch_id → available chicks for the JS available-count display
        # shown next to the "Add Chicks" batch selector.
        avail = {
            str(b.pk): b.chicks_available
            for b in Batch.objects.with_inventory().filter(chicks_available__gt=0)
        }
        ctx["batch_available_json"] = json.dumps(avail)

        # For PENDING sales: find line items whose requested quantity now
        # exceeds the batch's current available stock.  This can happen when
        # another sale referencing the same batch has since been closed.
        ctx["over_committed_pks"] = set()   # set of line PKs — used by {% if line.pk in … %}
        ctx["line_avail_json"] = "{}"       # JSON {str(line.pk): available} for JS tooltips

        if sale.status == Sale.Status.PENDING:
            lines = list(sale.lines.all())
            if lines:
                batch_ids = list({line.batch_id for line in lines})
                batch_avail = {
                    b.pk: b.chicks_available
                    for b in Batch.objects.with_inventory().filter(pk__in=batch_ids)
                }
                over = {
                    line.pk: batch_avail.get(line.batch_id, 0)
                    for line in lines
                    if line.quantity > batch_avail.get(line.batch_id, 0)
                }
                ctx["over_committed_pks"] = set(over.keys())
                # JSON uses string keys so JS can look up by data attribute value.
                ctx["line_avail_json"] = json.dumps({str(k): v for k, v in over.items()})

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
        sale = self.get_sale()
        if sale.status != Sale.Status.PENDING:
            messages.error(self.request, "Lines can only be added to pending sales.")
            return redirect("sales:sale_detail", pk=sale.pk)
        form.instance.sale = sale
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
    """POST-only delete — confirmed via modal on the sale detail page.
    Only allowed while the parent sale is PENDING.
    """

    def post(self, request, pk):
        line = get_object_or_404(SaleLine, pk=pk)
        sale = line.sale
        if sale.status != Sale.Status.PENDING:
            messages.error(request, "Lines can only be removed from pending sales.")
            return redirect("sales:sale_detail", pk=sale.pk)
        line.delete()
        messages.success(request, "Line item removed.")
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleCloseView(LoginRequiredMixin, View):
    """POST-only action: validate inventory then transition sale to CLOSED.

    Inventory ceiling is checked here for every line in the sale. Because
    only CLOSED sales are counted in ``sold_count``, the batch's
    ``chicks_available`` value already excludes this (still-pending) sale, so
    we simply compare each line's quantity against the current available stock.
    """

    def post(self, request, pk):
        sale = get_object_or_404(Sale.objects.prefetch_related("lines__batch"), pk=pk)
        if sale.status != Sale.Status.PENDING:
            messages.error(request, "Only pending sales can be closed.")
            return redirect("sales:sale_detail", pk=pk)

        lines = list(sale.lines.all())
        if not lines:
            messages.error(request, "Cannot close a sale with no line items.")
            return redirect("sales:sale_detail", pk=pk)

        # Fetch fresh inventory annotations for all relevant batches.
        batch_ids = [l.batch_id for l in lines]
        batch_map = {
            b.pk: b
            for b in Batch.objects.with_inventory().filter(pk__in=batch_ids)
        }

        # Aggregate total quantity requested per batch across all lines in
        # this sale (a batch can appear on multiple lines).
        from collections import defaultdict
        needed: dict = defaultdict(int)
        for line in lines:
            needed[line.batch_id] += line.quantity

        errors = []
        for batch_id, qty in needed.items():
            batch = batch_map[batch_id]
            if qty > batch.chicks_available:
                errors.append(
                    f"Batch #{batch_id}: {qty} requested but only "
                    f"{batch.chicks_available} available."
                )

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect("sales:sale_detail", pk=pk)

        sale.status = Sale.Status.CLOSED
        sale.save(update_fields=["status", "updated_at"])
        messages.success(request, "Sale closed — inventory has been committed.")
        return redirect("sales:sale_detail", pk=pk)


class SaleCancelView(LoginRequiredMixin, View):
    """POST-only action: cancel a pending sale. Has no inventory effect."""

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        if sale.status != Sale.Status.PENDING:
            messages.error(request, "Only pending sales can be cancelled.")
            return redirect("sales:sale_detail", pk=pk)
        sale.status = Sale.Status.CANCELLED
        sale.save(update_fields=["status", "updated_at"])
        messages.success(request, "Sale cancelled.")
        return redirect("sales:sale_detail", pk=pk)


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
