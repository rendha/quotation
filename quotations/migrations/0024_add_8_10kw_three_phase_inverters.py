"""Adds the 8 kW and 10 kW three-phase inverters (single and dual MPPT) when they are missing, and switches off the single-phase 8 kW ones
(above 5 kW only three-phase inverters are sold).  An existing inverter is never changed."""
from decimal import Decimal

from django.db import migrations

RATES = {(8, "SINGLE"): "44604", (8, "DUAL"): "50328", (10, "SINGLE"): "45144", (10, "DUAL"): "50328"}


def add_inverters(apps, schema_editor):
    Product = apps.get_model("quotations", "Product")
    for (kw, mppt), rate in RATES.items():
        name = "POLYCAB %dKW 3PH %s" % (kw, mppt)
        if Product.objects.filter(category="inverter", name__iexact=name).exists():
            continue
        Product.objects.create(category="inverter", name=name, make="POLYCAB", unit="Nos", rate=Decimal(rate),
                               inverter_capacity=Decimal(kw), is_active=True,
                               specification="%d KW THREE phase on-grid inverter, %d MPPT" % (kw, 2 if mppt == "DUAL" else 1))
    Product.objects.filter(category="inverter", name__icontains="1PH", inverter_capacity__gt=5).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0023_panel_both_dcr_non_dcr"),
    ]

    operations = [
        migrations.RunPython(add_inverters, migrations.RunPython.noop),
    ]
