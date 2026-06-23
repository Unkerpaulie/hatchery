"""Inventory views: Supplier CRUD and Batch lifecycle (list, create, detail,
begin-incubation, complete, hatch-record add/edit/delete).

Views stay thin: business logic lives on models/forms (rules.md §8).
All views require login (rules.md §14).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView,
)

from core.views import AuditMixin
from sales.models import Adjustment, SaleLine

from .forms import BatchForm, ExpenseForm, HatchForm, SupplierForm
from .models import Batch, Expense, Hatch, Supplier

# Statuses where chick inventory is tracked and sale lines are shown.
_CHICK_SALE_STATUSES = (Batch.Status.HATCHED, Batch.Status.RAISING, Batch.Status.GROWN)


# ---------------------------------------------------------------------------
# Supplier views
# ---------------------------------------------------------------------------

class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = "inventory/supplier_list.html"
    context_object_name = "suppliers"


class SupplierCreateView(AuditMixin, LoginRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    success_url = reverse_lazy("inventory:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier created successfully.")
        return super().form_valid(form)


class SupplierUpdateView(AuditMixin, LoginRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    context_object_name = "supplier"
    success_url = reverse_lazy("inventory:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier updated successfully.")
        return super().form_valid(form)


class SupplierDetailView(LoginRequiredMixin, DetailView):
    model = Supplier
    template_name = "inventory/supplier_detail.html"
    context_object_name = "supplier"

    def get_queryset(self):
        return Supplier.objects.prefetch_related("batches")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        s = self.object
        # Build a list of (number, label, display_type, has_whatsapp, wa_url)
        # so the template can loop without repeating itself.
        ctx["phone_entries"] = [
            (s.phone_1, "Phone 1", s.get_phone_1_type_display(), s.phone_1_whatsapp, s.phone_1_wa_url),
            (s.phone_2, "Phone 2", s.get_phone_2_type_display(), s.phone_2_whatsapp, s.phone_2_wa_url),
            (s.phone_3, "Phone 3", s.get_phone_3_type_display(), s.phone_3_whatsapp, s.phone_3_wa_url),
        ]
        return ctx


class SupplierDeleteView(LoginRequiredMixin, DeleteView):
    model = Supplier
    template_name = "inventory/supplier_confirm_delete.html"
    context_object_name = "supplier"
    success_url = reverse_lazy("inventory:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier deleted.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Batch views
# ---------------------------------------------------------------------------

class BatchListView(LoginRequiredMixin, ListView):
    template_name = "inventory/batch_list.html"
    context_object_name = "batches"

    def get_queryset(self):
        return Batch.objects.with_inventory().select_related("supplier")


class BatchCreateView(AuditMixin, LoginRequiredMixin, CreateView):
    model = Batch
    form_class = BatchForm
    template_name = "inventory/batch_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Batch created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:batch_detail", kwargs={"pk": self.object.pk})


class BatchDetailView(LoginRequiredMixin, DetailView):
    template_name = "inventory/batch_detail.html"
    context_object_name = "batch"

    def get_queryset(self):
        return Batch.objects.select_related("supplier").prefetch_related("hatches")

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        ctx = super().get_context_data(**kwargs)
        batch = self.object
        ctx["today"] = timezone.localdate()

        # Hatch form and egg-specific stats only apply to egg batches in INCUBATING.
        if batch.purchased_as == Batch.PurchasedAs.EGGS and batch.status == Batch.Status.INCUBATING:
            ctx["hatch_form"] = HatchForm(batch=batch)
            ctx["eggs_remaining"] = batch.initial_quantity - batch.hatched_count

        ctx["success_rate_pct"] = round(batch.success_rate * 100, 1)

        # Show sale history once chicks have entered the market (HATCHED or beyond).
        if batch.status in _CHICK_SALE_STATUSES:
            ctx["sale_lines"] = (
                SaleLine.objects.filter(batch=batch)
                .select_related("sale__customer")
                .order_by("sale__date")
            )
        return ctx


class BatchUpdateView(AuditMixin, LoginRequiredMixin, UpdateView):
    model = Batch
    form_class = BatchForm
    template_name = "inventory/batch_form.html"
    context_object_name = "batch"

    def form_valid(self, form):
        messages.success(self.request, "Batch updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:batch_detail", kwargs={"pk": self.object.pk})


class BatchDeleteView(LoginRequiredMixin, DeleteView):
    model = Batch
    template_name = "inventory/batch_confirm_delete.html"
    context_object_name = "batch"
    success_url = reverse_lazy("inventory:batch_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        batch = self.object
        ctx["hatches"] = batch.hatches.order_by("date")
        ctx["sale_lines"] = (
            SaleLine.objects
            .filter(batch=batch)
            .select_related("sale__customer")
            .order_by("sale__date")
        )
        ctx["adjustments"] = (
            Adjustment.objects
            .filter(batch=batch)
            .order_by("date")
        )
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Batch and all associated records deleted.")
        return super().form_valid(form)


class BatchBeginIncubationView(LoginRequiredMixin, View):
    """POST-only action: move egg batch from NEW to INCUBATING."""

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.begin_incubation(updated_by=request.user)
            messages.success(request, "Incubation started.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


class BatchMarkHatchedView(LoginRequiredMixin, View):
    """POST-only action: move egg batch from INCUBATING to HATCHED."""

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.mark_hatched(updated_by=request.user)
            messages.success(request, "Batch marked as hatched. Age tracking begins today.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


class BatchBeginRaisingView(LoginRequiredMixin, View):
    """POST-only action: move batch from HATCHED to RAISING.

    All remaining chicks are committed to growing; the batch leaves
    chick-sale inventory.
    """

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.begin_raising(updated_by=request.user)
            messages.success(request, "Batch moved to raising. Chicks are no longer available for sale.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


class BatchMarkGrownView(LoginRequiredMixin, View):
    """POST-only action: move batch from RAISING to GROWN."""

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.mark_grown(updated_by=request.user)
            messages.success(request, "Batch marked as grown and ready for meat sale.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


# ---------------------------------------------------------------------------
# Hatch record views
# ---------------------------------------------------------------------------

class HatchCreateView(AuditMixin, LoginRequiredMixin, CreateView):
    """Create a hatch record; submitted from the batch detail page."""

    model = Hatch
    form_class = HatchForm

    def get_batch(self):
        return get_object_or_404(Batch, pk=self.kwargs["batch_pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["batch"] = self.get_batch()
        return kwargs

    def form_valid(self, form):
        form.instance.batch = self.get_batch()
        messages.success(self.request, "Hatch record added.")
        return super().form_valid(form)

    def form_invalid(self, form):
        # Surface validation errors as a message and redirect back.
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(self.request, error)
        return redirect("inventory:batch_detail", pk=self.kwargs["batch_pk"])

    def get_success_url(self):
        return reverse("inventory:batch_detail", kwargs={"pk": self.kwargs["batch_pk"]})


class HatchUpdateView(AuditMixin, LoginRequiredMixin, UpdateView):
    model = Hatch
    form_class = HatchForm
    template_name = "inventory/hatch_form.html"
    context_object_name = "hatch"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["batch"] = self.object.batch
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Hatch record updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:batch_detail", kwargs={"pk": self.object.batch_id})


class HatchDeleteView(LoginRequiredMixin, View):
    """POST-only delete; confirmation is a modal on the batch detail page."""

    def post(self, request, pk):
        hatch = get_object_or_404(Hatch, pk=pk)
        batch_pk = hatch.batch_id
        hatch.delete()
        messages.success(request, "Hatch record deleted.")
        return redirect("inventory:batch_detail", pk=batch_pk)


# ---------------------------------------------------------------------------
# Expense views
# ---------------------------------------------------------------------------

class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = "inventory/expense_list.html"
    context_object_name = "expenses"


class ExpenseCreateView(AuditMixin, LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "inventory/expense_form.html"
    success_url = reverse_lazy("inventory:expense_list")

    def form_valid(self, form):
        messages.success(self.request, "Expense recorded.")
        return super().form_valid(form)


class ExpenseUpdateView(AuditMixin, LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "inventory/expense_form.html"
    context_object_name = "expense"
    success_url = reverse_lazy("inventory:expense_list")

    def form_valid(self, form):
        messages.success(self.request, "Expense updated.")
        return super().form_valid(form)


class ExpenseDeleteView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = "inventory/expense_confirm_delete.html"
    context_object_name = "expense"
    success_url = reverse_lazy("inventory:expense_list")

    def form_valid(self, form):
        messages.success(self.request, "Expense deleted.")
        return super().form_valid(form)
