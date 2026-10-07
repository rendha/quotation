from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl

from django.core.management.base import BaseCommand, CommandError
from quotations.models import Product, SolarPackage, SolarPackageItem


PACKAGE_SHEETS = {
    "2KW": {
        "name": "2 kW On-Grid",
        "capacity": "2 kW",
        "phase": "Single Phase",
    },
    "3KW": {
        "name": "3 kW On-Grid",
        "capacity": "3 kW",
        "phase": "Single Phase",
    },
    "4KW ": {
        "name": "4 kW On-Grid",
        "capacity": "4 kW",
        "phase": "Single Phase",
    },
    "5KW": {
        "name": "5 kW On-Grid",
        "capacity": "5 kW",
        "phase": "Single Phase",
    },
    "5KW 3PH": {
        "name": "5 kW On-Grid",
        "capacity": "5 kW",
        "phase": "Three Phase",
    },
    "6KW": {
        "name": "6 kW On-Grid",
        "capacity": "6 kW",
        "phase": "Three Phase",
    },
    "8KW ": {
        "name": "8 kW On-Grid",
        "capacity": "8 kW",
        "phase": "Three Phase",
    },
    "10KW": {
        "name": "10 kW On-Grid",
        "capacity": "10 kW",
        "phase": "Three Phase",
    },
}


def clean(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def decimal_value(value, default=0):
    if value is None or value == "":
        return Decimal(str(default))

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(default))


def percent_value(value):
    """
    Excel stores 12% as 0.12 and 18% as 0.18.
    Our Django model stores them as 12 and 18.
    """
    value = decimal_value(value)

    if value <= 1:
        return value * 100

    return value


class Command(BaseCommand):

    help = "Import products and solar packages from the quotation Excel workbook."

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str,
            help="Path to the Excel workbook",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear imported packages and package items before importing.",
        )

    def handle(self, *args, **options):

        excel_file = Path(options["excel_file"])

        if not excel_file.exists():
            raise CommandError(
                f"Excel file not found: {excel_file}"
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Reading workbook: {excel_file}"
            )
        )

        # data_only=True lets us read the calculated values
        # saved inside the Excel workbook.
        workbook = openpyxl.load_workbook(
            excel_file,
            data_only=True,
        )

        # ---------------------------------------------------------
        # CLEAR PREVIOUS IMPORT
        # ---------------------------------------------------------

        if options["clear"]:

            SolarPackageItem.objects.all().delete()
            SolarPackage.objects.all().delete()

            self.stdout.write(
                self.style.WARNING(
                    "Existing solar package data cleared."
                )
            )

        # ---------------------------------------------------------
        # IMPORT PACKAGE SHEETS
        # ---------------------------------------------------------

        total_items = 0
        total_packages = 0

        for sheet_name, package_info in PACKAGE_SHEETS.items():

            if sheet_name not in workbook.sheetnames:
                self.stdout.write(
                    self.style.WARNING(
                        f"Sheet not found: {sheet_name}"
                    )
                )
                continue

            worksheet = workbook[sheet_name]

            package, created = SolarPackage.objects.update_or_create(
                sheet_name=sheet_name,
                defaults={
                    "name": package_info["name"],
                    "capacity": package_info["capacity"],
                    "phase": package_info["phase"],
                    "is_active": True,
                },
            )

            if created:
                total_packages += 1

            # Remove old items for this package so re-importing
            # doesn't duplicate them.
            package.items.all().delete()

            # Excel structure:
            #
            # A = Sr.No
            # B = CAT
            # C = PRODUCT
            # D = MAKE
            # E = Qty
            # F = RATE
            # G = Tax %
            #
            for row in worksheet.iter_rows(
                min_row=2,
                max_col=10,
                values_only=True,
            ):

                sr_no = row[0]
                category = clean(row[1])
                product_name = clean(row[2])
                make = clean(row[3])
                quantity = row[4]
                rate = row[5]
                tax_percent = row[6]

                # Skip empty rows.
                if not product_name:
                    continue

                # Skip rows without a serial number.
                if sr_no is None:
                    continue

                # Excel tax is stored as 0.12 / 0.18.
                tax_percent = percent_value(tax_percent)

                item = SolarPackageItem.objects.create(
                    solar_package=package,
                    category=category,
                    product_name=product_name,
                    make=make,
                    quantity=decimal_value(quantity),
                    rate=decimal_value(rate),
                    tax_percent=tax_percent,
                )

                total_items += 1

        # ---------------------------------------------------------
        # SUMMARY
        # ---------------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Excel import completed successfully."
            )
        )

        self.stdout.write(
            f"Packages imported: {SolarPackage.objects.count()}"
        )

        self.stdout.write(
            f"Package items imported: {SolarPackageItem.objects.count()}"
        )

        self.stdout.write(
            f"Products currently in database: {Product.objects.count()}"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(
                "Next step: import the PRICE LIST into Product."
            )
        )