"""Enphase microinverters: the IQ8P (7,700) and IQ8HC (8,500) and the parts of the Enphase sheet
(rates before GST).  An existing product is never changed."""
from decimal import Decimal

from django.db import migrations

PRODUCTS = [
    # (name, category, rate, specification)
    ("ENPHASE IQ8P-72-INT MICRO", "inverter", "7700", "Enphase IQ8P microinverter, one per panel (TOPCon and bifacial panels)"),
    ("ENPHASE IQ8HC MICRO", "inverter", "8500", "Enphase IQ8HC microinverter, one per panel (bifacial panels)"),
    ("ENPHASE Q CABLE 1.3M", "other", "600", "Enphase Q cable 1.3 m, one per panel"),
    ("ENPHASE Q TERM", "other", "730", "Enphase Q terminator cap, one per branch"),
    ("ENPHASE CT 200 SPLIT", "other", "1500", "Enphase CT 200 Split current transformer"),
    ("ENPHASE IQ RELAY 3P", "other", "5400", "Enphase IQ Relay three phase"),
    ("ENPHASE IQ RELAY 1P", "other", "5400", "Enphase IQ Relay single phase (RATE TO BE CONFIRMED: the three-phase price was used)"),
    ("ENPHASE ENVOY S", "other", "12500", "Enphase Envoy S gateway"),
]


def add_products(apps, schema_editor):
    Product = apps.get_model("quotations", "Product")
    for name, category, rate, specification in PRODUCTS:
        if Product.objects.filter(category=category, name__iexact=name).exists():
            continue
        Product.objects.create(name=name, category=category, make="ENPHASE", unit="Nos", rate=Decimal(rate), is_active=True,
                               specification=specification)


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0026_add_solis_enprimo"),
    ]

    operations = [
        migrations.RunPython(add_products, migrations.RunPython.noop),
    ]
