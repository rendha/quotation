"""
quotations/filenames.py - the name a quotation PDF is saved under:    <name>_<plant kW>kW.pdf        for example   HUDA_3kW.pdf

The name is the customer printed on the PDF (the "Customer / Business Name" of the quotation).  To use the internal "Quotation For" person
instead, change NAME_FIELD below to "customer_name".  When the name is empty the other one is used, then the offer number.
Pure Python: no Django needed, so it can be tested on its own.
"""
import re
from decimal import Decimal, InvalidOperation

NAME_FIELD = "business_name"            # or "customer_name"  (the "Quotation For" person)
FALLBACK_FIELDS = ("business_name", "customer_name", "offer_no")
MAX_NAME_LENGTH = 80
DEFAULT_NAME = "Quotation"

_NOT_ALLOWED_IN_A_FILE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def clean_for_file_name(text):
    """'Mr Pramod K / Sons' -> 'Mr_Pramod_K_Sons'.  Letters of any language stay; characters a file name cannot hold become spaces."""
    text = _NOT_ALLOWED_IN_A_FILE_NAME.sub(" ", str(text or ""))
    text = "_".join(text.split())                                    # spaces (and runs of them) -> one underscore
    return text.strip("._-")[:MAX_NAME_LENGTH].rstrip("._-")


def kw_text(size):
    """Decimal('3.00') -> '3',  Decimal('3.30') -> '3.3'.  '' when there is no size."""
    try:
        value = Decimal(str(size))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if not value.is_finite() or value <= 0:
        return ""
    return format(value.normalize(), "f")


def pdf_filename(quotation):
    """HUDA_3kW.pdf  (HUDA.pdf if the size is unknown)."""
    name = ""
    for field in (NAME_FIELD,) + tuple(f for f in FALLBACK_FIELDS if f != NAME_FIELD):
        name = clean_for_file_name(getattr(quotation, field, ""))
        if name:
            break
    name = name or DEFAULT_NAME
    size = kw_text(getattr(quotation, "system_size", None))
    return "%s_%skW.pdf" % (name, size) if size else "%s.pdf" % name
