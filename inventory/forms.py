"""Inventory forms for Supplier, Batch, Hatch, and Expense records."""

from django import forms

from .models import Batch, Expense, Hatch, Supplier

# ---- shared widget helpers -------------------------------------------------

_TEXT = {"class": "form-control"}
_DATE = {"class": "form-control", "type": "date"}
_TEXTAREA = {"class": "form-control", "rows": 3}
_SELECT = {"class": "form-control"}


# ---- Supplier --------------------------------------------------------------

_CHECKBOX  = {"class": "form-check-input"}
_SELECT_SM = {"class": "form-control form-control-sm"}

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "business_name", "contact_name", "website",
            "phone_1", "phone_1_type", "phone_1_whatsapp",
            "phone_2", "phone_2_type", "phone_2_whatsapp",
            "phone_3", "phone_3_type", "phone_3_whatsapp",
            "email", "address", "notes",
        ]
        widgets = {
            "business_name":   forms.TextInput(attrs=_TEXT),
            "contact_name":    forms.TextInput(attrs=_TEXT),
            "website":         forms.URLInput(attrs=_TEXT),
            "phone_1":         forms.TextInput(attrs=_TEXT),
            "phone_1_type":    forms.Select(attrs=_SELECT_SM),
            "phone_1_whatsapp": forms.CheckboxInput(attrs=_CHECKBOX),
            "phone_2":         forms.TextInput(attrs=_TEXT),
            "phone_2_type":    forms.Select(attrs=_SELECT_SM),
            "phone_2_whatsapp": forms.CheckboxInput(attrs=_CHECKBOX),
            "phone_3":         forms.TextInput(attrs=_TEXT),
            "phone_3_type":    forms.Select(attrs=_SELECT_SM),
            "phone_3_whatsapp": forms.CheckboxInput(attrs=_CHECKBOX),
            "email":           forms.EmailInput(attrs=_TEXT),
            "address":         forms.Textarea(attrs=_TEXTAREA),
            "notes":           forms.Textarea(attrs=_TEXTAREA),
        }
        labels = {
            "business_name": "Business Name",
            "contact_name":  "Contact Person",
            "website":       "Website",
        }


# ---- Batch -----------------------------------------------------------------

class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["supplier", "purchase_date", "quantity", "total_cost", "breed", "notes"]
        widgets = {
            "supplier":      forms.Select(attrs=_SELECT),
            "purchase_date": forms.DateInput(attrs=_DATE),
            "quantity":      forms.NumberInput(attrs=_TEXT),
            "total_cost":    forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
            "breed":         forms.TextInput(attrs=_TEXT),
            "notes":         forms.Textarea(attrs=_TEXTAREA),
        }
        labels = {
            "total_cost": "Total Cost ($)",
            "quantity":   "Egg Quantity",
            "breed":      "Breed / Type",
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


# ---- Expense ---------------------------------------------------------------

_MONEY = {"class": "form-control", "step": "0.01"}

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "amount", "description"]
        widgets = {
            "date":        forms.DateInput(attrs=_DATE),
            "category":    forms.Select(attrs=_SELECT),
            "amount":      forms.NumberInput(attrs=_MONEY),
            "description": forms.TextInput(attrs=_TEXT),
        }
        labels = {"amount": "Amount ($)"}

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount
