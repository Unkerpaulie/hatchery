"""Root URL configuration.

All non-admin routes are delegated to the core app, which composes routes for
the inventory and sales apps (rules.md \u00a72 \u2014 root-level urls begin in core).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),          # dashboard + auth
    path("inventory/", include("inventory.urls")),
    path("sales/", include("sales.urls")),
]
