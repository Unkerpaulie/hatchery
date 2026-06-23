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
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "supplier", "breed", "purchase_date", "purchased_as", "initial_quantity", "status")
    list_filter = ("status", "purchased_as")
    search_fields = ("supplier__business_name", "breed")
    readonly_fields = (
        "purchased_as", "age_at_purchase", "incubation_start_date",
        "day_1_date", "status", "created_by", "updated_by", "created_at", "updated_at",
    )
    inlines = [HatchInline]


@admin.register(Hatch)
class HatchAdmin(admin.ModelAdmin):
    list_display = ("batch", "date", "quantity")
    list_filter = ("date",)
    readonly_fields = ("created_by", "updated_by", "created_at")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "description", "amount")
    list_filter = ("category",)
    search_fields = ("description",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
