"""Hybrid: the Solis hybrid inverters (5 and 10 years warranty) and the Enprimo lithium battery (rates before GST).  An existing product is never changed."""
from decimal import Decimal

from django.db import migrations

SOLIS = [  # (kW, phase, rate with 5 years warranty, rate with 10 years warranty)
    ("3", "1PH", "68999", "79349"),
    ("5", "1PH", "77999", "89699"),
    ("8", "3PH", "170399", "195959"),
    ("10", "3PH", "183799", "211369"),
    ("15", "3PH", "220199", "253229"),
    ("30", "3PH", "399799", "459769"),
    ("50", "3PH", "490000", "563500"),
]
ENPRIMO = [("5", "65000"), ("10", "74750")]       # years of warranty, rate


def add_products(apps, schema_editor):
    Product = apps.get_model("quotations", "Product")

    def add(name, make, category, rate, capacity=None, specification=""):
        if Product.objects.filter(category=category, name__iexact=name).exists():
            return
        Product.objects.create(name=name, category=category, make=make, unit="Nos", rate=Decimal(rate),
                               inverter_capacity=Decimal(capacity) if capacity else None, is_active=True, specification=specification)

    for kw, phase, rate5, rate10 in SOLIS:
        for years, rate in (("5", rate5), ("10", rate10)):
            add("SOLIS HYBRID %sKW %s - %s YEARS WARRANTY" % (kw, phase, years), "SOLIS", "inverter", rate, kw,
                "%s KW %s phase hybrid inverter, %s years warranty" % (kw, "single" if phase == "1PH" else "three", years))
    for years, rate in ENPRIMO:
        add("ENPRIMO LITHIUM BATTERY 6000 CYCLE - %s YEARS WARRANTY" % years, "ENPRIMO", "battery", rate, None,
            "Enprimo lithium battery, 6000 cycles, %s years warranty" % years)


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0025_hybrid_battery_and_inverters"),
    ]

    operations = [
        migrations.RunPython(add_products, migrations.RunPython.noop),
    ]
