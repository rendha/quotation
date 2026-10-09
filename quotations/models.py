from decimal import Decimal

from django.db import models


# =========================================================
# PRODUCT
# =========================================================

class Product(models.Model):

    CATEGORY_CHOICES = [
        ("module", "PV Module"),
        ("inverter", "Inverter"),
        ("structure", "Mounting Structure"),
        ("acdb", "ACDB"),
        ("dcdb", "DCDB"),
        ("ac_wire", "AC Wire"),
        ("dc_cable", "DC Cable"),
        ("energy_meter", "Energy Meter"),
        ("meter_box", "Meter Box"),
        ("ug_cable", "UG Cable"),
        ("net_meter", "Net Meter"),
        ("electrical", "Electrical"),
        ("cable", "Cable"),
        ("earthing", "Earthing"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=200)

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
    )

    make = models.CharField(
        max_length=200,
        blank=True,
    )

    specification = models.TextField(
        blank=True,
    )

    unit = models.CharField(
        max_length=50,
        default="Nos",
    )

    # Base rate entered in admin.
    # GST is NOT calculated here.
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    # Retained for product information / compatibility.
    # NOT used for quotation GST calculation.
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    is_active = models.BooleanField(
        default=True,
    )

    inverter_capacity = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


# =========================================================
# PANEL OPTION
# =========================================================

class PanelOption(models.Model):

    DCR_CHOICES = [
        ("dcr", "DCR - With Subsidy"),
        ("non_dcr", "Non-DCR - Without Subsidy"),
    ]

    company = models.CharField(
        max_length=100,
    )

    panel_type = models.CharField(
        max_length=100,
        blank=True,
    )

    dcr_status = models.CharField(
        max_length=20,
        choices=DCR_CHOICES,
    )

    wattage = models.DecimalField(
        max_digits=7,
        decimal_places=2,
    )

    # Rate entered by admin per watt.
    rate_per_watt = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    # Retained for compatibility/reference.
    # NOT used in final quotation calculation.
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "company",
            "dcr_status",
            "wattage",
        ]

    def __str__(self):
        return (
            f"{self.company} - "
            f"{self.panel_type} - "
            f"{self.wattage}W - "
            f"{self.get_dcr_status_display()}"
        )


# =========================================================
# SOLAR PACKAGE
# =========================================================

class SolarPackage(models.Model):

    name = models.CharField(
        max_length=100,
    )

    sheet_name = models.CharField(
        max_length=100,
        unique=True,
    )

    capacity = models.CharField(
        max_length=50,
    )

    phase = models.CharField(
        max_length=50,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["capacity", "name"]

    def __str__(self):
        return self.name


# =========================================================
# SOLAR PACKAGE ITEM
# =========================================================

class SolarPackageItem(models.Model):

    solar_package = models.ForeignKey(
        SolarPackage,
        on_delete=models.CASCADE,
        related_name="items",
    )

    category = models.CharField(
        max_length=50,
        blank=True,
    )

    product_name = models.CharField(
        max_length=200,
    )

    make = models.CharField(
        max_length=200,
        blank=True,
    )

    # Package quantity.
    #
    # Normally this is 1 for ordinary components.
    # DC cable / AC wire / earth are handled through the
    # quotation's editable quantity fields.
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("1"),
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    # Retained for compatibility/reference.
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    specification = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.solar_package.name} - "
            f"{self.product_name}"
        )


# =========================================================
# PACKAGE OPTION RULE
# =========================================================

class PackageOptionRule(models.Model):

    package = models.ForeignKey(
        SolarPackage,
        on_delete=models.CASCADE,
        related_name="option_rules",
    )

    excel_sheet = models.CharField(
        max_length=100,
    )

    excel_cell = models.CharField(
        max_length=50,
    )

    excel_row = models.PositiveIntegerField()

    field_name = models.CharField(
        max_length=100,
    )

    current_value = models.CharField(
        max_length=500,
        blank=True,
    )

    source_range = models.CharField(
        max_length=500,
        blank=True,
    )

    options = models.JSONField(
        default=list,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "package",
            "excel_row",
        ]

    def __str__(self):
        return (
            f"{self.package} - "
            f"{self.field_name} - "
            f"{self.excel_cell}"
        )


# =========================================================
# STRUCTURE WAGE SETTING
# =========================================================

class StructureWageSetting(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    factor = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
    )

    is_active = models.BooleanField(
        default=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} - {self.factor}"


# =========================================================
# QUOTATION
# =========================================================

class Quotation(models.Model):

    # =====================================================
    # BASIC CUSTOMER INFORMATION
    # =====================================================

    offer_no = models.CharField(
        max_length=100,
        unique=True,
    )

    business_name = models.CharField(
        max_length=200,
    )

    customer_name = models.CharField(
        max_length=200,
        blank=True,
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    location = models.CharField(
        max_length=200,
    )

    address = models.TextField(
        blank=True,
    )

    date = models.DateField()

    validity_days = models.PositiveIntegerField(
        default=15,
    )

    # =====================================================
    # SYSTEM INFORMATION
    # =====================================================

    PHASE_CHOICES = [
        ("single", "Single Phase"),
        ("three", "Three Phase"),
    ]

    SYSTEM_TYPE_CHOICES = [
        ("on_grid", "On-Grid"),
        ("off_grid", "Off-Grid"),
        ("hybrid", "Hybrid"),
    ]

    STRUCTURE_TYPE_CHOICES = [
        ("roof", "Roof Mounted"),
        ("gp", "GP"),
        ("gi", "GI"),
    ]

    DCR_CHOICES = [
        ("dcr", "DCR"),
        ("non_dcr", "Non-DCR"),
    ]

    phase = models.CharField(
        max_length=20,
        choices=PHASE_CHOICES,
        default="single",
    )

    system_type = models.CharField(
        max_length=20,
        choices=SYSTEM_TYPE_CHOICES,
        default="on_grid",
    )

    system_size = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
    )

    panel_dcr_status = models.CharField(
        max_length=20,
        choices=DCR_CHOICES,
        default="dcr",
    )

    structure_type = models.CharField(
        max_length=20,
        choices=STRUCTURE_TYPE_CHOICES,
        default="roof",
    )

    structure_feet = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # =====================================================
    # PACKAGE
    # =====================================================

    category = models.CharField(
        max_length=100,
        default="On-Grid",
    )

    capacity = models.CharField(
        max_length=50,
        blank=True,
    )

    solar_package = models.ForeignKey(
        SolarPackage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quotations",
    )

    # =====================================================
    # PANEL
    # =====================================================

    panel_option = models.ForeignKey(
        PanelOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quotations",
    )

    # Automatically calculated from system size and panel
    # wattage, but the user can manually change it.
    panel_quantity = models.PositiveIntegerField(
        default=0,    
    )

    panel_quantity_manual = models.PositiveIntegerField(
    null=True, blank=True)

    panel_total_watt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    panel_rate_per_watt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    panel_base_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # Kept for compatibility.
    # Individual panel GST is NOT calculated.
    panel_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    panel_tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    panel_total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # =====================================================
    # INVERTER
    # =====================================================

    inverter_kw = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    inverter_type = models.CharField(
        max_length=100,
        blank=True,
    )

    inverter_make = models.CharField(
        max_length=200,
        blank=True,
    )

    inverter_model = models.CharField(
        max_length=200,
        blank=True,
    )

    inverter_rate = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    inverter_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    inverter_tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    inverter_total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # =====================================================
    # ELECTRICAL / COMPONENT SELECTIONS
    # =====================================================

    # -----------------------------------------------------
    # DC CABLE
    # -----------------------------------------------------

    dc_cable = models.CharField(
        max_length=200,
        blank=True,
    )

    # ONLY THIS COMPONENT HAS AN EDITABLE QUANTITY.
    dc_cable_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("30"),
    )

    # -----------------------------------------------------
    # AC WIRE
    # -----------------------------------------------------

    ac_wire = models.CharField(
        max_length=200,
        blank=True,
    )

    # ONLY THIS COMPONENT HAS AN EDITABLE QUANTITY.
    ac_wire_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("20"),
    )

    # -----------------------------------------------------
    # OTHER COMPONENTS
    # -----------------------------------------------------

    # These are automatically treated as quantity = 1.
    # No quantity box is needed in the quotation form.

    acdb = models.CharField(
        max_length=200,
        blank=True,
    )

    dcdb = models.CharField(
        max_length=200,
        blank=True,
    )

    energy_meter = models.CharField(
        max_length=200,
        blank=True,
    )

    meter_box = models.CharField(
        max_length=200,
        blank=True,
    )

    ug_cable = models.CharField(
        max_length=200,
        blank=True,
    )

    net_meter = models.CharField(
        max_length=200,
        blank=True,
    )

    earthing = models.CharField(
        max_length=200,
        blank=True,
    )

    # Earth rod selection.
    earth_rod = models.CharField(
        max_length=100,
        blank=True,
    )

    # ONLY THIS COMPONENT HAS AN EDITABLE QUANTITY.
    earth_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("3"),
    )

    # =====================================================
    # STRUCTURE CALCULATION
    # =====================================================

    structure_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    structure_wage_factor = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("3"),
    )

    structure_wage = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )
    structure_kw_manual = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    structure_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # =====================================================
    # COMPONENT COSTS
    # =====================================================

    component_base_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    component_tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    component_total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # =====================================================
    # NON-TAXABLE / EDITABLE CHARGES
    # =====================================================

    electrical_work = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("9000"),
    )

    structure_work = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("10000"),
    )

    transportation_travel = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("2000"),
    )

    kseb_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    loading_charge = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000"),
    )

    documentation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000"),
    )

    # =====================================================
    # PRICING
    # =====================================================

    # 15 means approximately 15% margin.
    margin_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("15"),
    )

    taxable_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    non_taxable_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    calculated_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    margin_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    calculated_selling_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    gst_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    suggested_quotation_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    final_quotation_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    # =====================================================
    # NOTES
    # =====================================================

    notes = models.TextField(
        blank=True,
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # =====================================================
    # PROPERTIES
    # =====================================================

    @property
    def non_taxable_total(self):
        return (
            self.electrical_work
            + self.structure_work
            + self.transportation_travel
            + self.kseb_fee
            + self.loading_charge
            + self.documentation
        )

    @property
    def quotation_total(self):
        return self.final_quotation_price

    @property
    def panel_description(self):

        if not self.panel_option:
            return ""

        return (
            f"{self.panel_option.company} "
            f"{self.panel_option.wattage}W"
        )

    def __str__(self):
        return self.offer_no


# =========================================================
# QUOTATION ITEM
# =========================================================

class QuotationItem(models.Model):

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    description = models.CharField(
        max_length=500,
    )

    specification = models.TextField(
        blank=True,
    )

    # Ordinary package components are quantity 1.
    #
    # DC cable, AC wire and earth use the dedicated
    # quantity fields on Quotation instead.
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1"),
    )

    make = models.CharField(
        max_length=200,
        blank=True,
    )

    unit = models.CharField(
        max_length=50,
        default="Nos",
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    # Retained for compatibility/reference.
    # NOT used in final GST calculation.
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("9"),
    )

    @property
    def taxable_value(self):
        return (
            self.quantity *
            self.rate
        )

    @property
    def tax_amount(self):
        return Decimal("0")

    @property
    def total_value(self):
        return self.taxable_value

    def __str__(self):
        return self.description


# =========================================================
# OPTIONAL / LEGACY STRUCTURE SETTING
# =========================================================

class StructureSetting(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    base_rate = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )

    per_watt_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    per_feet_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )

    is_active = models.BooleanField(
        default=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentDetails(models.Model):
    """The company bank account printed on the last page of every quotation PDF (Admin > Payment details)."""
    beneficiary_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=40)
    ifsc = models.CharField("IFSC", max_length=20)
    bank_name = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Payment details"
        verbose_name_plural = "Payment details"

    def __str__(self):
        return "%s - %s" % (self.beneficiary_name, self.bank_name)        
