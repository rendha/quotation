from django.contrib import admin
from .models import (
    Product,
    Quotation,
    QuotationItem,
    SolarPackage,
    SolarPackageItem,
    PackageOptionRule,
    PanelOption,
    PaymentDetails
)

# Register your models here.
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'make',
        'unit',
        'rate',
        'tax_percent',
        'is_active',
    )

    list_filter = (
        'category',
        'is_active',
    )

    search_fields = (
        'name',
        'make',
        'specification',
    )

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = (
        'offer_no',
        'business_name',
        'location',
        'capacity',
        'date',
        'validity_days',
    )

    search_fields = (
        'offer_no',
        'buisness_name',
        'location',
    )

    list_filter = (
        'category',
        'date',
    )

@admin.register(QuotationItem)
class QuotationItemAdmin(admin.ModelAdmin):
    list_display = (
        'quotation',
        'description',
        'quantity',
        'make',
        'rate',
        'tax_percent',
    )  

    search_fields = (
        'description',
        'make',
    )



@admin.register(SolarPackage)
class SolarPackageAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'sheet_name',
        'capacity',
        'phase',
        'is_active',
    )

    list_filter = (
        'capacity',
        'phase',
        'is_active',
    )

    search_fields = (
        'name',
        'sheet_name',
    )


@admin.register(SolarPackageItem)
class SolarPackageItemAdmin(admin.ModelAdmin):

    list_display = (
        'solar_package',
        'product_name',
        'category',
        'make',
        'quantity',
        'rate',
        'tax_percent',
    )

    list_filter = (
        'category',
        'tax_percent',
    )

    search_fields = (
        'product_name',
        'make',
    )


@admin.register(PanelOption)
class PanelOptionAdmin(admin.ModelAdmin):

    list_display = (
        "company",
        "panel_type",
        "dcr_status",
        "wattage",
        "rate_per_watt",
        "tax_percent",
        "is_active",
    )

    list_filter = (
        "company",
        "dcr_status",
        "panel_type",
        "is_active",
    )

    search_fields = (
        "company",
        "panel_type",
    )

    ordering = (
        "company",
        "dcr_status",
        "wattage",
    )

@admin.register(PaymentDetails)
class PaymentDetailsAdmin(admin.ModelAdmin):
    list_display = ("beneficiary_name", "bank_name", "account_number", "ifsc")

    def has_add_permission(self, request):
        return not PaymentDetails.objects.exists()    