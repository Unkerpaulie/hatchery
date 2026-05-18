"""Inventory forms for Supplier, Batch, and Hatch records."""

from django import forms

from .models import Batch, Hatch, Supplier

# ---- shared widget helpers -------------------------------------------------

_TEXT = {"class": "form-control"}
_DATE = {"class": "form-control", "type": "date"}
_TEXTAREA = {"class": "form-control", "rows": 3}
_SELECT = {"class": "form-control"}


# ---- Supplier --------------------------------------------------------------

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["business_name", "contact_name", "phone", "email", "address"]
        widgets = {
            "business_name": forms.TextInput(attrs=_TEXT),
            "contact_name":  forms.TextInput(attrs=_TEXT),
            "phone":         forms.TextInput(attrs=_TEXT),
            "email":         forms.EmailInput(attrs=_TEXT),
            "address":       forms.Textarea(attrs=_TEXTAREA),
        }
        labels = {
            "business_name": "Business Name",
            "contact_name":  "Contact Person",
        }


# ---- Batch -----------------------------------------------------------------

class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["supplier", "purchase_date", "quantity", "total_cost"]
        widgets = {
            "supplier":     forms.Select(attrs=_SELECT),
            "purchase_date": forms.DateInput(attrs=_DATE),
            "quantity":     forms.NumberInput(attrs=_TEXT),
            "total_cost":   forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
        }
        labels = {
            "total_cost": "Total Cost ($)",
            "quantity":   "Egg Quantity",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Supplier is optional on a batch.
        self.fields["supplier"].required = False
        self.fields["supplier"].empty_label = "— No supplier —"


# ---- Hatch record ----------------------------------------------------------

class HatchForm(forms.ModelForm):
    """Used both for the inline create form on batch_detail and the edit page."""

    class Meta:
        model = Hatch
        fields = ["date", "quantity"]
        widgets = {
            "date":     forms.DateInput(attrs=_DATE),
            "quantity": forms.NumberInput(attrs=_TEXT),
        }

    def __init__(self, *args, batch=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Stash the batch so we can run model-level validation in clean().
        self._batch = batch

    def clean(self):
        cleaned = super().clean()
        if self._batch and self._batch.status != Batch.Status.INCUBATING:
            raise forms.ValidationError(
                "Hatch records can only be added while the batch is incubating."
            )
        qty = cleaned.get("quantity")
        if qty is not None and qty <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        return cleaned
