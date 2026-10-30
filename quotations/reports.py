"""Daily report: how many quotations were made on a day, and for which person.   /report/   /report/?date=2026-10-19   /report/?from=...&to=...
Monthly report (admin passkey): everything about one month.   /report/monthly/   /report/monthly/?month=2026-10   ...&format=csv"""
import csv
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.shortcuts import render

from . import dashboard_stats as stats
from .models import Quotation

INDIA = ZoneInfo("Asia/Kolkata")


def _day(text, fallback):
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return fallback


def daily_report(request):
    today = datetime.now(INDIA).date()
    first = _day(request.GET.get("from") or request.GET.get("date"), today)
    last = _day(request.GET.get("to") or request.GET.get("date"), first)
    if last < first:
        first, last = last, first

    start = datetime.combine(first, time.min, tzinfo=INDIA)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=INDIA)
    quotations = list(Quotation.objects.filter(created_at__gte=start, created_at__lt=end).order_by("-created_at"))

    rows = stats.rows_of(quotations)
    by_person = []
    for entry in stats.people(rows):
        by_person.append(entry)
    for entry in by_person:
        entry["quotations"] = [q for q in quotations if stats.name_key(q.customer_name) == entry["key"]]

    single = first == last
    return render(request, "quotations/report.html", {
        "first": first, "last": last, "single": single, "is_today": single and first == today,
        "previous": first - timedelta(days=1), "next": (last + timedelta(days=1)) if last < today else None,
        "today": today, "yesterday": today - timedelta(days=1),
        "totals": stats.format_summary(stats.summarize_clients(rows)),
        "people": by_person,
        "quotations": [{"q": q, "time": q.created_at.astimezone(INDIA)} for q in quotations],
    })


# =====================================================================================================  MONTHLY REPORT
ZERO = Decimal("0")


def _month(text, fallback):
    """'2026-10' -> date(2026, 10, 1)."""
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m").date().replace(day=1)
    except ValueError:
        return fallback


def _add_months(first, months):
    index = first.year * 12 + first.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _system_label(q):
    text = (q.system_type or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    return {"ongrid": "On-Grid", "offgrid": "Off-Grid", "hybrid": "Hybrid"}.get(text, (q.system_type or "").strip() or "Not set")


def _panel_label(q):
    return {"dcr": "DCR", "non_dcr": "Non-DCR", "both": "DCR + Non-DCR"}.get((q.panel_dcr_status or "").strip().lower(), "Not set")


def _phase_label(q):
    return "Three phase" if "three" in (q.phase or "").lower() else "Single phase"


def _inverter_label(q):
    name = (q.inverter_type or "").upper()
    if "MICRO" in name:
        return "Enphase (microinverter)"
    make = (q.inverter_make or "").strip()
    if make:
        return make.title()
    return (q.inverter_type or "").split(" ")[0].title() or "Not set"


def _size_label(q):
    return stats.number_text(q.system_size) + " kW"


def _group(quotations, label, sort="value"):
    """quotations -> [{label, count, kw, value, profit ...}] with the same counting rules as the daily report; biggest value first."""
    groups = OrderedDict()
    for q in quotations:
        groups.setdefault(label(q), []).append(q)
    out = []
    for name, items in groups.items():
        entry = stats.format_summary(stats.summarize_clients(stats.rows_of(items)))
        entry["name"] = name
        out.append(entry)
    out.sort(key=lambda e: (-e["value"], e["name"]) if sort == "value" else e["name"])
    return out


def _price(q):
    return q.final_quotation_price or ZERO


def _card(q):
    """One quotation as the plain facts the page prints (None when there is none)."""
    if q is None:
        return None
    return {"id": q.id, "offer_no": q.offer_no, "person": (q.customer_name or "").strip() or stats.NO_NAME_TEXT, "business": q.business_name,
            "location": q.location, "kw": stats.number_text(q.system_size), "price": stats.indian(_price(q)), "profit": stats.indian(q.margin_amount),
            "day": q.created_at.astimezone(INDIA).date(), "system": _system_label(q), "customer": bool(q.is_customer)}


def build_month(quotations, first, today, last=None):
    """
    Everything the monthly (and weekly) page prints, from the period's quotations (a list of Quotation objects, newest first).
    last = the period's last day (default: the end of the month `first` is in).
    No database access, so it is easy to test.
    """
    rows = stats.rows_of(quotations)
    totals = stats.format_summary(stats.summarize_clients(rows))
    customers = [q for q in quotations if q.is_customer]
    confirmed = stats.format_summary(stats.summarize_clients(stats.rows_of(customers)))

    priced = [q for q in quotations if _price(q) > 0]
    highest = max(priced, key=_price) if priced else None
    lowest = min(priced, key=_price) if priced else None
    biggest_kw = max(quotations, key=lambda q: q.system_size or ZERO) if quotations else None
    average_value = (totals["value"] / totals["clients"]) if totals["clients"] else ZERO
    average_kw = (totals["kw"] / totals["clients"]) if totals["clients"] else ZERO

    people = []
    for entry in stats.people(rows):
        mine = [q for q in quotations if stats.name_key(q.customer_name) == entry["key"]]
        entry["quotations"] = mine
        entry["highest"] = _card(max(mine, key=_price)) if mine else None
        entry["confirmed"] = sum(1 for q in mine if q.is_customer)
        people.append(entry)
    for position, entry in enumerate(people, 1):
        entry["rank"] = position
    most_quotations = max(people, key=lambda e: (e["count"], e["value"]), default=None)
    most_value = people[0] if people and people[0]["value"] > 0 else None
    most_kw = max(people, key=lambda e: e["kw"], default=None)

    days = OrderedDict()
    for q in sorted(quotations, key=lambda q: q.created_at):
        days.setdefault(q.created_at.astimezone(INDIA).date(), []).append(q)
    daily = []
    best_day = None
    for day, items in days.items():
        entry = stats.format_summary(stats.summarize_clients(stats.rows_of(items)))
        entry["day"] = day
        daily.append(entry)
        if best_day is None or entry["count"] > best_day["count"]:
            best_day = entry
    top_count = max((d["count"] for d in daily), default=0)
    for entry in daily:
        entry["bar"] = int(entry["count"] * 100 / top_count) if top_count else 0
    top_value = max((p["value"] for p in people), default=0)
    for entry in people:
        entry["bar"] = int(entry["value"] * 100 / top_value) if top_value else 0
    last_day = last or (_add_months(first, 1) - timedelta(days=1))
    by_day = {d["day"]: d for d in daily}
    shown_to = min(today, last_day) if today >= first else first
    chart = []
    for offset in range((shown_to - first).days + 1):
        day = first + timedelta(days=offset)
        count = by_day[day]["count"] if day in by_day else 0
        chart.append({"n": day.day, "name": day.strftime("%a"), "count": count, "weekend": day.weekday() == 6, "title": "%s: %d quotation%s" % (day.strftime("%d %b"), count, "" if count == 1 else "s"),
                      "h": max(int(count * 100 / top_count), 4) if count and top_count else 0})
    days_passed = ((min(today, last_day) - first).days + 1) if today >= first else 0

    return {
        "totals": totals, "confirmed": confirmed, "conversion": (round(confirmed["clients"] * 100 / totals["clients"]) if totals["clients"] else 0),
        "highest": _card(highest), "lowest": _card(lowest), "biggest_kw": _card(biggest_kw),
        "average_value": stats.indian(average_value), "average_kw": stats.number_text(average_kw.quantize(Decimal("0.1"))),
        "people": people, "most_quotations": most_quotations, "most_value": most_value, "most_kw": most_kw,
        "daily": daily, "chart": chart, "chart_max": top_count, "best_day": best_day, "active_days": len(daily), "days_passed": days_passed,
        "per_day": round(len(quotations) / days_passed, 1) if days_passed else 0,
        "by_system": _group(quotations, _system_label), "by_panel": _group(quotations, _panel_label), "by_phase": _group(quotations, _phase_label),
        "by_inverter": _group(quotations, _inverter_label), "by_size": _group(quotations, _size_label),
        "by_structure": _group(quotations, lambda q: (q.structure_type or "").strip() or "Not set"),
        "batteries": sum(int(q.battery_quantity or 0) for q in quotations if "hybrid" in (q.system_type or "").lower()),
        "no_name": sum(1 for q in quotations if not stats.name_key(q.customer_name)),
    }


def _changes(now, before):
    """This month against the last one: [{label, now, before, change}] (change is text, '' when there was nothing before)."""
    out = []
    for label, key, text in (("Quotations", "count", str), ("Clients", "clients", str), ("Total kW", "kw", stats.number_text),
                             ("Value", "value", stats.indian), ("Profit", "profit", stats.indian)):
        a, b = now[key], before[key]
        change = ""
        if b:
            percent = (Decimal(a) - Decimal(b)) * 100 / Decimal(b)
            change = "%s%s%%" % ("+" if percent >= 0 else "-", abs(int(percent.quantize(Decimal("1")))))
        out.append({"label": label, "now": text(a), "before": text(b), "change": change, "down": change.startswith("-")})
    return out


def month_context(quotations, earlier, first, today):
    """The whole context of the monthly page: this month's numbers, the comparison with the month before (`earlier`) and the navigation."""
    report = build_month(quotations, first, today)
    following = _add_months(first, 1)
    before = stats.summarize_clients(stats.rows_of(earlier))
    report.update({
        "first": first, "previous": _add_months(first, -1), "next": following if following <= today else None,
        "is_this_month": first == today.replace(day=1), "this_month": today.replace(day=1), "last_month": _add_months(today.replace(day=1), -1),
        "changes": _changes(report["totals"], before), "previous_name": _add_months(first, -1),
        "printed": datetime.now(INDIA),
        "quotations": [dict(_card(q), time=q.created_at.astimezone(INDIA)) for q in quotations],
    })
    return report


def monthly_report(request):
    from .views import rates_unlocked                      # the same admin passkey as the rates
    if not rates_unlocked(request):
        return render(request, "quotations/report_locked.html", {
            "next": request.get_full_path(), "error": "Wrong passkey." if request.GET.get("passkey") == "wrong" else "",
            "title": "Monthly report", "title_lower": "monthly report"})

    today = datetime.now(INDIA).date()
    first = min(_month(request.GET.get("month"), today.replace(day=1)), today.replace(day=1))
    following = _add_months(first, 1)
    start = datetime.combine(first, time.min, tzinfo=INDIA)
    end = datetime.combine(following, time.min, tzinfo=INDIA)
    quotations = list(Quotation.objects.filter(created_at__gte=start, created_at__lt=end).order_by("-created_at"))

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="quotations-%s.csv"' % first.strftime("%Y-%m")
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Date", "Offer no", "Quotation for", "Customer / business", "Phone", "Location", "System type", "Panel type", "Phase",
                         "kW", "Inverter", "Price (incl. GST)", "Profit", "Confirmed customer"])
        for q in reversed(quotations):
            writer.writerow([q.created_at.astimezone(INDIA).strftime("%d-%m-%Y %H:%M"), q.offer_no, q.customer_name, q.business_name, q.phone, q.location,
                             _system_label(q), _panel_label(q), _phase_label(q), q.system_size, q.inverter_type, q.final_quotation_price,
                             q.margin_amount, "Yes" if q.is_customer else ""])
        return response

    earlier = list(Quotation.objects.filter(created_at__gte=datetime.combine(_add_months(first, -1), time.min, tzinfo=INDIA), created_at__lt=start))
    report = month_context(quotations, earlier, first, today)
    return render(request, "quotations/monthly_report.html", report)


# =====================================================================================================  WEEKLY REPORT
def _monday(day):
    return day - timedelta(days=day.weekday())


def weekly_report(request):
    from .views import rates_unlocked                      # the same admin passkey as the rates
    if not rates_unlocked(request):
        return render(request, "quotations/report_locked.html", {
            "next": request.get_full_path(), "error": "Wrong passkey." if request.GET.get("passkey") == "wrong" else "",
            "title": "Weekly report", "title_lower": "weekly report"})

    today = datetime.now(INDIA).date()
    first = min(_monday(_day(request.GET.get("week"), today)), _monday(today))           # any date in the week opens that week (Monday to Sunday)
    last = first + timedelta(days=6)
    start = datetime.combine(first, time.min, tzinfo=INDIA)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=INDIA)
    quotations = list(Quotation.objects.filter(created_at__gte=start, created_at__lt=end).order_by("-created_at"))
    before = list(Quotation.objects.filter(created_at__gte=start - timedelta(days=7), created_at__lt=start))
    report = week_context(quotations, before, first, today)
    return render(request, "quotations/weekly_report.html", report)


def week_context(quotations, before, first, today):
    """The context of the weekly page: the week's numbers, the week before for comparison, and the navigation."""
    last = first + timedelta(days=6)
    report = build_month(quotations, first, today, last=last)
    report.update({
        "first": first, "last": last, "previous": first - timedelta(days=7), "next": (first + timedelta(days=7)) if first + timedelta(days=7) <= today else None,
        "previous_last": first - timedelta(days=1), "is_this_week": first == _monday(today), "this_week": _monday(today), "last_week": _monday(today) - timedelta(days=7),
        "changes": _changes(report["totals"], stats.summarize_clients(stats.rows_of(before))), "printed": datetime.now(INDIA),
        "quotations": [dict(_card(q), time=q.created_at.astimezone(INDIA)) for q in quotations],
    })
    return report
