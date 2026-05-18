"""Core shared models.

Houses the abstract ``Party`` base used by inventory.Supplier and sales.Customer
to share contact-detail fields (rules.md \u00a73 \u2014 shared logic centralized only
when reuse is proven; the PRD calls for this explicitly).
"""

from django.db import models


class Party(models.Model):
    """Abstract base for any external party (supplier, customer, etc.).

    Concrete subclasses are responsible for providing whatever ``name``-like
    field is appropriate for their domain (e.g. a business name for a
    supplier, a personal name for a customer).
    """

    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
