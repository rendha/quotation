"""
python manage.py set_panel_rates --dry-run      show what would change, save nothing
python manage.py set_panel_rates                update the Panel options

Sets the rate per watt of the DCR panels to the current price list (the table below).
A panel that is not in the database yet is added.  Panels that are not in the table (for example the Waaree 570 W)
are left alone.  Safe to run again: a second run finds everything unchanged.

To change a rate later, edit the table and run the command again, or change it in Admin > Panel options.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from quotations.models import PanelOption

DCR = "dcr"

# (company, technology, wattages, rate per watt)
PANEL_RATES = [
    ("Adani", "BIFACIAL", (545, 550, 555), "26.5"),
    ("Adani", "TOPCON", (600, 610, 620, 630), "27.5"),
    ("WAREE", "TOPCON", (600, 610, 620, 630), "28.5"),
    ("EMVEE", "TOPCON", (565, 580, 610), "25"),
]


def plain(value):
    return format(Decimal(value).normalize(), "f")


class Command(BaseCommand):
    help = "Set the rate per watt of the DCR panels to the current price list."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change and save nothing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        counts = {"updated": 0, "created": 0, "unchanged": 0}

        for company, technology, wattages, rate in PANEL_RATES:
            new_rate = Decimal(rate)
            for watts in wattages:
                matches = list(PanelOption.objects.filter(
                    company__iexact=company, panel_type__iexact=technology, dcr_status=DCR, wattage=watts))

                if not matches:
                    if not dry:
                        PanelOption.objects.create(company=company, panel_type=technology, dcr_status=DCR,
                                                   wattage=watts, rate_per_watt=new_rate, is_active=True)
                    counts["created"] += 1
                    self.stdout.write("  + %-6s %-9s %3d W   new, Rs %s per watt" % (company, technology, watts, plain(new_rate)))
                    continue

                for panel in matches:
                    if panel.rate_per_watt == new_rate and panel.is_active:
                        counts["unchanged"] += 1
                        continue
                    self.stdout.write("  ~ %-6s %-9s %3d W   Rs %s  ->  Rs %s per watt"
                                      % (company, technology, watts, plain(panel.rate_per_watt), plain(new_rate)))
                    if not dry:
                        panel.rate_per_watt = new_rate
                        panel.is_active = True
                        panel.save()
                    counts["updated"] += 1

        self.stdout.write("")
        self.stdout.write("Panels: %(updated)d updated, %(created)d added, %(unchanged)d already correct" % counts)
        self.stdout.write("DRY RUN - nothing was saved. Run again without --dry-run to save." if dry else "Done. Open Admin > Panel options to see the rates.")