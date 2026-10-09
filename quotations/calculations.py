"""
quotations/calculations.py
==========================

SINGLE SOURCE OF TRUTH FOR EVERY MONEY CALCULATION.   calculate_quotation(quotation) is called after every save
and before every PDF; views.py, the templates and the PDF generator never calculate money.

    TOTAL COST = everything the user selected, added up
        panel .............. panels x panel W x rate per watt   (PanelOption).  Panels = the count whose TOTAL WATTS are
                             NEAREST the requested size: 3,000 W / 540 W = 5.56, so compare 5 x 540 = 2,700 W with
                             6 x 540 = 3,240 W and take the nearer one -> 6.  (An optional limit on how far under the
                             requested size the total may be: PANEL_SHORTFALL_ALLOWED_PERCENT, 100 = no limit.)
                             A number typed in on the quotation (panel_quantity_manual) replaces the calculated count.
        inverter ........... the selected inverter's rate (default: the one matching kW and phase)    (rate sheet)
        DC cable, AC wire .. selected product's rate per metre x the length entered                   (rate sheet)
        earth rod .......... rate x EARTH_ROD_QUANTITY (fixed 3 nos)                                  (rate sheet)
        ACDB, DCDB, meter box, UG cable, earthing cable, arrester, energy meter, net meter ... by phase  (rate sheet)
        structure material . feet x STRUCTURE WATTS  roof 2 ft | GP selected height | GI selected height + 2 ft
                             (3 kW only: GP selected height - 1 ft, GI the selected height; STRUCTURE_FEET_ADJUST)
        structure wage ..... wage factor x STRUCTURE WATTS   factor 3 for 3-4 kW, 2.5 for 5 kW and above (calculated, not fixed;
                             a wage typed in by hand on the quotation replaces it)
                             STRUCTURE WATTS = the total panel watts, unless a structure kW is typed on the quotation
                             (structure_kw_manual: 8 -> 8,000 W).
      + BOS ................ ONE predefined amount that depends on the plant size and phase (BOS_AMOUNTS)
      + the prefixed non-taxable charges (fields of the quotation; a new quotation starts with the amounts set in views.py:
            electrical work 8,000, transportation / travel 2,000, KSEB fee 4,720, loading 1,000, documentation 2,500)
    SELLING PRICE = TOTAL COST / margin factor x 100      the costing sheet's "Cost+Margine": the cost is `factor` % of the price
    MARGIN        = SELLING PRICE - TOTAL COST            = a share of the SELLING price: GP % = 100 - factor
                    factor = the costing sheet's factor per plant size (MARGIN_FACTORS: 5 kW 85) minus
                    MARGIN_EXTRA_GP_POINTS (1):  5 kW 84 -> GP 16%.   3 kW is fixed at factor 85 -> GP 15% (FIXED_MARGIN_FACTORS)
    + GST         = SELLING PRICE x 9 / 100
    FINAL PRICE   = the amount above rounded to the nearest Rs 100   (a price typed in by hand is kept)

The rates come from the Excel rate sheet (Panel options and Products loaded by load_rates_from_excel); the package
items on a quotation (QuotationItem) are for DISPLAY - their own rates and quantities are never used.
Money is Decimal, rounded ROUND_HALF_UP (to the paisa; the final price to the nearest Rs 100).  The panel's own GST is calculated only for display.
Worked example (3 kW, Adani 600 W x 5 at Rs 27.5, 5 kW inverter, DC cable 50 m): cost 170,570.00 + margin 34,114.00 = 204,684.00, + GST 18,421.56 = 223,105.56, final price Rs 223,100.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

# =========================================================
# CONSTANTS
# =========================================================

GST_RATE = Decimal("9")            # final GST, applied once, after the margin

# MARGIN - worked out exactly as in the costing sheet (PM_Suraghar_2_0 ... Emvee.xlsx, the "Cost+Margine" row):
#     selling price = cost / FACTOR x 100         margin = selling price - cost         GP % = 100 - FACTOR  (of the SELLING price)
# The FACTOR is typed per plant size in that sheet; these are its values.  A size that is not listed uses DEFAULT_MARGIN_FACTOR.
# To change a margin, change the factor here (a lower factor = a higher margin).
MARGIN_FACTORS = {
    Decimal("2"): Decimal("83"), Decimal("3"): Decimal("83.5"), Decimal("4"): Decimal("83"), Decimal("5"): Decimal("85"),
    Decimal("6"): Decimal("83"), Decimal("8"): Decimal("85"), Decimal("10"): Decimal("83"),
}
DEFAULT_MARGIN_FACTOR = Decimal("85")
# One extra point of margin on top of the sheet's GP (3 kW 16.5% -> 17.5%, 5 kW 15% -> 16%): the factor used is the sheet's minus this.
# 0 = exactly the costing sheet.
MARGIN_EXTRA_GP_POINTS = Decimal("1")
# Sizes whose margin factor is fixed here as the FINAL factor (the extra point above is NOT taken off again).
# 3 kW: GP 15% -> factor 85.   Every other size keeps (sheet factor - MARGIN_EXTRA_GP_POINTS).
FIXED_MARGIN_FACTORS = {Decimal("3"): Decimal("85")}
ROUND_FINAL_TO = Decimal("100")         # the final price is rounded to the nearest Rs 100 (Decimal("0.01") would keep the paise)

# How many panels?  The count whose total watts are NEAREST the requested size (3 kW / 540 W: 5 x 540 = 2,700 W or
# 6 x 540 = 3,240 W -> 6).  This optional limit says how far BELOW the requested size the total may be:
#     100 = no limit: simply the nearest count  (the rule in force)
#     2.5 = never more than 2.5% under (3 kW / 580 W would then be 6 panels instead of 5);   0 = always round up
PANEL_SHORTFALL_ALLOWED_PERCENT = Decimal("100")

# A panel count typed in by hand (panel_quantity_manual) replaces the calculated one.  Limits for what can be typed, and the
# size of a gap between the panels' total watts and the requested size that is worth a warning (a typo such as 60 for 6).
MAX_MANUAL_PANELS = 500
MANUAL_PANELS_WARN_PERCENT = Decimal("20")

# Predefined BOS (balance of system) amount added ONCE to every quotation's cost.
# It replaces the individual BOS rows (sockets, glands, clamps ...), which are never added.
# The amount depends on the plant size (kW) and the phase:  3 kW 10,000 | 5 kW 1-phase 12,000 | 5 kW 3-phase 15,000 | 8 kW 15,000.
# key = (kW, "1PH" / "3PH" / None);  None = any phase.  A size that is not listed uses BOS_FIXED_AMOUNT.
BOS_AMOUNTS = {
    (Decimal("3"), None): Decimal("10000"),
    (Decimal("5"), "1PH"): Decimal("12000"),
    (Decimal("5"), "3PH"): Decimal("15000"),
    (Decimal("8"), None): Decimal("15000"),
}
BOS_FIXED_AMOUNT = Decimal("10000")

# Earth rods are always 3 nos (no box on the page any more).
EARTH_ROD_QUANTITY = Decimal("3")

# A structure kW typed on the quotation (8 -> 8,000 W) replaces the panels' total watts in the structure calculation.
MAX_STRUCTURE_KW = Decimal("100")

DEFAULT_STRUCTURE_FACTOR_3_4 = Decimal("3")        # structure wage: Rs per watt for 3 kW and 4 kW systems
DEFAULT_STRUCTURE_FACTOR_5_PLUS = Decimal("2.5")   # ... and for 5 kW and above (both editable in StructureWageSetting)
ROOF_FIXED_FEET = Decimal("2")
GI_EXTRA_FEET = Decimal("2")       # a GI structure is priced for its selected height + 2 ft (4 ft -> 6 ft x watts)
# Per plant size, the feet added to the selected height (default: GI +2, GP 0).
# 3 kW only: GI = the selected height itself (4 ft -> 4), GP = the selected height minus 1 (4 ft -> 3).
STRUCTURE_FEET_ADJUST = {Decimal("3"): {"gi": Decimal("0"), "gp": Decimal("-1")}}

# Cable lengths for the two per-metre components that have no box on the page.
UG_CABLE_METRES = Decimal("30")       # AC UG cable, ACDB to metering panel (the length printed on the sample quotation)
EARTHING_CABLE_METRES = Decimal("20")  # earthing cable length (m).  ASSUMED - the sheet gives only the rate (Rs 28/m); change it here

ZERO = Decimal("0")
HUNDRED = Decimal("100")

# Words in a QuotationItem description that tell us where its cost really belongs
CHARGE_WORDS = ("ELECTRICAL WORK", "TRANSPORT", "KSEB", "LOADING", "DOCUMENTATION", "WAGE")
STRUCTURE_WORDS = ("STRUCTURE", "MOUNTING")

# The BOS table of the rate sheet.  A quotation item whose description matches one of these is a BOS row.
BOS_ITEM_PATTERNS = [
    r"\bSOCKET\b",                       # Aluminum Socket, Copper Socket, Socket
    r"\bCABLE GLAND\b", r"\bEARTH PIT\b", r"\bISOLATOR\b", r"\bEND CAP\b", r"\bMID CLAMP\b", r"\bEND CLAMP\b",
    r"\bSADDLE\b", r"\bELBOW\b", r"\bTEE\b", r"\bBEND\b", r"\bCABLE TIE\b", r"\bCOND[UI]+LT\b", r"\bCONDUIT",
    r"\bCYCLE SCREW\b", r"\bDRY WALL SCREW\b", r"\bEARTH BENCH\b", r"\bINSULATION TAP",
    r"\bMC4\b", r"\bSCREW PLUG\b", r"\bNUT (AND|&) BOLT\b", r"\bCABLE TRAY\b", r"\bCONCRE",
    r"\bEARTHING COMPOUND\b", r"\bFLEXIBLE PIPE\b", r"\bFERRULE|\bFERULE", r"\bPANEL TO PANEL\b",
    r"\bCLEANING\b", r"\bWALKWAY\b", r"\bHANDRAIL\b",
]
_BOS_REGEX = re.compile("|".join(BOS_ITEM_PATTERNS))


# =========================================================
# SMALL HELPERS
# =========================================================

def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalized_text(value):
    return clean_text(value).upper()


def decimal_or_zero(value):
    if value is None:
        return ZERO
    value = clean_text(value)
    if not value:
        return ZERO
    try:
        return Decimal(value)
    except Exception:
        return ZERO


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def plain_number(value):
    """Decimal('50.00') -> '50',  Decimal('2.50') -> '2.5'  (for form inputs and labels)."""
    d = Decimal(str(value if value is not None else 0))
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def bos_amount_for(system_size, phase_token):
    """BOS amount for a plant: (size, phase) first, then (size, any phase), then BOS_FIXED_AMOUNT."""
    size = decimal_or_zero(system_size)
    for key in ((size, phase_token), (size, None)):
        if key in BOS_AMOUNTS:
            return BOS_AMOUNTS[key]
    return BOS_FIXED_AMOUNT


def parse_structure_kw(raw):
    """
    What was typed in the "Structure kW" box -> (Decimal kW or None, problem text).
    Empty = None: the structure uses the panels' total watts.  Otherwise a number above 0 and up to MAX_STRUCTURE_KW.
    """
    text = clean_text(raw)
    if text == "":
        return None, ""
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "The structure kW must be a number."
    if not number.is_finite() or number <= 0 or number > MAX_STRUCTURE_KW:
        return None, "The structure kW must be more than 0 and not more than %s." % plain_number(MAX_STRUCTURE_KW)
    return number, ""


def structure_kind(value):
    """'Roof Mounted' / 'roof' -> 'roof',  'GP' -> 'gp',  'GI' -> 'gi'  (old and new stored values both work)."""
    text = normalized_text(value).lower()
    if text.startswith("roof"):
        return "roof"
    if text.startswith("gp"):
        return "gp"
    if text.startswith("gi"):
        return "gi"
    return ""


# =========================================================
# WHAT KIND OF QUOTATION ITEM IS THIS?
# =========================================================

def item_kind(item):
    """module / bos / inverter / dc_cable / ac_wire / earth / structure / charge / other."""
    description = normalized_text(getattr(item, "description", ""))
    if any(word in description for word in CHARGE_WORDS):
        return "charge"
    if any(word in description for word in STRUCTURE_WORDS):
        return "structure"
    if "MODULE" in description and "CLEAN" not in description:
        return "module"
    if _BOS_REGEX.search(description):
        return "bos"
    if "INVERTER" in description and "CABLE" not in description and "WIRE" not in description:
        return "inverter"
    if "DC CABLE" in description or "DC WIRE" in description:
        return "dc_cable"
    if "AC WIRE" in description or "FR COPPER" in description:
        return "ac_wire"
    if "EARTH" in description:
        return "earth"
    return "other"


_FIND_KINDS = {
    "INVERTER": "inverter",
    "DC_CABLE": "dc_cable",
    "AC_WIRE": "ac_wire",
    "MODULE": "module",
    "EARTH": "earth",
    "EARTH ROD": "earth",
}


def find_quotation_item(quotation, item_type):
    """First quotation item of a dedicated kind (INVERTER, DC_CABLE, AC_WIRE, MODULE, EARTH)."""
    wanted = _FIND_KINDS.get(normalized_text(item_type))
    if wanted is None:
        return None
    for item in sorted(quotation.items.all(), key=lambda i: i.id):
        if item_kind(item) == wanted:
            return item
    return None


# =========================================================
# PANEL QUANTITY  (the count whose total watts are NEAREST the requested size:  3 kW / 540 W = 5.56 -> 6 panels (3,240 W)
#                  rather than 5 (2,700 W);   3 kW / 580 W = 5.17 -> 5 panels (2,900 W) rather than 6 (3,480 W))
# =========================================================

def calculate_panel_quantity(system_size, wattage):
    system_size = decimal_or_zero(system_size)
    wattage = decimal_or_zero(wattage)
    if system_size <= 0 or wattage <= 0:
        return ZERO
    required_panels = system_size * Decimal("1000") / wattage
    nearest = required_panels.quantize(Decimal("1"), rounding=ROUND_HALF_UP)      # nearest whole panel, halves up
    # the fewest panels that are not more than the allowed % below the requested size
    smallest_allowed = (required_panels * (HUNDRED - PANEL_SHORTFALL_ALLOWED_PERCENT) / HUNDRED).quantize(Decimal("1"), rounding=ROUND_CEILING)
    return max(nearest, smallest_allowed, Decimal("1"))                           # a plant always has at least one panel


def parse_manual_panels(raw):
    """
    What was typed in the "Number of Panels" box -> (whole number or None, problem text).
    An empty box means None: the system calculates the number.  Anything else must be a whole number from 1 to MAX_MANUAL_PANELS.
    """
    text = clean_text(raw)
    if text == "":
        return None, ""
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "The number of panels must be a whole number."
    if not number.is_finite() or number != number.to_integral_value():
        return None, "The number of panels must be a whole number."
    if number < 1 or number > MAX_MANUAL_PANELS:
        return None, "The number of panels must be between 1 and %d." % MAX_MANUAL_PANELS
    return int(number), ""


# =========================================================
# STRUCTURE: material and wage (both calculated)
# =========================================================

def get_structure_wage_factor(system_size):
    """3 / 4 kW -> 3,  5 kW and above -> 2.5   (editable in StructureWageSetting)."""
    from .models import StructureWageSetting      # imported here so this module can be tested without Django

    size = decimal_or_zero(system_size)
    if size >= Decimal("5"):
        setting_name, default_factor = "5 KW AND ABOVE", DEFAULT_STRUCTURE_FACTOR_5_PLUS
    else:
        setting_name, default_factor = "3 KW / 4 KW", DEFAULT_STRUCTURE_FACTOR_3_4

    setting, _ = StructureWageSetting.objects.get_or_create(
        name=setting_name, defaults={"factor": default_factor, "is_active": True})
    return setting.factor if setting.is_active else default_factor


def calculate_structure(quotation, structure_watts):
    """
    -> (material cost, calculated wage, wage factor, feet)
    material = feet x structure watts   roof 2 ft | GP selected height | GI selected height + 2 ft (no height selected -> 0)
    wage     = wage factor x structure watts
    structure watts = the panels' total watts, or the structure kW typed on the quotation x 1,000
    """
    wage_factor = get_structure_wage_factor(quotation.system_size)
    kind = structure_kind(quotation.structure_type)
    selected_feet = decimal_or_zero(quotation.structure_feet)

    if kind == "roof":
        feet = ROOF_FIXED_FEET
    elif kind in ("gp", "gi"):
        adjust = STRUCTURE_FEET_ADJUST.get(decimal_or_zero(quotation.system_size), {})
        add = adjust.get(kind, GI_EXTRA_FEET if kind == "gi" else ZERO)
        feet = max(selected_feet + add, ZERO) if selected_feet > 0 else ZERO
    else:
        feet = ZERO

    if structure_watts > 0:
        return money(feet * structure_watts), money(wage_factor * structure_watts), wage_factor, feet
    return ZERO, ZERO, wage_factor, feet


# =========================================================
# FINAL GST
# =========================================================

def calculate_gst(amount):
    return money(money(amount) * GST_RATE / HUNDRED)


# =========================================================
# THE CALCULATION
# =========================================================

def _line(key, label, amount, note=""):
    return {"key": key, "label": label, "amount": money(amount), "note": note}


# The rate-sheet components priced at a fixed quantity or a fixed length.
# (key, label, Product category, name prefix, phase specific?, quantity)
RATE_SHEET_COMPONENTS = [
    ("acdb", "ACDB", "acdb", "ACDB", True, Decimal("1")),
    ("dcdb", "DCDB", "dcdb", "DCDB", True, Decimal("1")),
    ("meter_box", "Meter box", "meter_box", "METER BOX", True, Decimal("1")),
    ("ug_cable", "AC UG cable", "ug_cable", "UG CABLE", True, "UG_CABLE_METRES"),
    ("earthing_cable", "Earthing cable", "earthing", "EARTHING CABLE", False, "EARTHING_CABLE_METRES"),
    ("lightning_arrestor", "Lightning arrestor", "electrical", "LIGHTNING ARRESTOR", False, Decimal("1")),
    ("energy_meter", "Energy meter", "energy_meter", "ENERGY METER", True, Decimal("1")),
    ("net_meter", "Net meter", "net_meter", "NET METER", True, Decimal("1")),
]

COMPONENT_WORDS = ("ACDB", "DCDB", "METER", "UG CABLE", "EARTHING", "LIGHTNING", "ARREST", "ENERGY")


def find_product(category, name=None, prefix=None, contains=(), capacity=None):
    """
    THE ONLY DATABASE LOOKUP OF THE RATE SHEET.  Returns an active Product or None.
    name = exact name, prefix = name starts with, contains = every text must be in the name, capacity = inverter kW.
    """
    from .models import Product                      # imported here so this module can be tested without Django

    queryset = Product.objects.filter(category=category, is_active=True)
    if name:
        queryset = queryset.filter(name__iexact=name)
    if prefix:
        queryset = queryset.filter(name__istartswith=prefix)
    for text in contains:
        queryset = queryset.filter(name__icontains=text)
    if capacity is not None:
        queryset = queryset.filter(inverter_capacity=capacity)
    return queryset.order_by("name").first()


def inverter_traits(name, capacity=None):
    """
    kW, phase and number of MPPT trackers of an inverter, read from the INVERTER (its product), not from the plant:
    'POLYCAB 5KW 1PH DUAL' -> 5 kW, SINGLE phase, 2 MPPT.   A 3 kW three-phase plant can have a 5 kW single-phase inverter.
    phase is None when the name does not say.
    """
    upper = clean_text(name).upper()
    if "3PH" in upper or "THREE PHASE" in upper:
        phase = "THREE"
    elif "1PH" in upper or "SINGLE PHASE" in upper:
        phase = "SINGLE"
    else:
        phase = None
    kw = decimal_or_zero(capacity)
    if kw <= 0:
        found = re.search(r"(\d+(?:\.\d+)?)\s*KW", upper)
        kw = Decimal(found.group(1)) if found else ZERO
    return {"capacity": kw if kw > 0 else None, "phase": phase, "mppt": 2 if "DUAL" in upper else 1}


def rate_sheet_requirements():
    """
    What the price calculation needs from the rate sheet, and whether each rate is in the database.
    -> list of {"label", "category", "product"}  (product is None when it is missing).
    Uses the same lookups as the calculation itself.
    """
    rows = [{"label": "DC cable 4 SQMM", "category": "dc_cable", "product": find_product("dc_cable", name="4 SQMM")},
            {"label": "AC wire 4 SQMM FR Copper", "category": "ac_wire", "product": find_product("ac_wire", prefix="4 SQMM FR Copper")},
            {"label": "Earth rod", "category": "earthing", "product": find_product("earthing", prefix="EARTH ROD")}]
    for key, label, category, prefix, by_phase, quantity in RATE_SHEET_COMPONENTS:
        if not by_phase:
            rows.append({"label": label, "category": category, "product": find_product(category, prefix=prefix)})
    for token, sizes in (("1PH", (3, 5, 8)), ("3PH", (5, 8))):             # the combinations that are sold: 3, 5 and 8 kW single phase, 5 and 8 kW three phase
        for kw in sizes:
            rows.append({"label": "Inverter %s kW %s" % (kw, token), "category": "inverter",
                         "product": find_product("inverter", capacity=Decimal(kw), contains=(token,))})
        for key, label, category, prefix, by_phase, quantity in RATE_SHEET_COMPONENTS:
            if not by_phase:
                continue
            if key == "ug_cable":
                product = find_product(category, prefix="%s %s" % (prefix, "4C" if token == "3PH" else "2C"))
            else:
                product = find_product(category, prefix=prefix, contains=(token,))
            rows.append({"label": "%s %s" % (label, token), "category": category, "product": product})
    return rows


def rate_sheet_report():
    """The same check as (label, Product or None) pairs."""
    return [(r["label"], r["product"]) for r in rate_sheet_requirements()]


def _phase_token(quotation):
    return "3PH" if "three" in clean_text(quotation.phase).lower() else "1PH"


def margin_factor_for(quotation):
    """
    The margin factor of the quotation's plant size (3 kW -> 83.5, 5 kW -> 85 ...), as typed in the costing sheet.
    A size that is not listed uses DEFAULT_MARGIN_FACTOR.  MARGIN_EXTRA_GP_POINTS is taken off the factor (one more point of GP).
    Whatever margin is stored on an old quotation is NOT used, so changing the factors changes every quotation the next time
    it is opened or printed.
    """
    size = decimal_or_zero(quotation.system_size)
    if size in FIXED_MARGIN_FACTORS:
        return FIXED_MARGIN_FACTORS[size]
    factor = MARGIN_FACTORS.get(size, DEFAULT_MARGIN_FACTOR) - MARGIN_EXTRA_GP_POINTS
    return factor if ZERO < factor <= HUNDRED else DEFAULT_MARGIN_FACTOR


def round_to_nearest(amount, step=None):
    """Rs 387,420 -> Rs 387,400   (nearest Rs 100, ROUND_HALF_UP)."""
    step = step or ROUND_FINAL_TO
    return money((Decimal(amount) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def _item_note(item):
    """Why a package item is not part of the price (the page lists these so nothing is hidden)."""
    kind = item_kind(item)
    description = normalized_text(getattr(item, "description", ""))
    if kind == "bos":
        return "included in the fixed BOS amount"
    if kind == "module":
        return "panel cost comes from the selected panel"
    if kind == "structure":
        return "structure cost is calculated from the structure rules"
    if kind == "charge":
        return "counted in the additional charges"
    if kind in ("inverter", "dc_cable", "ac_wire", "earth") or any(w in description for w in COMPONENT_WORDS):
        return "priced from the rate sheet (see the list on the left)"
    return "not priced - it is not in the rate sheet"


def _compute(quotation):
    """Calculates everything in one place and returns a dict.  Changes nothing."""
    warnings = []
    token = _phase_token(quotation)

    # ---- 1-4. PANEL: quantity is ALWAYS recalculated (nearest whole number), then total watts and cost ----
    panel = quotation.panel_option
    auto_panels = calculate_panel_quantity(quotation.system_size, panel.wattage) if panel is not None else ZERO
    manual_panels = decimal_or_zero(getattr(quotation, "panel_quantity_manual", None))          # None / 0 = calculated by the system
    panel_is_manual = panel is not None and manual_panels >= 1
    panel_quantity = manual_panels.quantize(Decimal("1"), rounding=ROUND_HALF_UP) if panel_is_manual else auto_panels

    panel_total_watt = ZERO
    panel_value = ZERO
    panel_tax_display = ZERO
    panel_note = ""
    if panel is not None and panel_quantity > 0:
        panel_total_watt = Decimal(panel.wattage) * panel_quantity
        panel_value = money(panel_total_watt * Decimal(panel.rate_per_watt))
        panel_tax_display = money(panel_value * decimal_or_zero(getattr(panel, "tax_percent", 0)) / HUNDRED)   # display only
        panel_note = "%s panels x %s W x Rs %s per watt" % (
            plain_number(panel_quantity), plain_number(panel.wattage), plain_number(panel.rate_per_watt))
        requested_watts = decimal_or_zero(quotation.system_size) * Decimal("1000")
        if panel_is_manual and requested_watts > 0:                                                 # a typo such as 60 instead of 6
            gap = (panel_total_watt - requested_watts) / requested_watts * HUNDRED
            if abs(gap) > MANUAL_PANELS_WARN_PERCENT:
                warnings.append("The %s panels entered by hand add up to %s W, which is %s%% %s the %s kW system size (the system calculated %s panels). Check the number."
                                % (plain_number(panel_quantity), plain_number(panel_total_watt), plain_number(abs(gap).quantize(Decimal("1"))),
                                   "above" if gap > 0 else "below", plain_number(quotation.system_size), plain_number(auto_panels)))
    else:
        warnings.append("No panel is selected, so the panel cost is 0.")

    # ---- 5-8. THE USER'S SELECTION: inverter, DC cable, AC wire, earth and the other components --------
    # Each is priced from the rate sheet (Excel products).  The package items on the quotation are never priced.
    components = {}                    # key -> {name, make, quantity, rate, amount, unit}
    lines_components = []

    def price(key, label, product, quantity, note_if_missing, unit="Nos"):
        quantity = Decimal(quantity or 0)
        if product is None:
            warnings.append(note_if_missing)
            components[key] = {"name": "", "make": "", "quantity": quantity, "rate": ZERO, "amount": ZERO, "unit": unit}
            lines_components.append(_line(key, label, ZERO, "no rate found"))
            return
        rate = Decimal(product.rate)
        amount = money(quantity * rate)
        components[key] = {"name": product.name, "make": (product.make or "").strip(), "quantity": quantity,
                           "rate": rate, "amount": amount, "unit": unit}
        lines_components.append(_line(key, label, amount, "%s: %s x Rs %s" % (product.name, plain_number(quantity), plain_number(rate))))

    selected = {"inverter_type": clean_text(quotation.inverter_type), "dc_cable": clean_text(quotation.dc_cable),
                "ac_wire": clean_text(quotation.ac_wire)}

    inverter_kw = decimal_or_zero(quotation.inverter_kw) or Decimal(quotation.system_size or 0)
    if selected["inverter_type"].lower() == "other":
        rate = decimal_or_zero(quotation.inverter_rate)
        components["inverter"] = {"name": clean_text(quotation.inverter_make) or "Other inverter", "make": clean_text(quotation.inverter_make),
                                  "quantity": Decimal("1"), "rate": rate, "amount": money(rate), "unit": "Nos",
                                  "capacity": inverter_kw or None, "phase": None, "mppt": 1}
        lines_components.append(_line("inverter", "Inverter", rate, "other inverter, rate entered by hand"))
        if rate <= 0:
            warnings.append("'Other' inverter selected but no rate was entered.")
    else:
        inverter = find_product("inverter", name=selected["inverter_type"]) if selected["inverter_type"] else None
        if inverter is None:
            inverter = find_product("inverter", capacity=inverter_kw, contains=(token,))
            if inverter is None:                                                     # e.g. an inverter whose name does not say the phase
                inverter = find_product("inverter", capacity=inverter_kw)
            if selected["inverter_type"] and inverter is not None:
                warnings.append("Inverter '%s' is not in the rate sheet; %s was used instead." % (selected["inverter_type"], inverter.name))
        price("inverter", "Inverter", inverter, 1,
              "No inverter rate found for %s kW %s. Add it in Admin > Products (category inverter, capacity %s, name containing %s)."
              % (plain_number(inverter_kw), token, plain_number(inverter_kw), token))
        if inverter is not None:
            selected["inverter_type"] = inverter.name
            traits = inverter_traits(inverter.name, getattr(inverter, "inverter_capacity", None))
            components["inverter"].update(traits)
            if traits["capacity"]:
                inverter_kw = traits["capacity"]                  # the inverter's own kW, whatever the plant size

    dc_cable = find_product("dc_cable", name=selected["dc_cable"]) if selected["dc_cable"] else None
    if dc_cable is None:
        dc_cable = find_product("dc_cable", name="4 SQMM")
        if selected["dc_cable"] and dc_cable is not None:
            warnings.append("DC cable '%s' is not in the rate sheet; %s was used instead." % (selected["dc_cable"], dc_cable.name))
    if dc_cable is not None:
        selected["dc_cable"] = dc_cable.name
    price("dc_cable", "DC cable", dc_cable, decimal_or_zero(quotation.dc_cable_quantity),
          "No DC cable rate found (4 SQMM). Add it in Admin > Products (category dc_cable).", "m")

    ac_wire = find_product("ac_wire", name=selected["ac_wire"]) if selected["ac_wire"] else None
    if ac_wire is None:
        ac_wire = find_product("ac_wire", prefix="4 SQMM FR Copper")
        if selected["ac_wire"] and ac_wire is not None:
            warnings.append("AC wire '%s' is not in the rate sheet; %s was used instead." % (selected["ac_wire"], ac_wire.name))
    if ac_wire is not None:
        selected["ac_wire"] = ac_wire.name
    price("ac_wire", "AC wire", ac_wire, decimal_or_zero(quotation.ac_wire_quantity),
          "No AC wire rate found (4 SQMM FR Copper). Add it in Admin > Products (category ac_wire).", "m")

    price("earth_rod", "Earth rod", find_product("earthing", prefix="EARTH ROD"), EARTH_ROD_QUANTITY,
          "No earth rod rate found. Add it in Admin > Products (category earthing, name starting EARTH ROD).")

    for key, label, category, prefix, by_phase, quantity in RATE_SHEET_COMPONENTS:
        if key == "ug_cable":
            product = find_product(category, prefix="%s %s" % (prefix, "4C" if token == "3PH" else "2C"))     # 1PH -> 2 core, 3PH -> 4 core
        elif by_phase:
            product = find_product(category, prefix=prefix, contains=(token,))
        else:
            product = find_product(category, prefix=prefix)
        unit = "m" if key in ("ug_cable", "earthing_cable") else "Nos"
        if isinstance(quantity, str):
            quantity = globals()[quantity]
            if quantity is None:
                warnings.append("%s length is not set (EARTHING_CABLE_METRES in calculations.py), so its cost is 0." % label)
                quantity = ZERO
        price(key, label, product, quantity,
              "No %s rate found%s. Add it in Admin > Products (category %s, name starting %s)." %
              (label.lower(), " for %s" % token if by_phase else "", category, prefix), unit)

    components_total = money(sum((c["amount"] for c in components.values()), ZERO))
    bos_amount = money(bos_amount_for(quotation.system_size, token))

    # ---- 9-10. STRUCTURE: material, then wage (a hand-entered wage replaces the calculated one) ---------
    # structure watts = the panels' total watts, unless a structure kW was typed (8 -> 8,000 W)
    structure_kw_manual = decimal_or_zero(getattr(quotation, "structure_kw_manual", None))
    structure_is_manual = structure_kw_manual > 0
    structure_watts = structure_kw_manual * Decimal("1000") if structure_is_manual else panel_total_watt
    structure_material, calculated_wage, wage_factor, feet = calculate_structure(quotation, structure_watts)

    stored_work = Decimal(quotation.structure_work or 0)
    previous_calculated_wage = Decimal(quotation.structure_wage or 0)
    wage_is_manual = stored_work != 0 and stored_work != previous_calculated_wage
    structure_work = money(stored_work) if wage_is_manual else calculated_wage

    # ---- 11. ADDITIONAL CHARGES (structure_work is the wage above) --------------------------------------
    charge_lines = [
        _line("electrical_work", "Electrical work", decimal_or_zero(quotation.electrical_work)),
        _line("transportation_travel", "Transportation / travel", decimal_or_zero(quotation.transportation_travel)),
        _line("kseb_fee", "KSEB fee", decimal_or_zero(quotation.kseb_fee)),
        _line("loading_charge", "Loading charge", decimal_or_zero(quotation.loading_charge)),
        _line("documentation", "Documentation", decimal_or_zero(quotation.documentation)),
    ]
    structure_note = "%s ft x %s W%s" % (plain_number(feet), plain_number(structure_watts), " (structure kW entered by hand)" if structure_is_manual else "")

    # ---- 12. TOTAL COST = the selection (with the structure and its wage) + BOS + the prefixed non-taxables ----
    lines = [_line("panel", "Solar panels", panel_value, panel_note)] + lines_components + [
        _line("structure_material", "Structure material", structure_material, structure_note),
        _line("structure_work", "Structure wage", structure_work,
              "entered by hand" if wage_is_manual else "Rs %s per watt x %s W" % (plain_number(wage_factor), plain_number(structure_watts))),
        _line("bos", "BOS total (fixed for %s kW)" % plain_number(decimal_or_zero(quotation.system_size)), bos_amount),
    ] + charge_lines
    calculated_cost = money(sum((l["amount"] for l in lines), ZERO))

    # ---- 13-15. SELLING PRICE = cost / factor x 100 (the sheet's "Cost+Margine"), margin = the difference, GST 9% of it ----
    margin_factor = margin_factor_for(quotation)
    selling_price = money(calculated_cost * HUNDRED / margin_factor)
    margin_amount = money(selling_price - calculated_cost)
    gp_percent = HUNDRED - margin_factor                          # the margin as a share of the SELLING price
    gst_amount = calculate_gst(selling_price)
    suggested_price = money(selling_price + gst_amount)

    # ---- 16. FINAL PRICE: the amount above rounded to the nearest Rs 100, unless a price was typed in by hand ----
    auto_final = round_to_nearest(suggested_price)
    stored_final = Decimal(quotation.final_quotation_price or 0)
    previous_suggested = Decimal(quotation.suggested_quotation_price or 0)
    # a stored price equal to the previous calculated price - or to it rounded to the nearest Rs 100, which is what the
    # earlier version stored - was automatic, so it follows the new calculation.  Anything else was typed in by hand.
    previous_autos = (previous_suggested, round_to_nearest(previous_suggested, Decimal("100")) if previous_suggested else ZERO)
    final_is_manual = stored_final != 0 and stored_final not in previous_autos
    final_price = money(stored_final) if final_is_manual else auto_final

    # a hand-entered price far from the calculated one is almost always a slip (a missing digit): say so loudly
    if final_is_manual and suggested_price > 0:
        gap = abs(final_price - suggested_price) / suggested_price
        if gap > Decimal("0.10"):
            warnings.append(
                "The Final Quotation Price (Rs %s) was entered by hand and is %s%% away from the calculated price (Rs %s). "
                "Clear the Final Quotation Price box and save to use the calculated price."
                % (plain_number(final_price), plain_number((gap * HUNDRED).quantize(Decimal("1"))), plain_number(suggested_price)))

    # ---- what the page shows for checking ---------------------------------------------------------------------
    counted_items = [{"name": c["name"], "quantity": c["quantity"], "rate": c["rate"], "amount": c["amount"]}
                     for c in components.values() if c["amount"] > 0]
    display_only_items = [{"name": (i.description or "").strip(), "note": _item_note(i)}
                          for i in sorted(quotation.items.all(), key=lambda i: i.id)]

    return {
        "lines": lines, "warnings": warnings, "components": components, "selected": selected,
        "counted_items": counted_items, "display_only_items": display_only_items,
        "panel_quantity": panel_quantity, "panel_quantity_auto": auto_panels, "panel_quantity_is_manual": panel_is_manual,
        "panel_total_watt": panel_total_watt, "panel_value": panel_value,
        "panel_tax_amount": panel_tax_display,
        "components_total": components_total, "bos_amount": bos_amount, "structure_note": structure_note,
        "structure_watts": structure_watts, "structure_watts_auto": panel_total_watt, "structure_is_manual": structure_is_manual,
        "inverter_kw": inverter_kw,
        "structure_cost": structure_material, "structure_wage_factor": wage_factor,
        "calculated_structure_wage": calculated_wage, "structure_work": structure_work, "wage_is_manual": wage_is_manual,
        "calculated_cost": calculated_cost,
        "margin_factor": margin_factor, "margin_percent": gp_percent, "margin_amount": margin_amount,
        "selling_price": selling_price,
        "gst_rate": GST_RATE, "gst_amount": gst_amount,
        "suggested_price": suggested_price, "final_price": final_price, "final_is_manual": final_is_manual,
        "round_off": final_price - suggested_price,
    }


def quotation_profit(final_price, cost):
    """
    What a quotation earns: the final price WITHOUT the GST, minus the cost  ->  price / (1 + GST%) - cost.
    The GST belongs to the tax office, not to us.  This stays right when the final price was edited by hand, and for an
    automatic price it equals the margin.  A quotation with no price yet (0) earns nothing - it is not "minus its cost".
    """
    final_price = decimal_or_zero(final_price)
    if final_price <= 0:
        return ZERO
    return money(final_price / (1 + GST_RATE / HUNDRED) - decimal_or_zero(cost))


def calculate_quotation(quotation):
    """
    Calculate the quotation, store every value on it, save it and return it.
    quotation.cost_breakdown (not saved) holds the line-by-line breakdown for the detail page and the PDF.
    """
    r = _compute(quotation)

    # ---- panel ----
    if quotation.panel_option is not None:
        quotation.panel_quantity = r["panel_quantity"]
        quotation.panel_rate_per_watt = quotation.panel_option.rate_per_watt
    else:
        quotation.panel_quantity = ZERO                         # no panel selected: no panels (whatever was stored before)
        quotation.panel_rate_per_watt = ZERO
    quotation.panel_total_watt = r["panel_total_watt"]
    quotation.panel_base_amount = r["panel_value"]
    quotation.panel_tax_amount = r["panel_tax_amount"]          # for display only: never added to the price
    quotation.panel_total_amount = r["panel_value"]

    quotation.earth_quantity = EARTH_ROD_QUANTITY               # always 3 nos (the PDF prints this)

    # ---- structure ----
    quotation.structure_cost = r["structure_cost"]
    quotation.structure_wage_factor = r["structure_wage_factor"]
    quotation.structure_wage = r["calculated_structure_wage"]   # the calculated value
    quotation.structure_work = r["structure_work"]              # the amount actually used (hand-entered or calculated)
    quotation.structure_total = money(r["structure_cost"] + r["structure_work"])

    # ---- BOQ / package items: boq_total = 0 ----
    boq = money(r["components_total"] + r["bos_amount"])
    quotation.component_base_amount = boq
    quotation.component_tax_amount = ZERO
    quotation.component_total_amount = boq

    # ---- cost, selling price, GST, final price ----
    quotation.taxable_cost = r["calculated_cost"]
    quotation.non_taxable_cost = ZERO
    quotation.calculated_cost = r["calculated_cost"]
    quotation.margin_percent = r["margin_percent"]               # GP %: the margin as a share of the selling price
    quotation.margin_amount = r["margin_amount"]
    if hasattr(quotation, "margin_factor"):
        quotation.margin_factor = r["margin_factor"]
    quotation.calculated_selling_price = r["selling_price"]
    quotation.gst_amount = r["gst_amount"]
    quotation.suggested_quotation_price = r["suggested_price"]
    quotation.final_quotation_price = r["final_price"]

    # ---- the selections shown on the page and printed in the PDF ----
    quotation.inverter_type = r["selected"]["inverter_type"]
    quotation.dc_cable = r["selected"]["dc_cable"]
    quotation.ac_wire = r["selected"]["ac_wire"]
    quotation.inverter_kw = r["inverter_kw"]
    inverter = r["components"]["inverter"]
    quotation.inverter_make = inverter["make"]
    quotation.inverter_rate = inverter["rate"]
    quotation.save()

    quotation.cost_breakdown = r
    return quotation