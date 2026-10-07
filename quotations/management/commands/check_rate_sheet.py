"""
python manage.py check_rate_sheet

Checks that every rate the price calculation needs is in the database, using the SAME lookups as the calculation.
If anything is MISSING the quotation shows "no rate found" for it and counts it as Rs 0 - run
    python manage.py load_rates_from_excel "<your excel file>" --replace-old
"""
from django.core.management.base import BaseCommand

from quotations.calculations import rate_sheet_report


class Command(BaseCommand):
    help = "Check that the Excel rates the quotation needs are in the Products table."

    def handle(self, *args, **options):
        missing = 0
        for label, product in rate_sheet_report():
            if product is None:
                missing += 1
                self.stdout.write(self.style.ERROR("  MISSING  %s" % label))
            else:
                self.stdout.write("  ok       %-34s -> %s  (Rs %s)" % (label, product.name, product.rate))
        self.stdout.write("")
        if missing:
            self.stdout.write(self.style.ERROR(
                "%d rate(s) missing. Run:  python manage.py load_rates_from_excel \"<your excel file>\" --replace-old" % missing))
        else:
            self.stdout.write(self.style.SUCCESS("All the rates the calculation needs are in the database."))