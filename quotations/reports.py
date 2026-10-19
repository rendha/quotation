"""Daily report: how many quotations were made on a day, and for which person.   /report/   /report/?date=2026-10-19   /report/?from=...&to=..."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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
