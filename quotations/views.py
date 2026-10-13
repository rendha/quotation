"""
quotations/views.py

HTTP only:  read the form  ->  save selections / quantities  ->  calculate_quotation(quotation)
            ->  render / redirect / PDF.

No money is calculated here.  Every amount comes from quotations/calculations.py.
"""
import hmac
import os
import time
from decimal import Decimal

from django.core import signing
from django.db import transaction
from django.contrib.auth.decorators import login_not_required
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .calculations import (
    labour_amounts,
    material_list,
    PANEL_SHORTFALL_ALLOWED_PERCENT,
    calculate_panel_quantity,
    parse_manual_panels,
    parse_structure_kw,
    calculate_quotation,
    clean_text,
    decimal_or_zero,
    find_quotation_item,
    normalized_text,
    plain_number,
    structure_kind,
)
from .models import (
    PanelOption,
    Product,
    Quotation,
    QuotationItem,
    SolarPackage,
)
from . import dashboard_stats as stats
from .filenames import pdf_filename
from .pdf_generator import build_quotation_pdf


# =========================================================
# PANEL TYPE
# =========================================================
# Only DCR panels are in the rate sheet for now, so the create page does not ask for the panel type.
# To ask for it again later, put the DCR / Non-DCR radio buttons back on the page (they post "panel_type").

DEFAULT_PANEL_DCR_STATUS = "dcr"


def _people_names():
    """Every person who already has a quotation, once - offered as suggestions under the "Quotation For" box (same spelling = one person)."""
    return stats.distinct_names(Quotation.objects.exclude(customer_name="").values_list("customer_name", flat=True))


def _model_has_field(model, name):
    """True when the model has this field (the page offers the manual panel number only once the field has been added and migrated)."""
    return any(field.name == name for field in model._meta.get_fields())


# =========================================================
# ADMIN PASSKEY  (no login: the passkey only decides whether the rates, margin and charges are shown)
# =========================================================
# Set the passkey in the environment variable ADMIN_PASSKEY (Render: Environment).  Nothing is shown to anybody while it is not set.
# Entering it stores a signed cookie on that device for RATES_UNLOCK_HOURS hours.

RATES_COOKIE = "rates_unlock"
RATES_SALT = "dehlsen-rates-v1"
RATES_UNLOCK_HOURS = 8


def rates_unlocked(request):
    """True when this browser entered the right passkey in the last RATES_UNLOCK_HOURS hours."""
    token = request.COOKIES.get(RATES_COOKIE)
    if not token:
        return False
    try:
        return signing.loads(token, salt=RATES_SALT, max_age=RATES_UNLOCK_HOURS * 3600) == "ok"
    except signing.BadSignature:
        return False


def _safe_next(request, fallback):
    """Only go back to a page of this site."""
    target = request.POST.get("next", "")
    return target if target.startswith("/") and not target.startswith("//") else fallback


def unlock_rates(request):
    if request.method != "POST":
        return redirect("quotation_dashboard")
    passkey = os.environ.get("ADMIN_PASSKEY", "")
    given = request.POST.get("passkey", "")
    target = _safe_next(request, reverse("quotation_dashboard"))
    if passkey and hmac.compare_digest(given.encode(), passkey.encode()):
        response = redirect(target)
        response.set_cookie(RATES_COOKIE, signing.dumps("ok", salt=RATES_SALT), max_age=RATES_UNLOCK_HOURS * 3600,
                            httponly=True, secure=request.is_secure(), samesite="Lax")
        return response
    time.sleep(1)                                           # slows down guessing
    return redirect(target + ("&" if "?" in target else "?") + "passkey=wrong")


def lock_rates(request):
    response = redirect(_safe_next(request, reverse("quotation_dashboard")))
    response.delete_cookie(RATES_COOKIE)
    return response


# =========================================================
# PRODUCT LOOKUP / APPLY PRODUCT
# =========================================================

def find_product_for_selection(selection, category=None):
    """Exact name, exact make, then partial name / make.  The category is preferred when it has products."""
    selection = clean_text(selection)
    if not selection:
        return None

    queryset = Product.objects.filter(is_active=True)

    if category:
        category_qs = queryset.filter(category=category)
        if category_qs.exists():
            queryset = category_qs

    for lookup in ("name__iexact", "make__iexact", "name__icontains", "make__icontains"):
        product = queryset.filter(**{lookup: selection}).first()
        if product:
            return product

    return None


def apply_product_to_item(item, selection, category=None):
    """The selected Product's rate becomes the item's rate (tax fields are kept for old data, never used)."""
    selection = clean_text(selection)

    if not item:
        return None
    if not selection:
        return item

    product = find_product_for_selection(selection, category=category)

    if product:
        item.product = product
        item.make = product.make or selection
        item.specification = product.specification or item.specification
        item.rate = product.rate
        item.tax_percent = product.tax_percent
        item.save(update_fields=["product", "make", "specification", "rate", "tax_percent"])
        return item

    # Product not found: keep the selected text visible but do NOT silently change the rate.
    item.make = selection
    item.save(update_fields=["make"])
    return item


# =========================================================
# FIND SOLAR PACKAGE
# =========================================================

def find_solar_package(system_size, phase):
    """The SolarPackage for this capacity and phase."""
    selected_phase = clean_text(phase).lower()

    for package in SolarPackage.objects.filter(is_active=True):
        capacity_text = clean_text(package.capacity).upper()

        digits = ""
        for character in capacity_text:
            if character.isdigit() or character == ".":
                digits += character
            elif digits:
                break

        if not digits:
            continue

        try:
            package_size = Decimal(digits)
        except Exception:
            continue

        if package_size != system_size:
            continue

        package_phase = clean_text(package.phase).lower()

        if not package_phase:
            return package

        if selected_phase in package_phase or package_phase in selected_phase:
            return package

    return None


# =========================================================
# CREATE QUOTATION
# =========================================================

def _create_error(request, message, posted=None):
    return render(request, "quotations/create_quotation.html", {"error": message, "posted": posted or {}, "people_names": _people_names()})


@transaction.atomic
def create_quotation(request):

    if request.method != "POST":
        posted = {}
        source = Quotation.objects.filter(id=request.GET.get("from") or 0).first() if str(request.GET.get("from") or "").isdigit() else None
        if source is not None:             # "Quote again": the same customer's details, nothing else
            posted = {"business_name": source.business_name, "customer_name": source.customer_name, "phone": source.phone,
                      "email": source.email, "address": source.address, "location": source.location}
        return render(request, "quotations/create_quotation.html", {"posted": posted, "people_names": _people_names(), "quote_again": source is not None})

    posted = {key: clean_text(request.POST.get(key)) for key in (
        "business_name", "customer_name", "phone", "email", "address", "location",
        "phase", "system_size", "panel_type", "structure", "system_type")}

    business_name = posted["business_name"]
    location = posted["location"]
    phase = posted["phase"]
    system_size_raw = posted["system_size"]
    panel_dcr_status = posted["panel_type"] if posted["panel_type"] in ("dcr", "non_dcr") else DEFAULT_PANEL_DCR_STATUS
    structure_type = posted["structure"]
    system_type = posted["system_type"]

    # ---- validation ----
    if not business_name:
        return _create_error(request, "Please enter customer name.", posted)
    if not location:
        return _create_error(request, "Please enter project location.", posted)
    if not phase:
        return _create_error(request, "Please select phase.", posted)
    if not system_size_raw:
        return _create_error(request, "Please select system size.", posted)
    if not structure_type:
        return _create_error(request, "Please select structure.", posted)
    if not system_type:
        return _create_error(request, "Please select system type.", posted)

    try:
        system_size = Decimal(system_size_raw)
    except Exception:
        return _create_error(request, "Invalid system size.", posted)

    if system_size <= 0:
        return _create_error(request, "System size must be greater than zero.", posted)

    selected_package = find_solar_package(system_size, phase)

    quotation = Quotation.objects.create(
        offer_no=f"INQ-{timezone.now().strftime('%Y%m%d%H%M%S%f')}",

        # customer
        business_name=business_name,
        customer_name=posted["customer_name"],
        phone=posted["phone"],
        email=posted["email"],
        address=posted["address"],
        location=location,

        # system
        phase=phase,
        system_size=system_size,
        panel_dcr_status=panel_dcr_status,
        structure_type=structure_type,
        system_type=system_type,
        capacity=system_size_raw,
        date=timezone.localdate(),
        validity_days=15,

        # default editable charges (structure_work 0 = use the calculated wage)
        electrical_work=Decimal("8000"),
        structure_work=Decimal("0"),
        transportation_travel=Decimal("2000"),
        kseb_fee=Decimal("4720"),
        loading_charge=Decimal("1000"),
        documentation=Decimal("2500"),

        solar_package=selected_package,
    )

    # ---- package items: the matching product's rate when it exists, else the package rate ----
    if selected_package:
        for package_item in selected_package.items.all():

            product = Product.objects.filter(name__iexact=package_item.product_name, is_active=True).first()

            if not product and package_item.make:
                product = Product.objects.filter(make__iexact=package_item.make, is_active=True).first()

            QuotationItem.objects.create(
                quotation=quotation,
                product=product,
                description=package_item.product_name,
                specification=(product.specification if product and product.specification else package_item.specification),
                quantity=package_item.quantity,
                make=(product.make if product and product.make else package_item.make),
                rate=product.rate if product else package_item.rate,
                tax_percent=product.tax_percent if product else package_item.tax_percent,
            )

    calculate_quotation(quotation)

    return redirect("quotation_detail", quotation_id=quotation.id)


# =========================================================
# OPTION RULE -> QUOTATION ITEM
# =========================================================

def find_item_for_rule(quotation, rule):
    """1) field name ~ description   2) current value ~ make   3) excel row position."""
    field_name = normalized_text(rule.field_name)
    current_value = normalized_text(rule.current_value)
    items = list(quotation.items.order_by("id"))

    if field_name:
        for item in items:
            description = normalized_text(item.description)
            if field_name == description or field_name in description or description in field_name:
                return item

    if current_value:
        for item in items:
            make = normalized_text(item.make)
            if make and (current_value == make or current_value in make or make in current_value):
                return item

    if rule.excel_row > 0:
        index = rule.excel_row - 1
        if 0 <= index < len(items):
            return items[index]

    return None


# =========================================================
# QUOTATION DETAIL
# =========================================================

def _quantity_from_post(request, name, current):
    """A quantity box left blank keeps the current value; a negative number is ignored."""
    raw = clean_text(request.POST.get(name))
    if raw == "":
        return current
    value = decimal_or_zero(raw)
    return value if value >= 0 else current


@transaction.atomic
def quotation_detail(request, quotation_id):

    quotation = get_object_or_404(Quotation, id=quotation_id)

    panel_options = PanelOption.objects.filter(
        is_active=True,
        dcr_status__iexact=clean_text(quotation.panel_dcr_status),
    ).order_by("company", "panel_type", "wattage")

    if quotation.solar_package:
        option_rules = list(quotation.solar_package.option_rules.filter(is_active=True).order_by("excel_row"))
    else:
        option_rules = []

    # =====================================================
    # POST: save what the user chose, then calculate once
    # =====================================================
    if request.method == "POST":

        # ---- panel (quantity = the nearest whole number of system size / wattage) ----
        panel_option_id = clean_text(request.POST.get("panel_option"))

        if panel_option_id:
            panel_option = get_object_or_404(PanelOption, id=panel_option_id, is_active=True)

            if normalized_text(panel_option.dcr_status) != normalized_text(quotation.panel_dcr_status):
                return HttpResponseBadRequest("Invalid panel DCR selection.")

            quotation.panel_option = panel_option
            quotation.panel_quantity = calculate_panel_quantity(quotation.system_size, panel_option.wattage)
        else:
            quotation.panel_option = None
            quotation.panel_quantity = 0

        # ---- panel number: calculated by the system unless a number is typed in (an empty box = calculated) ----
        if _model_has_field(Quotation, "panel_quantity_manual"):
            manual_panels, problem = parse_manual_panels(request.POST.get("panel_quantity_manual"))
            if problem:
                return HttpResponseBadRequest(problem)
            quotation.panel_quantity_manual = manual_panels

        # ---- inverter ----
        inverter_kw_raw = clean_text(request.POST.get("inverter_kw"))
        quotation.inverter_kw = decimal_or_zero(inverter_kw_raw) if inverter_kw_raw else quotation.system_size

        inverter_type = clean_text(request.POST.get("inverter_type"))
        quotation.inverter_type = inverter_type

        other_inverter_name = clean_text(request.POST.get("other_inverter_name") or request.POST.get("other_inverter"))
        other_inverter_rate = decimal_or_zero(request.POST.get("other_inverter_rate"))

        inverter_item = find_quotation_item(quotation, "INVERTER")

        if inverter_item:
            if inverter_type and inverter_type.lower() != "other":
                apply_product_to_item(inverter_item, inverter_type, category="inverter")
                quotation.inverter_make = inverter_item.make
                quotation.inverter_rate = inverter_item.rate

            elif inverter_type.lower() == "other":
                # the entered name and rate REPLACE the product rate (they are never added to it)
                inverter_item.make = other_inverter_name
                inverter_item.rate = other_inverter_rate
                inverter_item.product = None
                inverter_item.save()
                quotation.inverter_make = other_inverter_name
                quotation.inverter_rate = other_inverter_rate

        # ---- DC cable / AC wire: product + editable quantity ----
        dc_cable = clean_text(request.POST.get("dc_cable"))
        quotation.dc_cable = dc_cable
        dc_cable_item = find_quotation_item(quotation, "DC_CABLE")
        if dc_cable_item and dc_cable:
            apply_product_to_item(dc_cable_item, dc_cable, category="dc_cable")
        quotation.dc_cable_quantity = _quantity_from_post(request, "dc_cable_quantity", quotation.dc_cable_quantity)

        ac_wire = clean_text(request.POST.get("ac_wire"))
        quotation.ac_wire = ac_wire
        ac_wire_item = find_quotation_item(quotation, "AC_WIRE")
        if ac_wire_item and ac_wire:
            apply_product_to_item(ac_wire_item, ac_wire, category="ac_wire")
        quotation.ac_wire_quantity = _quantity_from_post(request, "ac_wire_quantity", quotation.ac_wire_quantity)

        # ---- earth rods: always 3 nos (set by calculate_quotation), nothing to read here ----

        # ---- structure kW: empty = the panels' total watts; a number (8) = that many kW (8,000 W) for the structure ----
        if _model_has_field(Quotation, "structure_kw_manual"):
            structure_kw, problem = parse_structure_kw(request.POST.get("structure_kw_manual"))
            if problem:
                return HttpResponseBadRequest(problem)
            quotation.structure_kw_manual = structure_kw

        # ---- structure height ----
        structure_height = clean_text(request.POST.get("structure_height"))
        custom_height = clean_text(request.POST.get("custom_height"))

        if structure_kind(quotation.structure_type) == "roof":
            quotation.structure_feet = Decimal("2")
        elif structure_height == "other":
            quotation.structure_feet = decimal_or_zero(custom_height) if custom_height else Decimal("0")
        elif structure_height:
            quotation.structure_feet = decimal_or_zero(structure_height)

        # ---- additional charges ----
        # (these boxes are on the page only in the admin view: when they are missing, the saved amounts are kept)
        for field in ("electrical_work", "transportation_travel", "kseb_fee", "loading_charge", "documentation"):
            if field in request.POST:
                setattr(quotation, field, decimal_or_zero(request.POST.get(field)))

        # ---- structure wage and final price ----
        # They are handed on exactly as submitted.  calculations.py decides whether they were typed by
        # hand (kept) or are just the previously displayed automatic values (recalculated).
        # A blank box means "automatic".
        if "structure_wage" in request.POST:
            quotation.structure_work = decimal_or_zero(request.POST.get("structure_wage"))
        quotation.final_quotation_price = decimal_or_zero(request.POST.get("final_quotation_price"))

        # ---- customer details (editable on the detail page too) ----
        for field in ("customer_name", "phone", "email", "address"):
            if field in request.POST:
                setattr(quotation, field, clean_text(request.POST.get(field)))

        quotation.save()

        # ---- package option rules (BOS dropdowns) ----
        for rule in option_rules:
            selected_option = clean_text(request.POST.get(f"option_{rule.excel_cell}"))
            if not selected_option:
                continue
            item = find_item_for_rule(quotation, rule)
            if item:
                apply_product_to_item(item, selected_option)

        # ---- ONE calculation ----
        calculate_quotation(quotation)

        return redirect("quotation_detail", quotation_id=quotation.id)

    # =====================================================
    # GET: always show the current calculation
    # =====================================================
    calculate_quotation(quotation)
    summary = quotation.cost_breakdown

    is_other_inverter = clean_text(quotation.inverter_type).lower() == "other"

    return render(
        request,
        "quotations/quotation_detail.html",
        {
            "quotation": quotation,
            "panel_options": panel_options,
            "summary": summary,
            "structure_kind": structure_kind(quotation.structure_type),
            "inverter_products": Product.objects.filter(category="inverter", is_active=True, rate__gt=0).order_by("name"),
            "dc_cable_products": Product.objects.filter(category="dc_cable", is_active=True, rate__gt=0).order_by("name"),
            "ac_wire_products": Product.objects.filter(category="ac_wire", is_active=True, rate__gt=0).order_by("name"),
            "other_inverter_name": quotation.inverter_make if is_other_inverter else "",
            "other_inverter_rate": plain_number(quotation.inverter_rate) if is_other_inverter else "",
            "panel_shortfall_percent": PANEL_SHORTFALL_ALLOWED_PERCENT,          # the page's live panel count uses the same rule
            "can_edit_panels": _model_has_field(Quotation, "panel_quantity_manual"),
            "can_edit_structure_kw": _model_has_field(Quotation, "structure_kw_manual"),
            "show_rates": rates_unlocked(request),
            "unlock_error": "Wrong passkey." if request.GET.get("passkey") == "wrong" else "",
            "pdf_name": pdf_filename(quotation),
            "people_names": _people_names(),
        },
    )


# =========================================================
# QUOTATION PDF
# =========================================================

def quotation_pdf(request, quotation_id, filename=None):
    """The PDF only PRINTS the saved calculation; recalculating first makes sure it is the current one.
    `filename` is only the last part of the address (/pdf/12/HUDA_3kW.pdf): phones name a saved PDF after the address, not after the header."""
    quotation = get_object_or_404(
        Quotation.objects.select_related("panel_option", "solar_package").prefetch_related("items__product"),
        id=quotation_id,
    )

    calculate_quotation(quotation)

    pdf_buffer = build_quotation_pdf(request, quotation)

    response = FileResponse(
        pdf_buffer,
        as_attachment=False,
        filename=pdf_filename(quotation),                       # HUDA_3kW.pdf
        content_type="application/pdf",
    )
    # never reuse an earlier copy: the PDF must always show the current saved quotation
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


# =========================================================
# DASHBOARD
# =========================================================

def _person_url():
    """The address of the person page ('' if its line has not been added to urls.py yet: the dashboard then still works)."""
    try:
        return reverse("person_dashboard")
    except NoReverseMatch:
        return ""


def dashboard(request):
    """All quotations, the totals of everybody, and one line per person (click a name for his own totals)."""
    quotations = list(Quotation.objects.order_by("-created_at"))
    rows = stats.rows_of(quotations)
    return render(request, "quotations/dashboard.html", {
        "quotations": quotations,
        "totals": stats.format_summary(stats.summarize_clients(rows)),
        "people": stats.people(rows),
        "person_url": _person_url(),
        "show_rates": rates_unlocked(request),
        "unlock_error": "Wrong passkey." if request.GET.get("passkey") == "wrong" else "",
    })


def person_dashboard(request):
    """One person's total quotations, kW, value and profit, with his quotations.   /person/?name=Imran"""
    link_name = request.GET.get("name", "")
    key = stats.key_from_link(link_name)
    quotations = [q for q in Quotation.objects.order_by("-created_at") if stats.name_key(q.customer_name) == key]
    if not quotations:
        raise Http404("There is no quotation for this name.")

    def make_item(q):
        line = stats.format_summary(stats.summarize(stats.rows_of([q])))
        return {"id": q.id, "offer_no": q.offer_no, "business_name": q.business_name, "location": q.location, "date": q.date,
                "pdf_name": pdf_filename(q), "is_customer": q.is_customer,
                "category": q.category, "kw_display": line["kw_display"], "value_display": line["value_display"],
                "profit_display": line["profit_display"], "profit_negative": line["profit_negative"],
                "search": stats.search_text(q) + " " + line["value_text"] + " " + line["kw_text"]}

    by_id = {q.id: q for q in quotations}
    items = []
    for group in stats.group_clients(stats.rows_of(quotations)):
        item = make_item(by_id[group["picked"]["id"]])
        item["others"] = [make_item(by_id[r["id"]]) for r in group["others"]]
        item["chosen"] = group["chosen"]
        confirmed = [x for x in [item] + item["others"] if x["is_customer"]]
        item["customer_id"] = confirmed[0]["id"] if confirmed else None
        item["customer_offer"] = confirmed[0]["offer_no"] if confirmed else ""
        item["preselect"] = item["customer_id"] or item["id"]
        item["search"] += " " + " ".join(o["search"] for o in item["others"])
        items.append(item)

    return render(request, "quotations/person.html", {
        "person_name": stats.most_common_name(q.customer_name for q in quotations) or stats.NO_NAME_TEXT,
        "totals": stats.format_summary(stats.summarize_clients(stats.rows_of(quotations))),
        "items": items,
        "show_rates": rates_unlocked(request),
    })


@login_not_required
def materials_api(request):
    """
    Read-only data for the separate materials website.  Needs the header  X-API-Key  equal to the environment variable
    MATERIALS_API_KEY (switched off when that is not set).      /api/materials/?q=huda       a search, newest first
                                                               /api/materials/?id=12        one quotation with its material list
    """
    expected = os.environ.get("MATERIALS_API_KEY", "")
    given = request.headers.get("X-API-Key", "")
    if not expected or not hmac.compare_digest(expected.encode(), given.encode()):
        raise Http404()

    def header(q):
        return {"id": q.id, "offer_no": q.offer_no, "business_name": q.business_name, "customer_name": q.customer_name,
                "phone": q.phone, "location": q.location, "system_size": str(q.system_size), "date": str(q.date)}

    if request.GET.get("id", "").isdigit():
        quotation = get_object_or_404(Quotation, id=int(request.GET["id"]), is_customer=True)
        try:
            data = header(quotation)
            data["items"] = material_list(quotation)
            data.update(labour_amounts(quotation))
        except Exception as problem:         # show the real reason to the materials website (this address needs the secret key anyway)
            return JsonResponse({"error": "%s: %s" % (type(problem).__name__, problem)}, status=500)
        return JsonResponse(data)

    query = request.GET.get("q", "").strip()
    found = [q for q in Quotation.objects.filter(is_customer=True).order_by("-created_at")[:500] if not query or stats.matches(stats.search_text(q), query)]
    return JsonResponse({"quotations": [header(q) for q in found[:30]]})


def confirm_customer(request, quotation_id=None):
    """
    POST: the client said yes - this quotation becomes a customer (and is the one that counts for the client).
    With the id in the address, pressing again undoes it.  Without it (the choice list on the person page) the chosen
    quotation_id is only ever CONFIRMED, never undone.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    choice = quotation_id is None
    if choice:
        raw = request.POST.get("quotation_id", "")
        if not raw.isdigit():
            return HttpResponseBadRequest("Choose a quotation.")
        quotation_id = int(raw)
    quotation = get_object_or_404(Quotation, id=quotation_id)
    if quotation.is_customer and choice:
        pass
    elif quotation.is_customer:
        Quotation.objects.filter(id=quotation.id).update(is_customer=False)
    else:
        key = stats.client_key(stats.rows_of([quotation])[0])
        same = [q.id for q in Quotation.objects.all() if stats.client_key(stats.rows_of([q])[0]) == key]
        Quotation.objects.filter(id__in=same).update(counted=False, is_customer=False)     # one confirmed quotation per client
        Quotation.objects.filter(id=quotation.id).update(counted=True, is_customer=True)
    return redirect(_safe_next(request, reverse("quotation_detail", args=[quotation.id])))


def set_counted(request, quotation_id):
    """POST: make this quotation the one that counts for its client (action=clear: back to the lowest price)."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    quotation = get_object_or_404(Quotation, id=quotation_id)
    key = stats.client_key(stats.rows_of([quotation])[0])
    same = [q.id for q in Quotation.objects.all() if stats.client_key(stats.rows_of([q])[0]) == key]
    Quotation.objects.filter(id__in=same).update(counted=False)
    if request.POST.get("action") != "clear":
        Quotation.objects.filter(id=quotation.id).update(counted=True)
    return redirect(_safe_next(request, reverse("quotation_dashboard")))


def search(request):
    """Looks through ALL quotations: offer number, business, person, place, phone ...   /search/?q=huda kozhikode"""
    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("quotation_dashboard")

    found = [q for q in Quotation.objects.order_by("-created_at") if stats.matches(stats.search_text(q), query)]
    items = []
    for q in found:
        line = stats.format_summary(stats.summarize(stats.rows_of([q])))
        items.append({"id": q.id, "offer_no": q.offer_no, "business_name": q.business_name, "location": q.location, "date": q.date,
                      "pdf_name": pdf_filename(q),
                      "category": q.category, "person_name": q.customer_name, "person_link": stats.link_key_for(q.customer_name),
                      "kw_display": line["kw_display"], "value_display": line["value_display"],
                      "profit_display": line["profit_display"], "profit_negative": line["profit_negative"]})

    return render(request, "quotations/search.html", {"query": query, "items": items, "person_url": _person_url(), "show_rates": rates_unlocked(request)})