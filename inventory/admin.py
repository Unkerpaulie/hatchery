from django.contrib import admin

from .models import Batch, Expense, Hatch, Supplier


class HatchInline(admin.TabularInline):
    model = Hatch
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("business_name", "contact_name", "phone_1", "email")
    search_fields = ("business_name", "contact_name", "email")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "supplier", "purchase_date", "quantity", "status")
    list_filter = ("status",)
    search_fields = ("supplier__business_name",)
    readonly_fields = ("incubation_start_date", "status", "created_at", "updated_at")
    inlines = [HatchInline]


@admin.register(Hatch)
class HatchAdmin(admin.ModelAdmin):
    list_display = ("batch", "date", "quantity")
    list_filter = ("date",)
    readonly_fields = ("created_at",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "description", "amount")
    list_filter = ("category",)
    search_fields = ("description",)
    readonly_fields = ("created_at", "updated_at")
