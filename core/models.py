"""Core shared models.

Houses the abstract ``Party`` base used by inventory.Supplier and sales.Customer
to share contact-detail fields (rules.md §3 — shared logic centralized only
when reuse is proven; the PRD calls for this explicitly).
"""

from django.db import models


class Party(models.Model):
    """Abstract base for any external party (supplier, customer, etc.).

    Concrete subclasses are responsible for providing whatever ``name``-like
    field is appropriate for their domain (e.g. a business name for a
    supplier, a personal name for a customer).

    Three phone slots are provided (phone_1 / phone_2 / phone_3). Each slot
    carries a type label and a WhatsApp flag. Helper properties generate
    ready-to-use wa.me URLs for slots that have WhatsApp enabled.
    """

    class PhoneType(models.TextChoices):
        WORK     = "work",     "Work"
        PERSONAL = "personal", "Personal"
        MOBILE   = "mobile",   "Mobile"
        FAX      = "fax",      "Fax"
        OTHER    = "other",    "Other"

    # ---- phone slot 1 -------------------------------------------------------
    phone_1          = models.CharField(max_length=32, blank=True, verbose_name="Phone 1")
    phone_1_type     = models.CharField(
        max_length=10, choices=PhoneType.choices, default=PhoneType.MOBILE,
        blank=True, verbose_name="Type"
    )
    phone_1_whatsapp = models.BooleanField(default=False, verbose_name="WhatsApp")

    # ---- phone slot 2 -------------------------------------------------------
    phone_2          = models.CharField(max_length=32, blank=True, verbose_name="Phone 2")
    phone_2_type     = models.CharField(
        max_length=10, choices=PhoneType.choices, default=PhoneType.MOBILE,
        blank=True, verbose_name="Type"
    )
    phone_2_whatsapp = models.BooleanField(default=False, verbose_name="WhatsApp")

    # ---- phone slot 3 -------------------------------------------------------
    phone_3          = models.CharField(max_length=32, blank=True, verbose_name="Phone 3")
    phone_3_type     = models.CharField(
        max_length=10, choices=PhoneType.choices, default=PhoneType.MOBILE,
        blank=True, verbose_name="Type"
    )
    phone_3_whatsapp = models.BooleanField(default=False, verbose_name="WhatsApp")

    # ---- other contact fields -----------------------------------------------
    email   = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes   = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    # ---- WhatsApp URL helpers -----------------------------------------------

    @staticmethod
    def _wa_url(phone: str) -> str:
        """Return a wa.me deep-link for *phone*, or an empty string if blank."""
        digits = "".join(c for c in phone if c.isdigit())
        return f"https://wa.me/{digits}" if digits else ""

    @property
    def phone_1_wa_url(self) -> str:
        return self._wa_url(self.phone_1)

    @property
    def phone_2_wa_url(self) -> str:
        return self._wa_url(self.phone_2)

    @property
    def phone_3_wa_url(self) -> str:
        return self._wa_url(self.phone_3)
