"""Quotations sold BELOW their calculated price: who quoted, the calculated value, the value they quoted, the margin lost and the margin now."""
from decimal import Decimal

from .calculations import GST_RATE, money
from .models import Quotation

TOLERANCE = Decimal("50")        # the automatic price is rounded to the nearest Rs 100: a smaller gap is only that rounding


def row_of(q):
    """-> dict for one quotation, or None when its price is not below the calculated price."""
    suggested, final, cost = Decimal(q.suggested_quotation_price or 0), Decimal(q.final_quotation_price or 0), Decimal(q.calculated_cost or 0)
    if suggested <= 0 or final <= 0 or suggested - final <= TOLERANCE:
        return None
    selling = money(final * 100 / (100 + GST_RATE))
    now_amount = money(selling - cost)
    return {
        "id": q.id, "offer_no": q.offer_no, "date": q.date, "person": q.customer_name or "-", "client": q.business_name or "-",
        "is_customer": q.is_customer,
        "calculated_value": suggested, "their_value": final, "below": money(suggested - final),
        "was_amount": Decimal(q.margin_amount or 0), "was_percent": money(Decimal(q.margin_percent or 0)),
        "now_amount": now_amount, "now_percent": money(now_amount * 100 / selling) if selling > 0 else Decimal(0),
        "lost": money(Decimal(q.margin_amount or 0) - now_amount), "loss": now_amount < 0,
    }


def rows(limit=300):
    found = []
    for q in Quotation.objects.order_by("-created_at")[:2000]:
        r = row_of(q)
        if r:
            found.append(r)
        if len(found) >= limit:
            break
    return found
