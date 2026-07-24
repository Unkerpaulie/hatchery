"""Sales forms: Customer, Sale header, SaleLine, Adjustment, MeatSale.

For PENDING sales, SaleLineForm skips the inventory ceiling check — lines on
a pending sale are drafts; the ceiling is enforced at close time in
SaleCloseView. AdjustmentForm still validates the ceiling on every save
because adjustments always commit immediately.

MeatSaleForm validates the weight list on every submit because meat sales
commit inventory immediately (no draft/pending state).
"""

from decimal import Decimal, InvalidOperation

from django import forms

from inventory.models import Batch

from .models import Adjustment, Customer, MeatSale, Sale, SaleLine

# ---- shared widget helpers -------------------------------------------------

_TEXT     = {"class": "form-control"}
_DATE     = {"class": "form-control", "type": "date"}
_TEXTAREA = {"class": "form-control", "rows": 3}
_SELECT   = {"class": "form-control"}
_NUMBER   = {"class": "form-control"}
_MONEY    = {"class": "form-control", "step": "0.01"}

# ---- batch queryset helper -------------------------------------------------

def _available_batches():
    """Annotated queryset of batches that currently have chicks available for sale,
    ordered by batch number ascending (oldest first).
    """
    return Batch.objects.with_inventory().filter(chicks_available__gt=0).order_by("id")


def _batch_label(obj):
    return f"Batch #{obj.pk} ({obj.get_status_display()}) — {obj.chicks_available} available"


def _adjustment_batches():
    """Annotated queryset of batches that have something adjustable (any status),
    ordered by batch number ascending (oldest first).
    """
    return Batch.objects.with_inventory().filter(adjustment_ceiling__gt=0).order_by("id")


def _adjustment_batch_label(obj):
    """Batch label for adjustment form — shows status-appropriate quantity."""
    status = obj.status
    ceiling = obj.adjustment_ceiling
    if status == Batch.Status.NEW:
        return f"Batch #{obj.pk} (New) — {ceiling} egg(s)"
    if status == Batch.Status.INCUBATING:
        return f"Batch #{obj.pk} (Incubating) — {ceiling} chick(s) available"
    if status == Batch.Status.HATCHED:
        return f"Batch #{obj.pk} (Hatched) — {ceiling} chick(s) available"
    # RAISING or GROWN
    return f"Batch #{obj.pk} ({obj.get_status_display()}) — {ceiling} bird(s)"


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
        fields = ["batch", "date", "quantity", "adjustment_type", "reason"]
        widgets = {
            "batch":           forms.Select(attrs=_SELECT),
            "date":            forms.DateInput(attrs=_DATE),
            "quantity":        forms.NumberInput(attrs=_NUMBER),
            "adjustment_type": forms.Select(attrs=_SELECT),
            "reason":          forms.TextInput(attrs=_TEXT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = _adjustment_batches()
        self.fields["batch"].label_from_instance = _adjustment_batch_label
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
            ceiling = batch.adjustment_ceiling + prior
            if qty > ceiling:
                self.add_error(
                    "quantity",
                    f"Only {ceiling} available to adjust in Batch #{batch.pk}.",
                )
        return cleaned


# ---- Meat sale helpers -----------------------------------------------------

def _meat_batches():
    """Annotated queryset of GROWN batches that still have birds available for meat sale."""
    return (
        Batch.objects.with_inventory()
        .filter(status=Batch.Status.GROWN, birds_count__gt=0)
        .order_by("id")
    )


def _meat_batch_label(obj):
    return f"Batch #{obj.pk} (Grown) — {obj.birds_count} bird(s) available"


# ---- Meat sale form --------------------------------------------------------

_WEIGHTS_TEXTAREA = {"class": "form-control", "rows": 10, "style": "font-family: monospace;"}


class MeatSaleForm(forms.ModelForm):
    """Form for a daily meat-chicken sale session.

    ``weights`` is a virtual field (not on the model): a textarea where the
    user pastes one weight per line. ``clean_weights`` parses the text into a
    list of Decimals; ``clean`` checks the count against batch availability.
    The view converts the parsed list into MeatSaleLine bulk inserts.
    """

    weights = forms.CharField(
        widget=forms.Textarea(attrs=_WEIGHTS_TEXTAREA),
        label="Chicken weights (lbs)",
        help_text=(
            "One weight per line. Use a decimal point (e.g. 4.2) — "
            "commas are accepted as decimal separators. "
            "No letters, units, or extra punctuation."
        ),
    )

    class Meta:
        model = MeatSale
        fields = ["batch", "date", "price_per_lb", "notes"]
        widgets = {
            "batch":        forms.Select(attrs=_SELECT),
            "date":         forms.DateInput(attrs=_DATE),
            "price_per_lb": forms.NumberInput(attrs=_MONEY),
            "notes":        forms.Textarea(attrs=_TEXTAREA),
        }
        labels = {"price_per_lb": "Price per lb ($)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = _meat_batches()
        self.fields["batch"].label_from_instance = _meat_batch_label
        self.fields["batch"].empty_label = "— Select a batch —"

    def clean_weights(self):
        """Parse the weights textarea into a list of positive Decimals.

        Normalisation applied before parsing:
          - Leading/trailing whitespace stripped per line.
          - Blank lines silently skipped.
          - A single comma is treated as a decimal separator (4,2 → 4.2).
            A comma used as a thousands separator (4,200) is still rejected
            because the result after replacement ('4.200') is unambiguous and
            parses correctly, while an ambiguous case like '4,2,00' will fail.

        All errors are collected before raising so the user sees every
        problem in one pass rather than fixing them one at a time.
        """
        raw = self.cleaned_data.get("weights", "")
        parsed = []
        errors = []

        for i, line in enumerate(raw.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue

            # Normalise comma-as-decimal-separator: only when there is
            # exactly one comma and no dot already present.
            normalised = line
            if "," in normalised and "." not in normalised and normalised.count(",") == 1:
                normalised = normalised.replace(",", ".")

            try:
                weight = Decimal(normalised)
                # Guard against special Decimal values (Infinity, NaN).
                if not weight.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                errors.append(f"Line {i}: '{line}' is not a valid number.")
                continue

            if weight <= 0:
                errors.append(f"Line {i}: weight must be greater than zero (got {line}).")
                continue

            parsed.append(weight)

        if errors:
            raise forms.ValidationError(errors)

        if not parsed:
            raise forms.ValidationError("Please enter at least one weight.")

        return parsed

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get("batch")
        weights = cleaned.get("weights")  # list of Decimals after clean_weights
        if batch and weights:
            batch_inv = Batch.objects.with_inventory().get(pk=batch.pk)
            if len(weights) > batch_inv.birds_count:
                raise forms.ValidationError(
                    f"You entered {len(weights)} weight(s) but Batch #{batch.pk} "
                    f"only has {batch_inv.birds_count} bird(s) available."
                )
        return cleaned
