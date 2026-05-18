"""Sales URL routes."""

from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    # Customers
    path("customers/",              views.CustomerListView.as_view(),   name="customer_list"),
    path("customers/new/",          views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),

    # Sales
    path("",                        views.SaleListView.as_view(),       name="sale_list"),
    path("new/",                    views.SaleCreateView.as_view(),     name="sale_create"),
    path("<int:pk>/",               views.SaleDetailView.as_view(),     name="sale_detail"),

    # Sale lines (operated from the sale detail page)
    path("<int:sale_pk>/lines/add/", views.SaleLineCreateView.as_view(), name="saleline_create"),
    path("lines/<int:pk>/delete/",   views.SaleLineDeleteView.as_view(), name="saleline_delete"),

    # Adjustments
    path("adjustments/",            views.AdjustmentListView.as_view(),  name="adjustment_list"),
    path("adjustments/new/",        views.AdjustmentCreateView.as_view(), name="adjustment_create"),
]
