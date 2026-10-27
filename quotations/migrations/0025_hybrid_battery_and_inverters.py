"""Hybrid quotations: a battery (type + number) on the quotation, the Battery / Battery MCCB box product categories, and the Polycab hybrid
inverters, battery and MCCB box (rates before GST).  An existing product is never changed."""
from decimal import Decimal

from django.db import migrations, models

HYBRID_INVERTERS = [
    # (kW, phase, model, rate)
    ("3", "1PH", "PHIS-3K0-ESUQ", "73440"),
    ("3.6", "1PH", "PHIS-3K6-ESUQ", "80136"),
    ("5", "1PH", "PHIS-5K0-ESUQ", "84780"),
    ("6", "1PH", "PHIS-6K0-ESUQ", "97956"),
    ("8", "3PH", "PHIT-8K-ETLV", "180830"),
    ("10", "3PH", "PHIT-10K-ETLV", "194205"),
    ("15", "3PH", "PHIT-15K-ETLV", "231441"),
    ("20", "3PH", "PHIT-20K-ETLV", "302275"),
]


def add_products(apps, schema_editor):
    Product = apps.get_model("quotations", "Product")

    def add(name, category, rate, capacity=None, specification=""):
        if Product.objects.filter(category=category, name__iexact=name).exists():
            return
        Product.objects.create(name=name, category=category, make="POLYCAB", unit="Nos", rate=Decimal(rate),
                               inverter_capacity=Decimal(capacity) if capacity else None, is_active=True, specification=specification)

    for kw, phase, model, rate in HYBRID_INVERTERS:
        add("POLYCAB HYBRID %sKW %s %s" % (kw, phase, model), "inverter", rate, kw,
            "%s KW %s phase hybrid inverter (%s)" % (kw, "single" if phase == "1PH" else "three", model))
    add("POLYCAB BATTERY 5KWH PHLVB-5K-AG3", "battery", "90950", None, "5 kWh lithium battery (PHLVB-5K-AG3)")
    if not Product.objects.filter(category="battery_box").exists():
        Product.objects.create(name="BATTERY MCCB BOX 250A 66V", category="battery_box", make="", unit="Nos", rate=Decimal("5500"),
                               is_active=True, specification="Battery MCCB box 250A 66V (rate from the hybrid costing sheet)")


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0024_add_8_10kw_three_phase_inverters"),
    ]

    operations = [
        migrations.AddField(model_name="quotation", name="battery_type", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="quotation", name="battery_quantity", field=models.PositiveIntegerField(default=1)),
        migrations.AlterField(
            model_name="product", name="category",
            field=models.CharField(max_length=50, choices=[
                ("module", "PV Module"), ("inverter", "Inverter"), ("battery", "Battery (hybrid)"), ("battery_box", "Battery MCCB box (hybrid)"),
                ("structure", "Mounting Structure"), ("acdb", "ACDB"), ("dcdb", "DCDB"), ("ac_wire", "AC Wire"), ("dc_cable", "DC Cable"),
                ("energy_meter", "Energy Meter"), ("meter_box", "Meter Box"), ("ug_cable", "UG Cable"), ("net_meter", "Net Meter"),
                ("electrical", "Electrical"), ("cable", "Cable"), ("earthing", "Earthing"), ("other", "Other")]),
        ),
        migrations.RunPython(add_products, migrations.RunPython.noop),
    ]
