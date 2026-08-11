"""Sales URL routes."""

from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    # Customers
    path("customers/",               views.CustomerListView.as_view(),   name="customer_list"),
    path("customers/new/",           views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/",      views.CustomerDetailView.as_view(), name="customer_detail"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),

    # Chick sales
    path("",                         views.SaleListView.as_view(),    name="sale_list"),
    path("new/",                     views.SaleCreateView.as_view(),  name="sale_create"),
    path("<int:pk>/",                views.SaleDetailView.as_view(),  name="sale_detail"),
    path("<int:pk>/edit/",           views.SaleUpdateView.as_view(),        name="sale_update"),
    path("<int:pk>/finalize/",       views.SaleFinalizeView.as_view(),      name="sale_finalize"),
    path("<int:pk>/update-payment/", views.SaleUpdatePaymentView.as_view(), name="sale_update_payment"),
    path("<int:pk>/cancel/",         views.SaleCancelView.as_view(),        name="sale_cancel"),
    path("<int:pk>/invoice/",        views.SaleInvoiceView.as_view(),       name="sale_invoice"),

    # Meat sales (daily retail)
    path("meat/",                 views.MeatSaleListView.as_view(),        name="meat_sale_list"),
    path("meat/new/",             views.MeatSaleCreateView.as_view(),      name="meat_sale_create"),
    path("meat/calculate/",       views.MeatSaleCalculateView.as_view(),   name="meat_sale_calculate"),
    path("meat/<int:pk>/detail/", views.MeatSaleDetailView.as_view(),      name="meat_sale_detail"),
    path("meat/lines/<int:pk>/update/", views.MeatSaleLineUpdateView.as_view(), name="meat_saleline_update"),
    path("meat/lines/<int:pk>/delete/", views.MeatSaleLineDeleteView.as_view(), name="meat_saleline_delete"),
    path("meat/<int:meat_sale_pk>/lines/add/", views.MeatSaleLineCreateView.as_view(), name="meat_saleline_create"),

    # Sale lines (operated from the sale detail page)
    path("<int:sale_pk>/lines/add/", views.SaleLineCreateView.as_view(), name="saleline_create"),
    path("lines/<int:pk>/delete/",   views.SaleLineDeleteView.as_view(), name="saleline_delete"),

    # Adjustments
    path("adjustments/",            views.AdjustmentListView.as_view(),  name="adjustment_list"),
    path("adjustments/new/",        views.AdjustmentCreateView.as_view(), name="adjustment_create"),
]
