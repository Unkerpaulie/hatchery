"""Core URL routes.

Composes auth endpoints, the dashboard, and the domain app routes
(``inventory`` and ``sales``) under the project root.
"""

from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("inventory/", include("inventory.urls")),
    path("sales/", include("sales.urls")),
]
