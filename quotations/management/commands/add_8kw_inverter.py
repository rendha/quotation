"""
python manage.py add_8kw_inverter            # adds (or updates) the 8 kW dual-MPPT inverter at Rs 58,300
python manage.py add_8kw_inverter --rate 59000

Creates two inverter products so an 8 kW plant finds its inverter whatever the phase:
    POLYCAB 8KW 3PH DUAL   and   POLYCAB 8KW 1PH DUAL
Safe to run again: an existing row is updated, never duplicated.  Untick Active in Admin for the one you do not sell.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from quotations.models import Product


class Command(BaseCommand):
    help = "Add the 8 kW dual-MPPT inverter (Rs 58,300) to the rate sheet."

    def add_arguments(self, parser):
        parser.add_argument("--rate", default="58300", help="price of the inverter (default 58300)")

    def handle(self, *args, **options):
        rate = Decimal(options["rate"])
        for token, phase_text in (("3PH", "THREE phase"), ("1PH", "SINGLE phase")):
            name = "POLYCAB 8KW %s DUAL" % token
            fields = {"make": "POLYCAB", "unit": "Nos", "rate": rate, "inverter_capacity": Decimal("8"), "is_active": True,
                      "specification": "8 KW %s on-grid inverter, 2 MPPT" % phase_text}
            product = Product.objects.filter(category="inverter", name__iexact=name).first()
            if product is None:
                Product.objects.create(category="inverter", name=name, **fields)
                self.stdout.write("  + created %s  Rs %s" % (name, rate))
            else:
                for key, value in fields.items():
                    if key == "specification" and (product.specification or "").strip():
                        continue                                    # never overwrite a specification typed in Admin
                    setattr(product, key, value)
                product.save()
                self.stdout.write("  ~ updated %s  Rs %s" % (name, rate))
        self.stdout.write(self.style.SUCCESS("Done."))
