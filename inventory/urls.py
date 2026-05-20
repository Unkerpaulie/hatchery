"""Inventory URL routes.

All paths here are mounted under /inventory/ by core.urls.
"""

from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    # ---- Suppliers --------------------------------------------------------
    path("suppliers/",                  views.SupplierListView.as_view(),          name="supplier_list"),
    path("suppliers/new/",              views.SupplierCreateView.as_view(),        name="supplier_create"),
    path("suppliers/<int:pk>/",         views.SupplierDetailView.as_view(),        name="supplier_detail"),
    path("suppliers/<int:pk>/edit/",    views.SupplierUpdateView.as_view(),        name="supplier_update"),
    path("suppliers/<int:pk>/delete/",  views.SupplierDeleteView.as_view(),        name="supplier_delete"),

    # ---- Batches ----------------------------------------------------------
    path("batches/",                    views.BatchListView.as_view(),             name="batch_list"),
    path("batches/new/",                views.BatchCreateView.as_view(),           name="batch_create"),
    path("batches/<int:pk>/",           views.BatchDetailView.as_view(),           name="batch_detail"),
    path("batches/<int:pk>/begin-incubation/",
                                        views.BatchBeginIncubationView.as_view(),  name="batch_begin_incubation"),
    path("batches/<int:pk>/complete/",  views.BatchCompleteView.as_view(),         name="batch_complete"),

    # ---- Hatch records ----------------------------------------------------
    path("batches/<int:batch_pk>/hatches/new/",
                                        views.HatchCreateView.as_view(),           name="hatch_create"),
    path("hatches/<int:pk>/edit/",      views.HatchUpdateView.as_view(),           name="hatch_update"),
    path("hatches/<int:pk>/delete/",    views.HatchDeleteView.as_view(),           name="hatch_delete"),

    # ---- Expenses ---------------------------------------------------------
    path("expenses/",                   views.ExpenseListView.as_view(),           name="expense_list"),
    path("expenses/new/",               views.ExpenseCreateView.as_view(),         name="expense_create"),
    path("expenses/<int:pk>/edit/",     views.ExpenseUpdateView.as_view(),         name="expense_update"),
    path("expenses/<int:pk>/delete/",   views.ExpenseDeleteView.as_view(),         name="expense_delete"),
]
