import re
import zipfile
import xml.etree.ElementTree as ET

from django.core.management.base import BaseCommand

from quotations.models import SolarPackage, PackageOptionRule


X14_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM_NS = "http://schemas.microsoft.com/office/excel/2006/main"

NS = {
    "x14": X14_NS,
    "xm": XM_NS,
}


class Command(BaseCommand):
    help = (
        "Import Excel blue-cell dropdown/data-validation "
        "configuration into PackageOptionRule."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str,
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing imported dropdown rules first.",
        )

    def handle(self, *args, **options):
        excel_file = options["excel_file"]

        if options["clear"]:
            PackageOptionRule.objects.all().delete()

            self.stdout.write(
                self.style.WARNING(
                    "Existing dropdown rules cleared."
                )
            )

        self.stdout.write(
            f"Reading workbook: {excel_file}"
        )

        with zipfile.ZipFile(
            excel_file,
            "r"
        ) as workbook_zip:

            # Load Excel shared strings first.
            self.shared_strings = (
                self.load_shared_strings(
                    workbook_zip
                )
            )

            workbook_xml = ET.fromstring(
                workbook_zip.read(
                    "xl/workbook.xml"
                )
            )

            relationships_xml = ET.fromstring(
                workbook_zip.read(
                    "xl/_rels/workbook.xml.rels"
                )
            )

            rel_namespace = (
                "http://schemas.openxmlformats.org/"
                "officeDocument/2006/relationships"
            )

            rel_map = {}

            for rel in relationships_xml:
                rel_map[
                    rel.attrib["Id"]
                ] = rel.attrib["Target"]

            workbook_namespace = (
                "http://schemas.openxmlformats.org/"
                "spreadsheetml/2006/main"
            )

            sheet_nodes = workbook_xml.find(
                f"{{{workbook_namespace}}}sheets"
            )

            sheets = []

            for sheet in sheet_nodes:

                name = sheet.attrib["name"]

                relationship_id = sheet.attrib[
                    f"{{{rel_namespace}}}id"
                ]

                target = rel_map[
                    relationship_id
                ]

                if target.startswith("/"):
                    target = target[1:]
                else:
                    target = (
                        "xl/"
                        + target.lstrip("/")
                    )

                sheets.append(
                    (
                        name,
                        target,
                    )
                )

            imported = 0
            skipped = 0

            for sheet_name, sheet_path in sheets:

                if sheet_name.strip().upper() in {
                    "SUMMARY",
                    "PRICE LIST",
                }:
                    continue

                self.stdout.write(
                    f"\nProcessing sheet: {sheet_name}"
                )

                try:
                    package = self.find_package(
                        sheet_name
                    )

                except SolarPackage.DoesNotExist:

                    self.stdout.write(
                        self.style.WARNING(
                            f"No SolarPackage found for "
                            f"sheet '{sheet_name}'. Skipping."
                        )
                    )

                    skipped += 1
                    continue

                xml_data = workbook_zip.read(
                    sheet_path
                )

                root = ET.fromstring(
                    xml_data
                )

                validations = root.findall(
                    f".//{{{X14_NS}}}dataValidation"
                )

                self.stdout.write(
                    f"  Dropdown rules found: "
                    f"{len(validations)}"
                )

                for validation in validations:

                    sqref_node = validation.find(
                        f"{{{XM_NS}}}sqref"
                    )

                    formula_node = validation.find(
                        f"{{{X14_NS}}}formula1/"
                        f"{{{XM_NS}}}f"
                    )

                    if sqref_node is None:
                        skipped += 1
                        continue

                    sqref = (
                        sqref_node.text
                        or ""
                    ).strip()

                    source_range = ""

                    if formula_node is not None:
                        source_range = (
                            formula_node.text
                            or ""
                        ).strip()

                    cells = self.expand_sqref(
                        sqref
                    )

                    for cell in cells:

                        row_number = (
                            self.get_row_number(
                                cell
                            )
                        )

                        current_value = (
                            self.get_cell_value(
                                root,
                                cell,
                            )
                        )

                        field_name = (
                            self.get_field_name(
                                root,
                                row_number,
                            )
                        )

                        option_values = (
                            self.get_options_from_source(
                                workbook_zip,
                                source_range,
                            )
                        )

                        PackageOptionRule.objects.update_or_create(
                            package=package,
                            excel_sheet=sheet_name,
                            excel_cell=cell,
                            defaults={
                                "excel_row": row_number,
                                "field_name": field_name,
                                "current_value": (
                                    current_value or ""
                                ),
                                "source_range": source_range,
                                "options": option_values,
                                "is_active": True,
                            },
                        )

                        imported += 1

        self.stdout.write(
            "\n"
            + self.style.SUCCESS(
                "Excel dropdown import completed."
            )
        )

        self.stdout.write(
            f"Rules imported/updated: {imported}"
        )

        self.stdout.write(
            f"Rows skipped: {skipped}"
        )

    # ---------------------------------------------------------
    # PACKAGE MATCHING
    # ---------------------------------------------------------

    def find_package(self, sheet_name):

        normalized = (
            sheet_name.strip().upper()
        )

        if normalized.endswith(" 3PH"):

            capacity = (
                normalized
                .replace(" 3PH", "")
                .strip()
            )

            phase = "Three Phase"

        else:

            capacity = normalized.strip()

            phase = "Single Phase"

            if capacity in {
                "6KW",
                "8KW",
                "10KW",
            }:
                phase = "Three Phase"

        if capacity.endswith("KW"):

            number = (
                capacity[:-2]
                .strip()
            )

            capacity = f"{number} kW"

        return SolarPackage.objects.get(
            capacity__iexact=capacity,
            phase__iexact=phase,
        )

    # ---------------------------------------------------------
    # EXCEL SHARED STRINGS
    # ---------------------------------------------------------

    def load_shared_strings(
        self,
        workbook_zip,
    ):

        path = "xl/sharedStrings.xml"

        if path not in workbook_zip.namelist():
            return []

        root = ET.fromstring(
            workbook_zip.read(path)
        )

        strings = []

        for item in root.findall(
            "{*}si"
        ):

            parts = []

            for text_node in item.findall(
                ".//{*}t"
            ):

                parts.append(
                    text_node.text or ""
                )

            strings.append(
                "".join(parts)
            )

        return strings

    # ---------------------------------------------------------
    # CELL VALUE
    # ---------------------------------------------------------

    def get_cell_value(
        self,
        root,
        cell_reference,
    ):

        cell = root.find(
            f".//{{*}}c[@r='{cell_reference}']"
        )

        if cell is None:
            return ""

        cell_type = cell.attrib.get(
            "t"
        )

        # Inline string
        if cell_type == "inlineStr":

            text_nodes = cell.findall(
                ".//{*}t"
            )

            return "".join(
                node.text or ""
                for node in text_nodes
            )

        value_node = cell.find(
            "{*}v"
        )

        if value_node is None:
            return ""

        value = (
            value_node.text or ""
        )

        # Shared string
        if cell_type == "s":

            try:

                index = int(value)

                if (
                    0 <= index
                    < len(self.shared_strings)
                ):

                    return (
                        self.shared_strings[index]
                    )

            except (
                ValueError,
                TypeError,
            ):
                pass

        return value

    # ---------------------------------------------------------
    # FIELD NAME
    # ---------------------------------------------------------

    def get_field_name(
        self,
        root,
        row_number,
    ):

        # Column C contains PRODUCT.
        cell_reference = (
            f"C{row_number}"
        )

        value = self.get_cell_value(
            root,
            cell_reference,
        )

        if value:
            return value.strip()

        return (
            f"Row {row_number}"
        )

    # ---------------------------------------------------------
    # EXPAND DATA VALIDATION RANGE
    # ---------------------------------------------------------

    def expand_sqref(
        self,
        sqref,
    ):

        cells = []

        for part in sqref.split():

            if ":" not in part:

                cells.append(part)
                continue

            start, end = part.split(
                ":",
                1
            )

            start_match = re.match(
                r"([A-Z]+)(\d+)",
                start
            )

            end_match = re.match(
                r"([A-Z]+)(\d+)",
                end
            )

            if (
                not start_match
                or not end_match
            ):
                continue

            start_col = (
                self.column_number(
                    start_match.group(1)
                )
            )

            end_col = (
                self.column_number(
                    end_match.group(1)
                )
            )

            start_row = int(
                start_match.group(2)
            )

            end_row = int(
                end_match.group(2)
            )

            for row in range(
                start_row,
                end_row + 1
            ):

                for col in range(
                    start_col,
                    end_col + 1
                ):

                    cells.append(
                        self.column_name(
                            col
                        )
                        + str(row)
                    )

        return cells

    # ---------------------------------------------------------
    # COLUMN NUMBER
    # ---------------------------------------------------------

    def column_number(
        self,
        letters,
    ):

        result = 0

        for char in letters:

            result = (
                result * 26
                + ord(char)
                - ord("A")
                + 1
            )

        return result

    # ---------------------------------------------------------
    # COLUMN NAME
    # ---------------------------------------------------------

    def column_name(
        self,
        number,
    ):

        result = ""

        while number:

            number, remainder = divmod(
                number - 1,
                26
            )

            result = (
                chr(65 + remainder)
                + result
            )

        return result

    # ---------------------------------------------------------
    # ROW NUMBER
    # ---------------------------------------------------------

    def get_row_number(
        self,
        cell,
    ):

        match = re.search(
            r"(\d+)$",
            cell
        )

        return (
            int(match.group(1))
            if match
            else 0
        )

    # ---------------------------------------------------------
    # READ OPTIONS FROM PRICE LIST
    # ---------------------------------------------------------

    def get_options_from_source(
        self,
        workbook_zip,
        source_range,
    ):

        if not source_range:
            return []

        # Example:
        # 'PRICE LIST '!$Q$27:$Q$33
        match = re.search(
            r"'?PRICE LIST '?!"
            r"\$?([A-Z]+)\$?(\d+):"
            r"\$?([A-Z]+)\$?(\d+)",
            source_range,
            re.IGNORECASE,
        )

        if not match:
            return []

        start_col = match.group(1)

        start_row = int(
            match.group(2)
        )

        end_col = match.group(3)

        end_row = int(
            match.group(4)
        )

        price_list_path = (
            self.find_price_list_sheet(
                workbook_zip
            )
        )

        root = ET.fromstring(
            workbook_zip.read(
                price_list_path
            )
        )

        options = []

        for row_number in range(
            start_row,
            end_row + 1
        ):

            cell_reference = (
                f"{start_col}{row_number}"
            )

            value = (
                self.get_cell_value(
                    root,
                    cell_reference,
                )
            )

            if value:

                options.append(
                    value.strip()
                )

        return options

    # ---------------------------------------------------------
    # FIND PRICE LIST SHEET
    # ---------------------------------------------------------

    def find_price_list_sheet(
        self,
        workbook_zip,
    ):

        workbook_xml = ET.fromstring(
            workbook_zip.read(
                "xl/workbook.xml"
            )
        )

        relationships_xml = ET.fromstring(
            workbook_zip.read(
                "xl/_rels/workbook.xml.rels"
            )
        )

        rel_namespace = (
            "http://schemas.openxmlformats.org/"
            "officeDocument/2006/relationships"
        )

        rel_map = {}

        for rel in relationships_xml:

            rel_map[
                rel.attrib["Id"]
            ] = rel.attrib["Target"]

        workbook_namespace = (
            "http://schemas.openxmlformats.org/"
            "spreadsheetml/2006/main"
        )

        sheet_nodes = workbook_xml.find(
            f"{{{workbook_namespace}}}sheets"
        )

        for sheet in sheet_nodes:

            name = sheet.attrib["name"]

            if (
                name.strip().upper()
                == "PRICE LIST"
            ):

                relationship_id = sheet.attrib[
                    f"{{{rel_namespace}}}id"
                ]

                target = rel_map[
                    relationship_id
                ]

                if target.startswith("/"):
                    target = target[1:]

                else:
                    target = (
                        "xl/"
                        + target.lstrip("/")
                    )

                return target

        raise ValueError(
            "PRICE LIST sheet not found."
        )