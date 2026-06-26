"""Inventory forms for Supplier, Batch, Hatch, and Expense records."""

from django import forms

from .models import Batch, Expense, Hatch, Supplier

# ---- batch label helper for expense form ------------------------------------

def _expense_batch_label(batch):
    """Human-readable batch label shown in the Expense form dropdown."""
    return f"Batch #{batch.pk} ({batch.get_status_display()}) — {batch.purchase_date}"

# ---- shared widget helpers -------------------------------------------------

_TEXT = {"class": "form-control"}
_DATE = {"class": "form-control", "type": "date"}
_TEXTAREA = {"class": "form-control", "rows": 3}
_SELECT = {"class": "form-control"}


# ---- Supplier --------------------------------------------------------------

_CHECKBOX  = {"class": "form-check-input"}
_SELECT_SM = {"class": "form-control form-control-sm"}
_PHONE     = {**_TEXT, "data-phone-input": "1"}


def _strip_phone(value: str) -> str:
    """Return only the digit characters from *value* (strips E.164 '+' prefix
    and any formatting characters sent by intl-tel-input on submit)."""
    return "".join(c for c in (value or "") if c.isdigit())


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
            "phone_1":         forms.TextInput(attrs=_PHONE),
            "phone_1_type":    forms.Select(attrs=_SELECT_SM),
            "phone_1_whatsapp": forms.CheckboxInput(attrs=_CHECKBOX),
            "phone_2":         forms.TextInput(attrs=_PHONE),
            "phone_2_type":    forms.Select(attrs=_SELECT_SM),
            "phone_2_whatsapp": forms.CheckboxInput(attrs=_CHECKBOX),
            "phone_3":         forms.TextInput(attrs=_PHONE),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prepend '+' to digit-only stored phone values so intl-tel-input
        # can resolve the country code when rendering the edit form.
        for field in ("phone_1", "phone_2", "phone_3"):
            val = self.initial.get(field, "")
            if val and str(val).isdigit():
                self.initial[field] = f"+{val}"

    # ---- normalise phone fields on every save ------------------------------

    def clean_phone_1(self):
        return _strip_phone(self.cleaned_data.get("phone_1", ""))

    def clean_phone_2(self):
        return _strip_phone(self.cleaned_data.get("phone_2", ""))

    def clean_phone_3(self):
        return _strip_phone(self.cleaned_data.get("phone_3", ""))


# ---- Batch -----------------------------------------------------------------

class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = [
            "purchased_as", "supplier", "purchase_date",
            "initial_quantity", "age_at_purchase", "total_cost", "breed", "notes",
        ]
        widgets = {
            "purchased_as":    forms.RadioSelect(attrs={"class": "form-check-input"}),
            "supplier":        forms.Select(attrs=_SELECT),
            "purchase_date":   forms.DateInput(attrs=_DATE),
            "initial_quantity": forms.NumberInput(attrs=_TEXT),
            "age_at_purchase": forms.NumberInput(attrs={**_TEXT, "min": "0"}),
            "total_cost":      forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
            "breed":           forms.TextInput(attrs=_TEXT),
            "notes":           forms.Textarea(attrs=_TEXTAREA),
        }
        labels = {
            "purchased_as":    "Purchased As",
            "total_cost":      "Total Cost ($)",
            "initial_quantity": "Quantity",
            "age_at_purchase": "Age at Purchase (days)",
            "breed":           "Breed / Type",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].required = False
        self.fields["supplier"].empty_label = "— No supplier —"
        self.fields["age_at_purchase"].required = False
        # On edit, lock the purchase-origin fields — they are immutable.
        if self.instance.pk:
            self.fields["purchased_as"].disabled = True
            self.fields["age_at_purchase"].disabled = True

    def clean(self):
        cleaned = super().clean()
        purchased_as = cleaned.get("purchased_as")
        age = cleaned.get("age_at_purchase")
        if purchased_as == Batch.PurchasedAs.CHICKS and age is None:
            self.add_error("age_at_purchase", "Age at purchase is required for chick batches.")
        return cleaned


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
        fields = ["date", "category", "amount", "batch", "supplier", "description"]
        widgets = {
            "date":        forms.DateInput(attrs=_DATE),
            "category":    forms.Select(attrs=_SELECT),
            "amount":      forms.NumberInput(attrs=_MONEY),
            "batch":       forms.Select(attrs=_SELECT),
            "supplier":    forms.Select(attrs=_SELECT),
            "description": forms.TextInput(attrs=_TEXT),
        }
        labels = {"amount": "Amount ($)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = Batch.objects.order_by("-purchase_date", "-id")
        self.fields["batch"].label_from_instance = _expense_batch_label
        self.fields["batch"].empty_label = "— General expense (no batch) —"
        self.fields["supplier"].queryset = Supplier.objects.order_by("business_name")
        self.fields["supplier"].empty_label = "— No supplier —"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount
