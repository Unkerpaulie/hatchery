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

_CHECKBOX = {"class": "form-check-input"}
_SELECT_SM = {"class": "form-control form-control-sm"}

# Phone inputs get a data attribute so the JS initializer can find them
# without relying on id_phone_N naming (which would break with form prefixes).
_PHONE = {**_TEXT, "data-phone-input": "1"}


def _strip_phone(value: str) -> str:
    """Return only the digit characters from *value*.

    intl-tel-input submits an E.164 string such as ``+18681234567``.
    This strips the leading ``+`` and any formatting characters, giving
    us the raw digit string we store in the database.
    """
    return "".join(c for c in (value or "") if c.isdigit())


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone_1", "phone_1_type", "phone_1_whatsapp",
            "phone_2", "phone_2_type", "phone_2_whatsapp",
            "phone_3", "phone_3_type", "phone_3_whatsapp",
            "email", "address", "notes",
        ]
        widgets = {
            "name":            forms.TextInput(attrs=_TEXT),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # When rendering an edit form, stored values are digit-only strings
        # (e.g. "18681234567"). Prepend '+' so intl-tel-input can parse the
        # country code and show the correct flag on page load.
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
