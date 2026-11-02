"""
How much of a projected cost falls in a span of days. The one rule every
projection uses: the dashboard card, the monthly chart, projected vs real,
the weekly view and /projected/monthly.

Option A of the signed analytics acta (docs/decisiones/acta-analitica.pdf,
defect 10): a cost is spread over the calendar, day by day.

  weekly, no day_of_week     amount / 7 for every day in the span
  weekly, day_of_week        amount on every such weekday in the span
                             (0 = Monday ... 6 = Sunday, as Python's weekday())
  monthly, day_of_month      amount on that day; a day the month does not
                             have (31 in a 30-day month) falls on its last day
  monthly, no day_of_month   amount / days in that month, for every day
  one_time                   as monthly, but only in its own month and year

Before this, a weekly cost was amount x 4.333 a month but its full amount in
every week of the weekly view, so the same response gave two figures for
one cost. $500 a week is now $2,214.29 in a 31-day month in every view.

Every rule is additive: splitting a span into parts and adding the parts
gives the whole. That is what makes the weeks of a month add up to it.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal


def _days(start: date, end: date) -> int:
    return (end - start).days + 1 if end >= start else 0


def _weekday_count(start: date, end: date, weekday: int) -> int:
    first = start + timedelta(days=(weekday - start.weekday()) % 7)
    return (end - first).days // 7 + 1 if first <= end else 0


def _month_spans(start: date, end: date):
    """(year, month, first, last) for each month the span touches, clipped to it."""
    current = date(start.year, start.month, 1)
    while current <= end:
        days = calendar.monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, days)
        yield current.year, current.month, max(start, current), min(end, month_end)
        current = month_end + timedelta(days=1)


def amount_in_range(cost: dict, start: date, end: date, rate: Decimal = Decimal("1")) -> Decimal:
    """The part of the cost that falls between start and end, both included, in MXN."""
    if end < start:
        return Decimal("0")

    amount = Decimal(str(cost["amount"])) * rate
    frequency = cost["frequency"]

    if frequency == "weekly":
        weekday = cost.get("day_of_week")
        if weekday is None:
            return amount * _days(start, end) / 7
        return amount * _weekday_count(start, end, weekday)

    if frequency not in ("monthly", "one_time"):
        return Decimal("0")

    total = Decimal("0")
    for year, month, first, last in _month_spans(start, end):
        if frequency == "one_time" and (cost.get("year"), cost.get("month")) != (year, month):
            continue
        days_in_month = calendar.monthrange(year, month)[1]
        day = cost.get("day_of_month")
        if day is None:
            total += amount * _days(first, last) / days_in_month
        elif first <= date(year, month, min(day, days_in_month)) <= last:
            total += amount
    return total


def monthly_amount(cost: dict, year: int, month: int, rate: Decimal = Decimal("1")) -> Decimal:
    """The cost's projection for one calendar month."""
    last = calendar.monthrange(year, month)[1]
    return amount_in_range(cost, date(year, month, 1), date(year, month, last), rate)


def split_rounded(parts: list[Decimal]) -> list[Decimal]:
    """
    Rounds each part to cents so that the rounded parts add up to the
    rounded whole. Each part is the difference between consecutive rounded
    running totals; rounding each part on its own could leave the weeks a
    cent or two away from their month.
    """
    rounded, running, previous = [], Decimal("0"), Decimal("0")
    for part in parts:
        running += part
        # round(), like every other figure in the analytics, so the last
        # running total is exactly the month as the API reports it.
        current = round(running, 2)
        rounded.append(current - previous)
        previous = current
    return rounded
