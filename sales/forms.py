"""Sales forms: Customer, Sale header, SaleLine, Adjustment.

For PENDING sales, SaleLineForm skips the inventory ceiling check — lines on
a pending sale are drafts; the ceiling is enforced at close time in
SaleCloseView. AdjustmentForm still validates the ceiling on every save
because adjustments always commit immediately.
"""

from django import forms

from inventory.models import Batch

from .models import Adjustment, Customer, Sale, SaleLine

# ---- shared widget helpers -------------------------------------------------

_TEXT     = {"class": "form-control"}
_DATE     = {"class": "form-control", "type": "date"}
_TEXTAREA = {"class": "form-control", "rows": 3}
_SELECT   = {"class": "form-control"}
_NUMBER   = {"class": "form-control"}
_MONEY    = {"class": "form-control", "step": "0.01"}

# ---- batch queryset helper -------------------------------------------------

def _available_batches():
    """Annotated queryset of batches that currently have chicks available,
    ordered by batch number ascending (oldest first).
    """
    return Batch.objects.with_inventory().filter(chicks_available__gt=0).order_by("id")


def _batch_label(obj):
    return f"Batch #{obj.pk} ({obj.get_status_display()}) — {obj.chicks_available} available"


# ---- Customer --------------------------------------------------------------

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address"]
        widgets = {
            "name":    forms.TextInput(attrs=_TEXT),
            "phone":   forms.TextInput(attrs=_TEXT),
            "email":   forms.EmailInput(attrs=_TEXT),
            "address": forms.Textarea(attrs=_TEXTAREA),
        }


# ---- Sale header -----------------------------------------------------------

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ["customer", "date", "notes"]
        widgets = {
            "customer": forms.Select(attrs=_SELECT),
            "date":     forms.DateInput(attrs=_DATE),
            "notes":    forms.Textarea(attrs=_TEXTAREA),
        }


# ---- Sale line -------------------------------------------------------------

class SaleLineForm(forms.ModelForm):
    class Meta:
        model = SaleLine
        fields = ["batch", "quantity", "unit_price"]
        widgets = {
            "batch":      forms.Select(attrs=_SELECT),
            "quantity":   forms.NumberInput(attrs=_NUMBER),
            "unit_price": forms.NumberInput(attrs=_MONEY),
        }
        labels = {"unit_price": "Unit Price ($)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = _available_batches()
        self.fields["batch"].label_from_instance = _batch_label
        self.fields["batch"].empty_label = "— Select a batch —"

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity")
        if qty is not None and qty <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        return cleaned


# ---- Adjustment ------------------------------------------------------------

class AdjustmentForm(forms.ModelForm):
    class Meta:
        model = Adjustment
        fields = ["batch", "date", "quantity", "reason"]
        widgets = {
            "batch":    forms.Select(attrs=_SELECT),
            "date":     forms.DateInput(attrs=_DATE),
            "quantity": forms.NumberInput(attrs=_NUMBER),
            "reason":   forms.TextInput(attrs=_TEXT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = _available_batches()
        self.fields["batch"].label_from_instance = _batch_label
        self.fields["batch"].empty_label = "— Select a batch —"

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get("batch")
        qty   = cleaned.get("quantity")
        if batch and qty:
            prior = 0
            if self.instance.pk:
                prior = Adjustment.objects.filter(pk=self.instance.pk).values_list(
                    "quantity", flat=True
                ).first() or 0
            ceiling = batch.chicks_available + prior
            if qty > ceiling:
                self.add_error(
                    "quantity",
                    f"Only {ceiling} chick(s) available in Batch #{batch.pk}.",
                )
        return cleaned
