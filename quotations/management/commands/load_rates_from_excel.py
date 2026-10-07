"""
python manage.py load_rates_from_excel "C:\\path\\QOUTATION_WORK_OUT.xlsx" --dry-run
python manage.py load_rates_from_excel "C:\\path\\QOUTATION_WORK_OUT.xlsx" --replace-old

Fills the admin tables from the rate sheet:
    Panel options  <- 'SOLAR PANEL MOD'  (all loaded as DCR - the sheet only contains DCR panels)
    Products       <- inverters, ACDB, DCDB, meter box, DC cable, AC wire, UG cable, earthing cable,
                      earth rod, lightning arrestor, energy meter, net meter

NOT loaded: the BOS table (ignored on purpose) and the 'Non Taxable Particular' amounts (they are fields
on the quotation, not tables).  Nothing is ever deleted.

Safe to run again: existing rows are matched and updated (rate, make, unit, active), never duplicated, and a
specification you typed in Admin is never overwritten.  --dry-run shows exactly what would change and saves nothing.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quotations.excel_rates import parse_workbook, plain
from quotations.models import PanelOption, Product


# Categories where the sheet clearly supersedes whatever an earlier import left behind
REPLACED_CATEGORIES = ["inverter", "dc_cable", "ac_wire"]


class Command(BaseCommand):
    help = "Load panels, inverters and component rates from the Excel rate sheet into the admin tables."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", help="Path to QOUTATION_WORK_OUT.xlsx")
        parser.add_argument(
            "--panels", default="dcr", choices=["dcr", "non_dcr", "both"],
            help="Type given to the panels. The sheet only contains DCR panels, so the default is dcr. "
                 "(non_dcr / both are there for later.) You can change a panel's type in Admin at any time.")
        parser.add_argument(
            "--replace-old", action="store_true",
            help="After loading, HIDE (untick Active - nothing is deleted) the older rows in the categories the sheet "
                 "replaces: inverter, dc_cable and ac_wire. Use it when those categories already hold rows from an earlier import. "
                 "Rows can be switched back on in Admin.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would happen and save nothing.")

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        try:
            data = parse_workbook(options["excel_path"])
        except FileNotFoundError:
            raise CommandError("File not found: %s" % options["excel_path"])

        if not isinstance(data, dict):
            raise CommandError(
                "quotations/excel_rates.py is incomplete (parse_workbook returned nothing). It was probably cut off "
                "when it was copied: the file must end with the line 'return out' and be about 211 lines long. "
                "Copy it again from loader_fix.zip instead of pasting.")

        statuses = ["dcr", "non_dcr"] if options["panels"] == "both" else [options["panels"]]
        dry = options["dry_run"]
        counts = {"panels": {"created": 0, "updated": 0, "unchanged": 0},
                  "products": {"created": 0, "updated": 0, "unchanged": 0}}

        with transaction.atomic():
            for panel in data["panels"]:
                for status in statuses:
                    self._save_panel(panel, status, counts["panels"])
            loaded = []
            for product in data["products"]:
                loaded.append(self._save_product(product, counts["products"]))
            hidden = self._hide_old(loaded) if options["replace_old"] else []
            if dry:
                transaction.set_rollback(True)

        for message in data["skipped"]:
            self.stdout.write("  skipped: %s" % message)

        self.stdout.write("")
        self.stdout.write("Panel options : %(created)d created, %(updated)d updated, %(unchanged)d unchanged" % counts["panels"])
        self.stdout.write("Products       : %(created)d created, %(updated)d updated, %(unchanged)d unchanged" % counts["products"])
        if options["replace_old"]:
            self.stdout.write("Older rows hidden (Active unticked, not deleted): %d" % len(hidden))
        self.stdout.write("BOS table      : ignored (%d rows)" % data["bos_ignored_rows"])
        if data["charges"]:
            self.stdout.write("Not loaded (they are quotation fields, not tables): " +
                              ", ".join("%s %s" % (c["item"], plain(c["rate"])) for c in data["charges"]))
        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN - nothing was saved. Run again without --dry-run to save."))
        else:
            self.stdout.write(self.style.SUCCESS("Done. Open Admin to see the rows."))

    # ------------------------------------------------------------------
    def _save_panel(self, p, status, counts):
        existing = PanelOption.objects.filter(
            company__iexact=p["company"], panel_type__iexact=p["panel_type"], dcr_status=status, wattage=p["wattage"]).first()

        if existing is None:
            PanelOption.objects.create(company=p["company"], panel_type=p["panel_type"], dcr_status=status,
                                       wattage=p["wattage"], rate_per_watt=p["rate_per_watt"], is_active=True)
            counts["created"] += 1
            self.stdout.write("  + panel   %s %s %sW %s  Rs %s/W" % (p["company"], p["panel_type"], plain(p["wattage"]), status, p["rate_per_watt"]))
            return

        changes = {}
        if existing.rate_per_watt != p["rate_per_watt"]:
            changes["rate_per_watt"] = p["rate_per_watt"]
        if not existing.is_active:
            changes["is_active"] = True
        if changes:
            for field, value in changes.items():
                setattr(existing, field, value)
            existing.save()
            counts["updated"] += 1
            self.stdout.write("  ~ panel   %s %s %sW %s  updated %s" % (p["company"], p["panel_type"], plain(p["wattage"]), status, ", ".join(changes)))
        else:
            counts["unchanged"] += 1

    def _save_product(self, p, counts):
        existing = Product.objects.filter(category=p["category"], name__iexact=p["name"]).first()

        if existing is None:
            created = Product.objects.create(
                name=p["name"], category=p["category"], make=p["make"], specification=p["specification"], unit=p["unit"],
                rate=p["rate"], inverter_capacity=p.get("inverter_capacity"), is_active=True)
            counts["created"] += 1
            self.stdout.write("  + product %-12s %-40s Rs %s/%s" % (p["category"], p["name"], p["rate"], p["unit"]))
            return created

        wanted = {"make": p["make"], "unit": p["unit"], "rate": p["rate"], "is_active": True}
        if p.get("inverter_capacity") is not None:
            wanted["inverter_capacity"] = p["inverter_capacity"]
        if not (existing.specification or "").strip():          # never overwrite a specification written in Admin
            wanted["specification"] = p["specification"]

        changes = {k: v for k, v in wanted.items() if getattr(existing, k) != v}
        if changes:
            for field, value in changes.items():
                setattr(existing, field, value)
            existing.save()
            counts["updated"] += 1
            self.stdout.write("  ~ product %-12s %-40s updated %s" % (p["category"], p["name"], ", ".join(changes)))
        else:
            counts["unchanged"] += 1
        return existing

    def _hide_old(self, loaded):
        """Untick Active on every other product in the replaced categories.  Nothing is deleted."""
        keep = {product.pk for product in loaded}
        hidden = []
        for old in Product.objects.filter(category__in=REPLACED_CATEGORIES, is_active=True):
            if old.pk in keep:
                continue
            old.is_active = False
            old.save()
            hidden.append(old)
            self.stdout.write("  - hidden  %-12s %-40s Rs %s" % (old.category, old.name, old.rate))
        return hidden