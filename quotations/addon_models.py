"""Upgrade / add-on quotation: a short quotation (only the items supplied) for an existing customer.
Rates come from the normal rate list (Product).  GST is per item: 5% for panels and inverters, 18% for everything else."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models

GST_LOW = Decimal("5")
GST_HIGH = Decimal("18")
LOW_GST_CATEGORIES = ("module", "inverter")


def default_gst(category):
    return GST_LOW if category in LOW_GST_CATEGORIES else GST_HIGH


def _m(v):
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AddonQuotation(models.Model):
    offer_no = models.CharField(max_length=40, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    customer_name = models.CharField(max_length=200)
    sales_name = models.CharField("Quotation for (sales person)", max_length=200, blank=True)
    location = models.CharField(max_length=100, blank=True)
    validity_days = models.PositiveIntegerField(default=15)
    note = models.CharField(max_length=300, blank=True)

    taxable_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gst_low_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)    # all lines at 5%
    gst_high_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)   # lines at any other %
    calculated_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # taxable + GST
    final_override = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    final_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    margin_drop = models.DecimalField(max_digits=14, decimal_places=2, default=0)       # calculated - final, when final is lower

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Add-on quotation"

    def __str__(self):
        return "%s - %s" % (self.offer_no or self.pk, self.customer_name)

    @property
    def low_margin(self):
        return self.margin_drop > 0

    def recalculate(self, save=True):
        taxable = low = high = Decimal("0")
        for it in self.items.all():
            t = _m(it.quantity * it.rate)
            g = _m(t * it.gst_percent / Decimal("100"))
            taxable += t
            if it.gst_percent == GST_LOW:
                low += g
            else:
                high += g
        self.taxable_total, self.gst_low_amount, self.gst_high_amount = _m(taxable), _m(low), _m(high)
        self.calculated_total = _m(taxable + low + high)
        self.final_total = _m(self.final_override) if self.final_override is not None else self.calculated_total
        self.margin_drop = max(Decimal("0"), self.calculated_total - self.final_total)
        if save:
            self.save()
        return self


class AddonItem(models.Model):
    addon = models.ForeignKey(AddonQuotation, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("quotations.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=300)
    specification = models.TextField(blank=True)
    make = models.CharField(max_length=200, blank=True)
    unit = models.CharField(max_length=50, default="Nos")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)          # base rate, before GST
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)

    class Meta:
        ordering = ["id"]

    @property
    def taxable_value(self):
        return _m(self.quantity * self.rate)

    @property
    def gst_amount(self):
        return _m(self.taxable_value * self.gst_percent / Decimal("100"))

    @property
    def total_value(self):
        return self.taxable_value + self.gst_amount

    def __str__(self):
        return self.description
