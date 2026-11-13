"""PDF of an add-on quotation, in the normal quotation design: cover, welcome page, then ONE summary page with the items table
(a separate BOQ page only when there are too many items for the box)."""
import io

from pypdf import PdfReader, PdfWriter

from . import pdf_layout as L
from .pdf_generator import ASSETS_DIR, ASSETS_URI, PAYMENT_NOTE, PAYMENT_TERMS, _part, bank_details

BOX_ITEMS = 6      # how many items fit inside the overview box


def _cover(a):
    rows = [
        ("OFFER NO: %s" % a.offer_no, 53.4, 676.8, 12, 155),
        ("CATEGORY: UPGRADE", 225.9, 676.8, 12, 160),
        ("LOCATION: %s" % (a.location or "-").upper(), 401.6, 676.8, 12, 145),
        ("ITEMS: %d NOS" % a.items.count(), 54.1, 716.2, 12, 155),
        ("DATED: %s" % a.created_at.strftime("%d-%m-%Y"), 226.7, 716.2, 12, 160),
        ("QUOTATION VALIDITY: %s DAYS" % a.validity_days, 401.6, 716.0, 10, 145),
        ("BUSINESS NAME: %s" % a.customer_name.upper(), 54.5, 755.5, 12, 490),
    ]
    return [{"text": t, "left": L.pt(l), "top": L.pt(tp), "size": L.pt(L.fit_size(t, b, w))} for t, l, tp, b, w in rows]


def _rows(a):
    out = []
    for n, it in enumerate(a.items.all(), 1):
        out.append({"sr": n, "particular": it.description, "spec": L.text_html(it.specification) if it.specification else "",
                    "qty": "%s %s" % (L.fmt_num(it.quantity), it.unit), "make": it.make})
    return out


def build_addon_pdf(a):
    rows = _rows(a)
    overflow = len(rows) > BOX_ITEMS
    low = "GST @ 5%: ₹ %s" % L.money_text(a.gst_low_amount)
    high = "GST @ 18%: ₹ %s" % L.money_text(a.gst_high_amount)
    base = {"assets": ASSETS_URI}
    parts = [_part("cover.html", dict(base, cover_fields=_cover(a))), PdfReader(str(ASSETS_DIR / "page_welcome.pdf"))]
    if overflow:
        parts.append(_part("boq.html", dict(base, boq_rows=[dict(r, skip_sr=False, rowspan=None) for r in rows], wide_qty=False)))
    parts.append(_part("addon_summary.html", dict(
        base, rows=[] if overflow else rows, overflow=overflow,
        taxable="₹ %s" % L.money_text(a.taxable_total), gst_low=low, gst_high=high,
        total="₹ %s/-" % L.money_text(a.final_total),
        payment_terms=PAYMENT_TERMS, payment_note=PAYMENT_NOTE,
        bank_lines=L.positioned([{"text": "%s: %s" % (k, v)} for k, v in bank_details()], L.BANK_TOP, L.BANK_PITCH))))
    w = PdfWriter()
    for part in parts:
        for page in part.pages:
            w.add_page(page)
    w.add_metadata({"/Title": "Upgrade quotation %s" % a.offer_no, "/Author": "Dehlsen Energy"})
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf
