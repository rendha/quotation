"""
Quotation PDF generator (WeasyPrint).  Drop-in replacement for the old ReportLab version:
the public function is unchanged ->  generate_quotation_pdf(quotation)  returns a BytesIO.

Pages
  1  Cover      cover_base.jpg (your cover, 7 fields blanked) + live text at measured coordinates
  2  Welcome    original page 2 copied unchanged (page_welcome.pdf)
  3  BOQ        HTML table built from quotation.items
  4  Summary    summary_base.jpg (logos/frames kept, values blanked) + live text

All artwork lives in ./pdf_design/ (templates + assets).  Business text you may want to edit
is in the EDITABLE section right below.
"""
import io
import logging
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from . import pdf_layout as L
from .calculations import GST_RATE, find_quotation_item, is_hybrid, is_tata, structure_kind
from .pdf_boq_sample import SAMPLE_BOQ

DESIGN_DIR = Path(__file__).resolve().parent / "pdf_design"
TEMPLATE_DIR = DESIGN_DIR / "templates"
ASSETS_DIR = DESIGN_DIR / "assets"
ASSETS_URI = ASSETS_DIR.as_uri() + "/"

# =====================================================================
# EDITABLE BUSINESS TEXT
# =====================================================================

# Subsidy printed for DCR quotations.  Non-DCR quotations print "Not applicable".
# NOTE: one flat amount is what the old generator printed for every quotation; if the amount
# depends on system size, replace this constant with a lookup inside subsidy_text().
SUBSIDY_DCR = Decimal("78000")
SUBSIDY_NOT_APPLICABLE = "Not Applicable"
REFUND_NOTE = "(80% of KSEB Reg fee excluding GST is refundable)"   # shown for DCR only

# {fee} is replaced by quotation.kseb_fee.  If your kseb_fee is BEFORE gst, use
# "\u20b9{fee} +18%GST /- (INCLUDED)"
KSEB_FEE_TEXT = "\u20b9{fee}/- (INCLUDED)"

logger = logging.getLogger(__name__)

PAYMENT_TERMS = [
    "60% upon signing the quotation/ work contract",
    "30% upon delivering materials",
    "10% upon completing all physical works",
]
PAYMENT_NOTE = "All payments are directed to Dehlsen Engineering LLP."
# The bank account printed under the payment terms is NOT in this file: it is read from the database
# (Admin > Payment details), so the account number never goes into git.  See bank_details() below.

# Wording that depends on the panel technology (edit if your warranty text differs by brand).  {w} = wattage.
PANEL_SPEC_TOPCON = ("N- Type TOPCon {w} WP High performance bifacial solar module 132 half-cell, glass/glass, "
                     "N-Type TOPCon, 12 years Manufacturer's warranty and 30 years Performance guarantee")
PANEL_SPEC_BIFACIAL = ("{w} WP High performance bifacial solar module, glass/glass, "
                       "12 years Manufacturer's warranty and 30 years Performance guarantee")
PANEL_SPEC_OTHER = ("{tech} {w} WP High performance solar module, glass/glass, "
                    "12 years Manufacturer's warranty and 30 years Performance guarantee")
STRUCTURE_MAKE = "REPUTED"          # printed in the MAKE column of the mounting structure row

# BOQ rows whose description contains these words get blue "Label:" text / a bold first label
# The price summary on the BOQ page shows: amount before GST, GST, total.  Set True to also print the
# internal total cost and margin (normally NOT shown to the customer).
SHOW_COST_AND_MARGIN = False

# Which Quotation field is printed as "Price" on the summary page.
# Options: "final_quotation_price" (the editable price) or "suggested_quotation_price" (the calculated one).
PRICE_FIELD = "final_quotation_price"

# BOQ rows (by Sr.No) whose specification text is taken from the quotation's own item instead of the
# sample text.  Empty set = always print the sample text (only qty / make follow the quotation).
SPEC_FROM_ITEM = set()

BLUE_LABEL_KEYWORDS = ("MOUNTING", "EARTHING", "INVERTER")
BOLD_FIRST_LABEL_KEYWORDS = ("MOUNTING",)


# =====================================================================
# DATA MAPPING  (your models -> what is printed)
# =====================================================================
def _is_dcr(q):
    return (q.panel_dcr_status or "").strip().lower() == "dcr"


def _is_non_dcr(q):
    return (q.panel_dcr_status or "").strip().lower() == "non_dcr"


def _is_both(q):
    """A quotation with a DCR panel and a non-DCR panel (the second one is q.panel2_option / q.panel2_quantity)."""
    return (q.panel_dcr_status or "").strip().lower() == "both" and getattr(q, "panel2_option", None) is not None


def _items(q):
    return sorted(q.items.all(), key=lambda i: i.id)


def _is_alt(q):
    """A DCR / Non-DCR quotation that offers a SECOND panel (q.panel2_option, quantity 0): priced with the first panel, printed with both makes."""
    return ((q.panel_dcr_status or "").strip().lower() in ("dcr", "non_dcr") and getattr(q, "panel2_option", None) is not None
            and q.panel_option is not None)


def _find_item(q, keyword):
    for item in _items(q):
        if keyword in (item.description or "").upper():
            return item
    return None


def _cover_fields(q):
    return L.cover_fields(
        offer_no=(q.offer_no or "").strip(),
        category=q.get_system_type_display(),
        location=(q.location or "").strip(),
        capacity=L.fmt_num(q.system_size),
        date_str=q.date.strftime("%d/%m/%Y"),
        validity_days=q.validity_days,
        business=(q.business_name or "").strip(),
    )


def _norm(text):
    return " ".join((text or "").upper().split())


def _match_items(q):
    """For each sample BOQ row, pick the quotation item it stands for (each item is used once)."""
    items, used, matched = _items(q), set(), {}
    for row in SAMPLE_BOQ:
        for item in items:
            if item.id in used:
                continue
            desc = _norm(item.description)
            if any(k in desc for k in row["keywords"]) and not any(x in desc for x in row["exclude"]):
                matched[row["sr"]] = item
                used.add(item.id)
                break
    return matched


# ---------------------------------------------------------------------
# BOQ ROWS - every dynamic value comes from what the user chose on the quotation
# ---------------------------------------------------------------------
def _three_phase(q):
    return "three" in (q.phase or "").lower()


def _size_mm(text):
    """'4 SQMM' / '4 SQ.MM' / '2.5 SQMM FR Copper' / '25 Sq.mm'  ->  '4' / '2.5' / '25'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*sq", text or "", re.I)
    return m.group(1) if m else ""


def _label(item):
    """The dropdown option text the old import stored in item.make (a size or spec, NOT a brand)."""
    return (getattr(item, "make", "") or "").strip() if item is not None else ""


def _product_brand(item):
    """The brand of the product the user selected for this item, if there is one."""
    product = getattr(item, "product", None) if item is not None else None
    return (getattr(product, "make", "") or "").strip() if product is not None else ""


def _brand_from_label(label):
    """'Single Phase L&T' -> 'L&T',  'LT TOD 0.5s Visiontech' -> 'Visiontech'.  Anything unclear -> ''."""
    text = re.sub(r"(single|three)\s*phase", "", label or "", flags=re.I)
    text = re.sub(r"\b[LH]T\s*TOD\s*[\d.]+\s*s?\b", "", text, flags=re.I)
    text = " ".join(text.split())
    if not text or any(ch.isdigit() for ch in text) or len(text.split()) > 2 or text.upper() == "SPEC":
        return ""
    return text


def _comp(q, key):
    """The rate-sheet product calculate_quotation() priced for this component: name, make, quantity, rate."""
    breakdown = getattr(q, "cost_breakdown", None) or {}
    return (breakdown.get("components") or {}).get(key) or {}


def _positive(value):
    try:
        return value is not None and Decimal(str(value)) > 0
    except Exception:
        return False


def _panel_spec(panel, watts=None):
    w, tech = (watts or L.fmt_num(panel.wattage)), (panel.panel_type or "").strip()
    if "TOPCON" in tech.upper():
        return PANEL_SPEC_TOPCON.format(w=w)
    if "BIFACIAL" in tech.upper():
        return PANEL_SPEC_BIFACIAL.format(w=w)
    return PANEL_SPEC_OTHER.format(tech=tech.title(), w=w).strip()


def _panel_kind(panel):
    tech = (panel.panel_type or "").upper()
    return "TOPCON" if "TOPCON" in tech else "BIFACIAL" if "BIFACIAL" in tech else tech.strip()


def _both_watts(q):
    """610-620 (or just 610 when both panels have the same wattage)."""
    a, b = sorted([q.panel_option.wattage, q.panel2_option.wattage])
    return L.fmt_num(a) if a == b else "%s-%s" % (L.fmt_num(a), L.fmt_num(b))


def _both_makes(q):
    names = []
    for p in (q.panel_option, q.panel2_option):
        name = (p.company or "").strip()
        if name and name.upper() not in [n.upper() for n in names]:
            names.append(name)
    return "/".join(names)


def _row_panel(q, item, row):
    panel = q.panel_option
    if _is_both(q) or _is_alt(q):                           # two kinds of panel on one BOQ row
        # like the sample "both" quotation: one row, the TOTAL number, the wattage as a range and both makes
        second = q.panel2_option
        spec = _panel_spec(panel, _both_watts(q))
        if _panel_kind(panel) != _panel_kind(second):             # different technology: describe both
            spec = _panel_spec(panel, L.fmt_num(panel.wattage)) + "\n" + _panel_spec(second, L.fmt_num(second.wattage))
        out = {"spec": spec, "make": _both_makes(q)}
        total = (q.panel_quantity or 0) + ((q.panel2_quantity or 0) if _is_both(q) else 0)      # an offered second panel is not added to the number
        if _positive(total):
            out["qty"] = L.fmt_num(total)
        return out
    if panel is None:
        return {}
    out = {"spec": _panel_spec(panel), "make": (panel.company or "").strip()}
    if _positive(q.panel_quantity):
        out["qty"] = L.fmt_num(q.panel_quantity)
    return out


def _inverter_make(q):
    """Brand of the inverter the user selected ('Other' uses the name that was typed in)."""
    if (q.inverter_make or "").strip():
        return q.inverter_make.strip()
    item = find_quotation_item(q, "INVERTER")
    return _product_brand(item) or _label(item) or (q.inverter_make or "").strip()


def _row_inverter(q, item, row):
    """kW, phase and MPPT come from the INVERTER that was selected (e.g. a 5 kW single-phase inverter on a 3 kW three-phase plant)."""
    comp = _comp(q, "inverter")
    chosen = ((q.inverter_type or "") + " " + (getattr(getattr(item, "product", None), "name", "") or "")).upper()
    kw = comp.get("capacity") or q.inverter_kw or q.system_size
    phase = comp.get("phase") or ("THREE" if _three_phase(q) else "SINGLE")          # only an unnamed ('other') inverter falls back to the plant
    mppt = comp.get("mppt") or (2 if "DUAL" in chosen else 1)
    spec = row["spec"].replace("{kw}", L.fmt_num(kw)) \
                      .replace("{phase}", phase) \
                      .replace("1 MPPT trackers", "%s MPPT trackers" % mppt)
    if is_hybrid(q):
        spec = spec.replace("on grid inverter", "Hybrid inverter")
        years = _warranty_years(comp.get("name") or q.inverter_type)
        if years:
            spec = re.sub(r"Warranty: \d+ Years", "Warranty: %s Years" % years, spec)
    out = {"spec": spec, "qty": "1"}
    make = _inverter_make(q)
    if make:
        out["make"] = make
    return out


def _warranty_years(name):
    """'SOLIS HYBRID 5KW 1PH - 10 YEARS WARRANTY' -> '10' (empty when the name has no warranty)."""
    found = re.search(r"(\d+)\s*YEARS", (name or "").upper())
    return found.group(1) if found else ""


def _row_structure(q, item, row):
    kind = structure_kind(q.structure_type)
    if kind == "none":
        return {"spec": "Mounting structure is not included in this quotation", "qty": "-", "make": "-"}
    spec = row["spec"]
    title = {"roof": "RCC Roof Structure", "gp": "GP Structure", "gi": "GI Structure"}.get(kind)
    if title:
        spec = spec.replace("RCC Roof Structure", title)
        if kind == "gp":
            spec = spec.replace("GI pipe", "GP pipe")                 # a GP structure is made of GP pipe
    feet = Decimal("2") if kind == "roof" else q.structure_feet
    if _positive(feet):
        spec = spec.replace("Height: 1.2M", "Height: %s FT" % L.fmt_num(feet))
    return {"spec": spec, "qty": "1", "make": "TATA" if is_tata(q.structure_type) else STRUCTURE_MAKE}


def _row_box(q, item, row):
    """ACDB / DCDB: 1 in 1 out for single phase, 2 in 2 out for three phase."""
    spec = row["spec"]
    if _three_phase(q):
        spec = spec.replace("1 IN 1 OUT", "2 IN 2 OUT").replace("1 in 1 out", "2 in 2 out")
    return {"spec": spec, "qty": "1"}


def _row_dc_cable(q, item, row):
    comp = _comp(q, "dc_cable")
    size = _size_mm(q.dc_cable) or _size_mm(comp.get("name", "")) or _size_mm(_label(item))
    spec = row["spec"]
    if size:
        spec = spec.replace("4 Sq.mm 1.8kV", "%s Sq.mm 1.8kV" % size).replace("1C X 4 Sq.mm", "1C X %s Sq.mm" % size)
    out = {"spec": spec}
    if _positive(q.dc_cable_quantity):
        out["qty"] = L.fmt_num(q.dc_cable_quantity)
    make = comp.get("make") or _product_brand(item)
    if make:
        out["make"] = make
    return out


def _row_ac_wire(q, item, row):
    comp = _comp(q, "ac_wire")
    size = _size_mm(q.ac_wire) or _size_mm(comp.get("name", "")) or _size_mm(_label(item))
    out = {"spec": row["spec"].replace("2RX4 Sq.mm", "2RX%s Sq.mm" % size) if size else row["spec"]}
    if _positive(q.ac_wire_quantity):
        out["qty"] = L.fmt_num(q.ac_wire_quantity)
    make = comp.get("make") or _product_brand(item)
    if make:
        out["make"] = make
    return out


def _row_ug_cable(q, item, row):
    comp = _comp(q, "ug_cable")
    m = re.search(r"UG CABLE\s+(\d+)\s*C\s*(\d+(?:\.\d+)?)\s*SQ", comp.get("name", ""), re.I) or \
        re.search(r"(\d+)\s*C\s*X\s*(\d+(?:\.\d+)?)\s*(?:AL|CU)?", _label(item), re.I)
    out = {}
    if m:
        out["spec"] = "%sCX%s Sq.mm XLPE, Aluminum Ug Cable" % (m.group(1), m.group(2))
    if _positive(comp.get("quantity")):
        out["qty"] = L.fmt_num(comp["quantity"])                       # the length that was priced
    elif item is not None and _positive(item.quantity):
        out["qty"] = L.fmt_num(item.quantity)
    if comp.get("make"):
        out["make"] = comp["make"]
    return out


def _row_meter_panel(q, item, row):
    return {"spec": row["spec"].replace("Single phase Energy Meter", "%s phase Energy Meter" % ("Three" if _three_phase(q) else "Single")),
            "qty": "1"}


def _row_arrester(q, item, row):
    m = re.search(r"(\d+(?:\.\d+)?)\s*m\b", _label(item), re.I)
    out = {"qty": "1"}
    if m:
        out["spec"] = "Vertical Air Terminal with accessories %sm" % m.group(1)
    return out


def _row_earthing(q, item, row):
    size = _size_mm(_comp(q, "earthing_cable").get("name", "")) or _size_mm(_label(item))
    spec = row["spec"]
    if size:
        spec = spec.replace("25 Sq.mm", "%s Sq.mm" % size)
    out = {"spec": spec}
    if _positive(q.earth_quantity):
        out["qty"] = L.fmt_num(q.earth_quantity)
        out["spec"] = out["spec"].replace("rod-3", "rod-%s" % L.fmt_num(q.earth_quantity))      # rods = earth quantity
    return out


def _row_meter(q, item, row):
    out = {"qty": "1"}
    brand = _comp(q, "net_meter" if row["sr"] == 15 else "energy_meter").get("make") or _brand_from_label(_label(item))
    if brand:
        out["make"] = brand
    return out


DYNAMIC_ROWS = {1: _row_panel, 2: _row_inverter, 3: _row_structure, 5: _row_box, 6: _row_box, 7: _row_dc_cable,
                8: _row_ac_wire, 9: _row_ug_cable, 10: _row_meter_panel, 11: _row_arrester, 12: _row_earthing,
                15: _row_meter, 16: _row_meter}


def _boq_rows(q):
    """
    Always the 19 rows of the sample quotation.  Rows that depend on the customer's choices are built from
    those choices (DYNAMIC_ROWS); the other rows (walkway, accessories, conduits, documentation, design, AMC)
    keep the sample wording.  Nothing is taken blindly from the package item's quantity / make.
    """
    matched = _match_items(q)
    rows = []
    for row in SAMPLE_BOQ:
        values = {"spec": row["spec"], "qty": row["qty"], "make": row["make"]}
        builder = DYNAMIC_ROWS.get(row["sr"])
        if builder is not None:
            values.update({k: v for k, v in builder(q, matched.get(row["sr"]), row).items() if v not in (None, "")})

        spec = values["spec"]
        if row["sr"] in SPEC_FROM_ITEM and matched.get(row["sr"]) is not None and (matched[row["sr"]].specification or "").strip():
            spec = matched[row["sr"]].specification

        up = row["particular"].upper()
        rows.append({
            "sr": row["sr"],
            "particular": L.text_html(row["particular"]),
            "spec": L.spec_html(
                spec,
                blue_labels=any(k in up for k in BLUE_LABEL_KEYWORDS),
                bold_first_label=any(k in up for k in BOLD_FIRST_LABEL_KEYWORDS),
            ),
            "qty": values["qty"],
            "make": values["make"],
        })
    if is_hybrid(q):
        battery = _battery_row(q)
        if battery is not None:
            rows[1]["rowspan"] = 2                                    # the sample: the battery is a second line of the inverter's number
            rows.insert(2, battery)
    return rows


def _battery_row(q):
    """The BOQ row of a hybrid quotation's battery (None when no battery was priced)."""
    comp = _comp(q, "battery")
    name = (comp.get("name") or "").strip()
    if not name:
        return None
    upper = name.upper()
    spec = "Li-Ion battery"
    kwh = re.search(r"(\d+(?:\.\d+)?)\s*KWH", upper)
    cycles = re.search(r"(\d+)\s*CYCLE", upper)
    if kwh:
        spec += " %s kWh" % kwh.group(1)
    if cycles:
        spec += ", %s cycles" % cycles.group(1)
    years = _warranty_years(name)
    if years:
        spec += "\nWarranty: %s Years" % years
    return {"sr": "", "skip_sr": True, "particular": L.text_html("Battery"), "spec": L.spec_html(spec, blue_labels=True, bold_first_label=False),
            "qty": L.fmt_num(comp.get("quantity") or 1), "make": (comp.get("make") or "").strip() or "POLYCAB"}


def _customer_lines(q):
    """Customer details printed under the BOQ.  (q.customer_name is now "Quotation For" - an internal name for the dashboard - so it is not printed.)"""
    lines = [
        ("Customer", q.business_name),
        ("Phone", q.phone),
        ("Email", q.email),
        ("Address", q.address),
        ("Project location", q.location),
    ]
    return [{"label": label, "value": (value or "").strip()} for label, value in lines if (value or "").strip()]


def _price_summary(q):
    """
    Only PRINTS values already calculated by calculations.calculate_quotation().
    The BOQ above is a display table: nothing in it is added to these amounts.

    The automatic price is  selling price + GST  rounded to the nearest Rs 100, so a "Round off" line closes the
    small gap.  A price typed in by hand is far from that, so it is printed as one total.
    """
    final = Decimal(str(q.final_quotation_price or 0))
    suggested = Decimal(str(q.suggested_quotation_price or 0))
    difference = final - suggested
    rows = []
    if SHOW_COST_AND_MARGIN:
        rows.append(("Total cost", q.calculated_cost))
        rows.append(("Margin %s%%" % L.fmt_num(q.margin_percent), q.margin_amount))
    if abs(difference) <= Decimal("50"):
        rows.append(("Amount before GST", q.calculated_selling_price))
        rows.append(("GST @ %s%%" % L.fmt_num(GST_RATE), q.gst_amount))
        if difference != 0:
            rows.append(("Round off", difference))
    rows.append(("Total price (incl. GST)", final))
    return [{"label": label, "value": "\u20b9 " + L.money_text(value), "strong": i == len(rows) - 1}
            for i, (label, value) in enumerate(rows)]


def _module_text(q):
    panel = q.panel_option
    if _is_alt(q):                                    # two makes offered: "ADANI/RENEWSYS TOPCON DCR"
        techs = []
        for p in (panel, q.panel2_option):
            t = (p.panel_type or "").strip().upper()
            if t and t not in techs:
                techs.append(t)
        return " ".join(x for x in (_both_makes(q).upper(), "/".join(techs), "DCR" if _is_dcr(q) else "NDCR") if x)
    if _is_both(q) and panel is not None:
        # like the sample: "EMMVEE/RENEWSYS TOPCON BIFACIAL (8DCR+5NDCR)"
        techs = []
        for p in (panel, q.panel2_option):
            t = (p.panel_type or "").strip().upper()
            if t and t not in techs:
                techs.append(t)
        text = " ".join(x for x in (_both_makes(q).upper(), "/".join(techs)) if x)
        return "%s (%sDCR+%sNDCR)" % (text, L.fmt_num(q.panel_quantity or 0), L.fmt_num(q.panel2_quantity or 0))
    if panel is None:
        return "-"
    text = " ".join(x.strip() for x in (panel.company, panel.panel_type) if x and x.strip()).upper()
    tokens = text.split()
    if not any(t in ("DCR", "NON-DCR", "NONDCR", "NDCR") for t in tokens):
        text += " DCR" if _is_dcr(q) else " NDCR"
    return text


def _system_size_text(q):
    panel = q.panel_option
    if _is_both(q) and panel is not None and (q.panel_quantity or q.panel2_quantity):
        return "%sWP*%s NOS" % (_both_watts(q), L.fmt_num((q.panel_quantity or 0) + (q.panel2_quantity or 0)))
    if _is_alt(q) and q.panel_quantity:
        return "%sWP*%s NOS" % (_both_watts(q), L.fmt_num(q.panel_quantity))
    if panel is not None and q.panel_quantity:
        return "%sWP*%s NOS" % (L.fmt_num(panel.wattage), L.fmt_num(q.panel_quantity))
    return "%s kWp" % L.fmt_num(q.system_size)


def _inverter_text(q):
    kw = _comp(q, "inverter").get("capacity") or q.inverter_kw or q.system_size       # the inverter's own kW
    if is_hybrid(q):
        return ("%s Hybrid %skW" % (_inverter_make(q), L.fmt_num(kw))).strip()          # the sample: "SOLAIRE Hybrid 5kW"
    return ("%s %s KW" % (_inverter_make(q), L.fmt_num(kw))).strip()


def subsidy_text(q):
    return "\u20b9%s/-" % L.inr(SUBSIDY_DCR) if _is_dcr(q) else SUBSIDY_NOT_APPLICABLE


def _summary_rows(q):
    rows = [
        {"label": "Product Classification", "value": q.get_system_type_display(), "joined": True},
        {"label": "System size", "value": _system_size_text(q)},
        {"label": "Solar modules", "value": _module_text(q)},
        {"label": "Inverter", "value": _inverter_text(q)},
        {"label": "Price", "value": "\u20b9 %s/-" % L.money_text(getattr(q, PRICE_FIELD))},
        {"label": "KSEB Reg. FEE", "value": KSEB_FEE_TEXT.format(fee=L.inr(q.kseb_fee))},
        {"label": "Subsidy", "value": subsidy_text(q)},
    ]
    if _is_non_dcr(q):                                # Non-DCR: "Price ₹ 3,90,000/-(KSEB INCLUDED)", no KSEB row, Subsidy: Not Applicable
        rows = [r for r in rows if r["label"] != "KSEB Reg. FEE"]
        for r in rows:
            if r["label"] == "Price":
                r["value"] += "(KSEB INCLUDED)"
    if _is_both(q) or is_hybrid(q):                   # the sample "both" and hybrid quotations have no Subsidy row
        rows = [r for r in rows if r["label"] != "Subsidy"]
    return L.positioned(rows, L.SUMMARY_TOP, L.SUMMARY_PITCH)


# =====================================================================
# RENDERING
# =====================================================================
_engine = None


def _render_html(template_name, context):
    """Render one of our templates with a standalone Django engine (independent of project settings)."""
    global _engine
    from django.template import Context, Engine
    if _engine is None:
        _engine = Engine(dirs=[str(TEMPLATE_DIR)], autoescape=True)
    return _engine.get_template(template_name).render(Context(context))


def _html_to_pdf(html):
    from weasyprint import HTML          # imported here so a WeasyPrint problem only affects PDF creation
    return HTML(string=html, base_url=ASSETS_URI).write_pdf()


def _part(template_name, context):
    return PdfReader(io.BytesIO(_html_to_pdf(_render_html(template_name, context))))


def bank_details():
    """
    The bank lines for the last page: [("Beneficiary Name", "..."), ("Account Number", "..."), ("IFSC", "..."), ("Bank", "...")].
    They come from the first "Payment details" record (Admin).  A blank field is left out.  With no record - or if the table has not been
    created yet - the page simply has no bank lines (and a warning is written to the log), the PDF never fails because of it.
    """
    try:
        from .models import PaymentDetails                  # imported here so this module can be tested without Django
        record = PaymentDetails.objects.order_by("id").first()
    except Exception:
        logger.warning("The bank details could not be read from the database: the PDF has no bank lines.  "
                       "Did you run 'python manage.py migrate' after adding Payment details?", exc_info=True)
        return []
    if record is None:
        logger.warning("No Payment details record: the PDF has no bank lines.  Add one in the Admin (Payment details).")
        return []
    pairs = (("Beneficiary Name", record.beneficiary_name), ("Account Number", record.account_number),
             ("IFSC", record.ifsc), ("Bank", record.bank_name))
    return [(label, str(value).strip()) for label, value in pairs if str(value or "").strip()]


def generate_quotation_pdf(quotation):
    q = quotation
    base = {"assets": ASSETS_URI}
    parts = [
        _part("cover.html", dict(base, cover_fields=_cover_fields(q))),
        PdfReader(str(ASSETS_DIR / "page_welcome.pdf")),
        _part("boq.html", dict(base, boq_rows=_boq_rows(q), customer_lines=_customer_lines(q), price_rows=_price_summary(q))),
        _part("summary.html", dict(
            base,
            summary_rows=_summary_rows(q),
            refund_note=REFUND_NOTE if (_is_dcr(q) or _is_both(q)) else "",
            payment_terms=PAYMENT_TERMS,
            payment_note=PAYMENT_NOTE,
            bank_lines=L.positioned(
                [{"text": "%s: %s" % (k, v)} for k, v in bank_details()], L.BANK_TOP, L.BANK_PITCH),
        )),
    ]
    writer = PdfWriter()
    for part in parts:
        for page in part.pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": "Quotation %s" % q.offer_no, "/Author": "Dehlsen Energy"})

    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer


# ---- compatibility for views that use the other function name / extra arguments ----
def build_quotation_pdf(*args, **kwargs):
    """Finds the Quotation among the arguments the view passes."""
    for arg in list(args) + list(kwargs.values()):
        if hasattr(arg, "offer_no") and hasattr(arg, "items"):
            return generate_quotation_pdf(arg)
    raise TypeError("build_quotation_pdf() was not given a Quotation object")