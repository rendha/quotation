import os
from pathlib import Path

import fitz  # PyMuPDF

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Extract embedded images from a quotation PDF."

    def add_arguments(self, parser):
        parser.add_argument(
            "pdf_path",
            type=str,
            help="Path to the PDF file",
        )

    def handle(self, *args, **options):
        pdf_path = Path(options["pdf_path"])

        if not pdf_path.exists():
            raise CommandError(f"PDF not found: {pdf_path}")

        output_dir = Path(settings.MEDIA_ROOT) / "quotation_assets"
        output_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(
            self.style.NOTICE(f"Opening PDF: {pdf_path}")
        )

        try:
            pdf = fitz.open(pdf_path)
        except Exception as e:
            raise CommandError(f"Could not open PDF: {e}")

        total_images = 0

        for page_number, page in enumerate(pdf, start=1):
            images = page.get_images(full=True)

            self.stdout.write(
                f"Page {page_number}: {len(images)} embedded image(s)"
            )

            for image_number, image in enumerate(images, start=1):
                xref = image[0]

                try:
                    image_data = pdf.extract_image(xref)
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Could not extract image {image_number} "
                            f"on page {page_number}: {e}"
                        )
                    )
                    continue

                image_bytes = image_data["image"]
                extension = image_data["ext"]

                filename = (
                    f"page_{page_number:02d}"
                    f"_image_{image_number:02d}"
                    f"_xref_{xref}.{extension}"
                )

                output_path = output_dir / filename

                with open(output_path, "wb") as file:
                    file.write(image_bytes)

                total_images += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {filename}"
                    )
                )

        pdf.close()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Extracted {total_images} image(s)."
            )
        )
        self.stdout.write(
            f"Saved to: {output_dir}"
        )