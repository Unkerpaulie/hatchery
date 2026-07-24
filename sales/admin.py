from django.contrib import admin

from .models import Adjustment, Customer, MeatSale, MeatSaleLine, Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_1", "email")
    search_fields = ("name", "email")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        """Customer records are intentionally protected from deletion (rules.md)."""
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "customer", "date", "status")
    list_select_related = ("customer",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    inlines = [SaleLineInline]


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ("sale", "batch", "quantity", "unit_price", "line_total_display")
    list_select_related = ("sale", "batch")
    readonly_fields = ("created_by", "updated_by")

    @admin.display(description="Line total")
    def line_total_display(self, obj):
        return f"${obj.line_total:,.2f}"


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ("batch", "date", "quantity", "adjustment_type", "reason")
    list_select_related = ("batch",)
    readonly_fields = ("created_by", "updated_by", "created_at")


class MeatSaleLineInline(admin.TabularInline):
    model = MeatSaleLine
    extra = 0
    readonly_fields = ("weight_lb",)


@admin.register(MeatSale)
class MeatSaleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "batch", "date", "price_per_lb")
    list_select_related = ("batch",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    inlines = [MeatSaleLineInline]


@admin.register(MeatSaleLine)
class MeatSaleLineAdmin(admin.ModelAdmin):
    list_display = ("meat_sale", "weight_lb")
    list_select_related = ("meat_sale__batch",)
