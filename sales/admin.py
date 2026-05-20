from django.contrib import admin

from .models import Adjustment, Customer, Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_1", "email")
    search_fields = ("name", "email")

    def has_delete_permission(self, request, obj=None):
        """Customer records are intentionally protected from deletion (rules.md)."""
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "customer", "date", "total_revenue_display", "total_quantity")
    list_select_related = ("customer",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [SaleLineInline]

    @admin.display(description="Revenue")
    def total_revenue_display(self, obj):
        return f"${obj.total_revenue:,.2f}"


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ("sale", "batch", "quantity", "unit_price", "line_total_display")
    list_select_related = ("sale", "batch")

    @admin.display(description="Line total")
    def line_total_display(self, obj):
        return f"${obj.line_total:,.2f}"


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ("batch", "date", "quantity", "reason")
    list_select_related = ("batch",)
    readonly_fields = ("created_at",)
