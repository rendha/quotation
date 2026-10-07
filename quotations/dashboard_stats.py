"""
quotations/dashboard_stats.py
=============================

The numbers on the dashboard.  Pure Python: it is given plain rows (dicts) and never touches the database, so it is easy to test.

A "person" is the name typed in the "Quotation For" box (stored in Quotation.customer_name).  Names are matched ignoring capital
letters and extra spaces, so "Imran", "imran " and "IMRAN" are ONE person.

For every person (and for everybody together):
    quotations .. how many
    kW .......... the sum of the system sizes
    value ....... the sum of the final quotation prices (GST included)
    profit ...... the sum of the MARGINS (Quotation.margin_amount: the margin each quotation was calculated with)
"""
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
NO_NAME_KEY = "__none__"          # what the link carries for quotations that have no name
NO_NAME_TEXT = "No name"


# ---------------------------------------------------------------------------------------------- names
def clean_name(value):
    """'  Imran   K ' -> 'Imran K'."""
    return " ".join(str(value or "").split())


def name_key(value):
    """The key that decides who is the same person: the cleaned name without capital letters ('' = no name)."""
    return clean_name(value).casefold()


def key_from_link(parameter):
    """The ?name=... of the person page -> the key above."""
    return "" if parameter == NO_NAME_KEY else name_key(parameter)


def most_common_name(names):
    """The spelling used most often ('' when there is none); a tie goes to the one used first."""
    cleaned = [clean_name(n) for n in names if clean_name(n)]
    return Counter(cleaned).most_common(1)[0][0] if cleaned else ""


def distinct_names(names):
    """Every person once, as the most common spelling, sorted - for the suggestions under the "Quotation For" box."""
    groups = {}
    for name in names:
        if name_key(name):
            groups.setdefault(name_key(name), []).append(name)
    return sorted((most_common_name(v) for v in groups.values()), key=str.casefold)


# ---------------------------------------------------------------------------------------------- numbers
def _decimal(value):
    if value is None or str(value).strip() == "":
        return ZERO
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def indian(amount, decimals=0):
    """Indian digit grouping:  240000 -> '2,40,000',  -1234567.5 -> '-12,34,568'."""
    value = _decimal(amount).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    sign = "-" if value < 0 else ""
    whole, _, fraction = "{:f}".format(abs(value)).partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join(groups + [tail]) if groups else tail
    return sign + text + ("." + fraction if decimals else "")


def number_text(value):
    """3.00 -> '3',  12.50 -> '12.5'."""
    return "{:f}".format(_decimal(value).normalize())


# ---------------------------------------------------------------------------------------------- totals
ROW_FIELDS = ("customer_name", "system_size", "final_quotation_price", "margin_amount")


def rows_of(quotations):
    """Quotation objects -> plain dicts holding only the fields the dashboard adds up (so this module never touches the database)."""
    return [{name: getattr(q, name, None) for name in ROW_FIELDS} for q in quotations]


def row_value(row):
    return _decimal(row.get("final_quotation_price"))


def row_profit(row):
    """The profit of a quotation is its margin: the amount the calculation added on top of the cost."""
    return _decimal(row.get("margin_amount"))


def summarize(rows):
    """-> {count, kw, value, profit} for these rows."""
    rows = list(rows)
    return {
        "count": len(rows),
        "kw": sum((_decimal(r.get("system_size")) for r in rows), ZERO),
        "value": sum((row_value(r) for r in rows), ZERO),
        "profit": sum((row_profit(r) for r in rows), ZERO),
    }


def format_summary(summary):
    """The same numbers with the text the page prints: Indian grouping, no decimals, and a loss as '-' before the rupee sign."""
    out = dict(summary)
    profit = indian(summary["profit"])
    out["kw_text"] = number_text(summary["kw"])
    out["value_text"] = indian(summary["value"])
    out["profit_text"] = profit
    out["profit_negative"] = profit.startswith("-")
    out["kw_display"] = out["kw_text"] + " kW"
    out["value_display"] = "\u20b9" + out["value_text"]
    out["profit_display"] = ("-\u20b9" + profit[1:]) if out["profit_negative"] else "\u20b9" + profit
    return out


def people(rows):
    """
    One entry per person, biggest value first, the quotations without a name last:
    {name, key, link_key, count, kw, value, profit, kw_text, value_text, profit_text, profit_negative}
    """
    groups = {}
    for row in rows:
        groups.setdefault(name_key(row.get("customer_name")), []).append(row)

    result = []
    for key, items in groups.items():
        entry = format_summary(summarize(items))
        entry.update(key=key, link_key=NO_NAME_KEY if key == "" else key,
                     name=most_common_name(r.get("customer_name") for r in items) or NO_NAME_TEXT)
        result.append(entry)
    result.sort(key=lambda e: (e["key"] == "", -e["value"], e["name"].casefold()))
    return result
