"""
python manage.py add_4kw_inverter            # adds (or updates) the 4 kW inverter at Rs 19,415 (POLYCAB, single phase, single MPPT)
python manage.py add_4kw_inverter --rate 20000

Rate sheet (QOUTATION_WORK_OUT.xlsx): POLYCAB 1PH SINGLE 4KW 19,415.
Safe to run again: an existing row is updated, never duplicated.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from quotations.models import Product


class Command(BaseCommand):
    help = "Add the 4 kW inverter (Rs 19,415) to the rate sheet."

    def add_arguments(self, parser):
        parser.add_argument("--rate", default="19415", help="price of the inverter (default 19415)")

    def handle(self, *args, **options):
        rate = Decimal(options["rate"])
        name = "POLYCAB 4KW 1PH SINGLE"
        fields = {"make": "POLYCAB", "unit": "Nos", "rate": rate, "inverter_capacity": Decimal("4"), "is_active": True,
                  "specification": "4 KW SINGLE phase on-grid inverter, 1 MPPT"}
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
