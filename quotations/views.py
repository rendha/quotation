"""
quotations/views.py

HTTP only:  read the form  ->  save selections / quantities  ->  calculate_quotation(quotation)
            ->  render / redirect / PDF.

No money is calculated here.  Every amount comes from quotations/calculations.py.
"""
from decimal import Decimal

from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .calculations import (
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
        return render(request, "quotations/create_quotation.html", {"posted": {}, "people_names": _people_names()})

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
        quotation.electrical_work = decimal_or_zero(request.POST.get("electrical_work"))
        quotation.transportation_travel = decimal_or_zero(request.POST.get("transportation_travel"))
        quotation.kseb_fee = decimal_or_zero(request.POST.get("kseb_fee"))
        quotation.loading_charge = decimal_or_zero(request.POST.get("loading_charge"))
        quotation.documentation = decimal_or_zero(request.POST.get("documentation"))

        # ---- structure wage and final price ----
        # They are handed on exactly as submitted.  calculations.py decides whether they were typed by
        # hand (kept) or are just the previously displayed automatic values (recalculated).
        # A blank box means "automatic".
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
            "people_names": _people_names(),
        },
    )


# =========================================================
# QUOTATION PDF
# =========================================================

def quotation_pdf(request, quotation_id):
    """The PDF only PRINTS the saved calculation; recalculating first makes sure it is the current one."""
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
        "totals": stats.format_summary(stats.summarize(rows)),
        "people": stats.people(rows),
        "person_url": _person_url(),
    })


def person_dashboard(request):
    """One person's total quotations, kW, value and profit, with his quotations.   /person/?name=Imran"""
    link_name = request.GET.get("name", "")
    key = stats.key_from_link(link_name)
    quotations = [q for q in Quotation.objects.order_by("-created_at") if stats.name_key(q.customer_name) == key]
    if not quotations:
        raise Http404("There is no quotation for this name.")

    items = []
    for q in quotations:
        line = stats.format_summary(stats.summarize(stats.rows_of([q])))
        items.append({"id": q.id, "offer_no": q.offer_no, "business_name": q.business_name, "location": q.location, "date": q.date,
                      "category": q.category, "kw_display": line["kw_display"], "value_display": line["value_display"],
                      "profit_display": line["profit_display"], "profit_negative": line["profit_negative"],
                      "search": stats.search_text(q) + " " + line["value_text"] + " " + line["kw_text"]})

    return render(request, "quotations/person.html", {
        "person_name": stats.most_common_name(q.customer_name for q in quotations) or stats.NO_NAME_TEXT,
        "totals": stats.format_summary(stats.summarize(stats.rows_of(quotations))),
        "items": items,
    })


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
                      "category": q.category, "person_name": q.customer_name, "person_link": stats.link_key_for(q.customer_name),
                      "kw_display": line["kw_display"], "value_display": line["value_display"],
                      "profit_display": line["profit_display"], "profit_negative": line["profit_negative"]})

    return render(request, "quotations/search.html", {"query": query, "items": items, "person_url": _person_url()})