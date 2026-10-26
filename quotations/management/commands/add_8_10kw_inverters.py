"""
python manage.py add_8_10kw_inverters

Adds (or updates) the THREE-PHASE POLYCAB 8 kW and 10 kW inverters, single MPPT and dual MPPT:
      8 kW:  single MPPT Rs 44,604    dual MPPT Rs 50,328
     10 kW:  single MPPT Rs 45,144    dual MPPT Rs 50,328
Names:  POLYCAB 8KW 3PH SINGLE / DUAL  and  POLYCAB 10KW 3PH SINGLE / DUAL.  (The PDF prints 1 or 2 MPPT trackers from the name.)
Above 5 kW only three-phase inverters are sold, so any 1PH inverter bigger than 5 kW is switched off (Active unticked).
Safe to run again: an existing row is updated, never duplicated.
Other prices:  python manage.py add_8_10kw_inverters --kw8-single 45000 --kw8-dual 51000 --kw10-single 46000 --kw10-dual 52000
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from quotations.models import Product


class Command(BaseCommand):
    help = "Add / update the 8 kW and 10 kW three-phase inverters (single and dual MPPT)."

    def add_arguments(self, parser):
        parser.add_argument("--kw8-single", default="44604")
        parser.add_argument("--kw8-dual", default="50328")
        parser.add_argument("--kw10-single", default="45144")
        parser.add_argument("--kw10-dual", default="50328")

    def handle(self, *args, **options):
        rates = {(8, "SINGLE"): options["kw8_single"], (8, "DUAL"): options["kw8_dual"],
                 (10, "SINGLE"): options["kw10_single"], (10, "DUAL"): options["kw10_dual"]}
        for (kw, mppt), raw in rates.items():
            rate = Decimal(raw)
            name = "POLYCAB %dKW 3PH %s" % (kw, mppt)
            fields = {"make": "POLYCAB", "unit": "Nos", "rate": rate, "inverter_capacity": Decimal(kw), "is_active": True,
                      "specification": "%d KW THREE phase on-grid inverter, %d MPPT" % (kw, 2 if mppt == "DUAL" else 1)}
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
        off = Product.objects.filter(category="inverter", name__icontains="1PH", inverter_capacity__gt=5, is_active=True).update(is_active=False)
        if off:
            self.stdout.write("  - switched off %d single-phase inverter(s) above 5 kW" % off)
        self.stdout.write(self.style.SUCCESS("Done."))
