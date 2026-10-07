"""
Helpers for the WeasyPrint quotation PDF: number formatting, text-fitting and the
exact positions (PDF points, origin top-left) of every variable field.
Coordinates were measured from the original Dehlsen sample PDF (A4 = 595.56 x 842.04 pt).
No Django imports at module level, so it can be tested on its own.
"""
from decimal import Decimal, ROUND_HALF_UP
from html import escape

CHAR_W = 0.58   # average em-width of Poppins caps/digits, used to shrink long text


def _safe(html):
    try:
        from django.utils.safestring import mark_safe
        return mark_safe(html)
    except ImportError:          # unit tests without Django
        return html


def _dec(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def fmt_num(value):
    """Decimal('5.00') -> '5', Decimal('0.50') -> '0.5', 545.00 -> '545'."""
    d = _dec(value)
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def inr(value):
    """240000 -> '2,40,000' (Indian digit grouping)."""
    n = int(_dec(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    if len(s) <= 3:
        return sign + s
    head, tail, parts = s[:-3], s[-3:], []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts + [tail])


def money_text(value):
    """178272.77 -> '1,78,272.77'   240000.00 -> '2,40,000'   (paise shown only when there are any)."""
    from decimal import Decimal, ROUND_HALF_UP
    d = _dec(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, frac = format(abs(d), "f").split(".")
    text = inr(int(whole))
    if frac != "00":
        text += "." + frac
    return ("-" if d < 0 else "") + text


def fit_size(text, base, avail):
    """Shrink the font size so `text` fits in `avail` points (never grows)."""
    need = CHAR_W * base * len(text)
    return round(base if need <= avail else base * avail / need, 2)


def pt(x):
    """Format a float for CSS (always '.' as decimal separator)."""
    return "%.2f" % x


def financial_year(d):
    """date(2026,9,21) -> '26-27' (Indian FY runs April-March)."""
    y = d.year if d.month >= 4 else d.year - 1
    return "%02d-%02d" % (y % 100, (y + 1) % 100)


def next_offer_no(quotation_model, on_date, prefix="INQ"):
    """Optional: 'INQ/26-27/249'. Pass the Quotation model class."""
    head = "%s/%s/" % (prefix, financial_year(on_date))
    last = 0
    for no in quotation_model.objects.filter(offer_no__startswith=head).values_list("offer_no", flat=True):
        try:
            last = max(last, int(no.rsplit("/", 1)[1]))
        except ValueError:
            pass
    return "%s%d" % (head, last + 1)


# --------------------------------------------------------------------- cover
def cover_fields(offer_no, category, location, capacity, date_str, validity_days, business):
    rows = [  # text, left, top, base size, max width
        ("OFFER NO: %s" % offer_no, 53.4, 676.8, 12, 155),
        ("CATEGORY NO: %s" % category, 225.9, 676.8, 12, 160),
        ("LOCATION: %s" % location.upper(), 401.6, 676.8, 12, 145),
        ("CAPACITY (kW): %s kWp" % capacity, 54.1, 716.2, 12, 155),
        ("DATED: %s" % date_str, 226.7, 716.2, 12, 160),
        ("QUOTATION VALIDITY: %s DAYS" % validity_days, 401.6, 716.0, 10, 145),
        ("BUSINESS NAME: %s" % business.upper(), 54.5, 755.5, 12, 490),
    ]
    return [{"text": t, "left": pt(l), "top": pt(tp), "size": pt(fit_size(t, b, w))} for t, l, tp, b, w in rows]


# ------------------------------------------------------------------- summary
SUMMARY_TOP, SUMMARY_PITCH = 110.5, 16.6
BANK_TOP, BANK_PITCH = 697.0, 14.5


def positioned(rows, top, pitch, **extra):
    out = []
    for n, r in enumerate(rows):
        d = dict(r) if isinstance(r, dict) else {"text": r}
        d.update(extra)
        d["top"] = pt(top + n * pitch)
        out.append(d)
    return out


# ----------------------------------------------------------------- BOQ text
def text_html(text):
    """Escape and keep line breaks."""
    return _safe("<br>".join(escape(l) for l in (text or "").replace("\r\n", "\n").split("\n")))


def spec_html(specification, blue_labels=False, bold_first_label=False):
    """
    One <div> per line of the specification.
      blue_labels       -> text before ':' is blue
      bold_first_label  -> the first line's label is bold (e.g. 'RCC Roof Structure:')
    """
    out = []
    lines = [l for l in (specification or "").replace("\r\n", "\n").split("\n") if l.strip()]
    for i, line in enumerate(lines):
        head, sep, tail = line.partition(":")
        if sep and i == 0 and bold_first_label:
            out.append("<div><strong>%s:</strong>%s</div>" % (escape(head), escape(tail)))
        elif sep and blue_labels and len(head) <= 24:
            out.append('<div><span class="lbl">%s:</span>%s</div>' % (escape(head), escape(tail)))
        else:
            out.append("<div>%s</div>" % escape(line))
    return _safe("".join(out))

