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

from sales.models import SaleLine

from .forms import BatchForm, HatchForm, SupplierForm
from .models import Batch, Hatch, Supplier


# ---------------------------------------------------------------------------
# Supplier views
# ---------------------------------------------------------------------------

class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = "inventory/supplier_list.html"
    context_object_name = "suppliers"


class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    success_url = reverse_lazy("inventory:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier created successfully.")
        return super().form_valid(form)


class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    context_object_name = "supplier"
    success_url = reverse_lazy("inventory:supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier updated successfully.")
        return super().form_valid(form)


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


class BatchCreateView(LoginRequiredMixin, CreateView):
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
        ctx["hatch_form"] = HatchForm(batch=batch)
        ctx["today"] = timezone.localdate()
        # Pre-compute values templates can't derive without arithmetic filters.
        ctx["eggs_remaining"] = batch.quantity - batch.hatched_count
        ctx["success_rate_pct"] = round(batch.success_rate * 100, 1)
        if batch.status == Batch.Status.DONE:
            ctx["sale_lines"] = (
                SaleLine.objects.filter(batch=batch)
                .select_related("sale__customer")
                .order_by("sale__date")
            )
        return ctx


class BatchBeginIncubationView(LoginRequiredMixin, View):
    """POST-only action: move batch from READY to INCUBATING."""

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.begin_incubation()
            messages.success(request, "Incubation started.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


class BatchCompleteView(LoginRequiredMixin, View):
    """POST-only action: mark batch as DONE."""

    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk)
        try:
            batch.complete()
            messages.success(request, "Batch marked as complete.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect("inventory:batch_detail", pk=pk)


# ---------------------------------------------------------------------------
# Hatch record views
# ---------------------------------------------------------------------------

class HatchCreateView(LoginRequiredMixin, CreateView):
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


class HatchUpdateView(LoginRequiredMixin, UpdateView):
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
