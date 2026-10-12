"""
The date and period helpers, tested directly.

These four functions take values in and give values back without touching
Supabase, so they need no stubbing at all. They are also where the
arithmetic is easiest to get subtly wrong — month ends, leap years and week
boundaries — and every module above them inherits whatever they decide.
"""
from datetime import date, timedelta

import pytest

from app.analytics.service import get_month_range, month_label
from app.budgets.service import get_period_date_range
from app.recurring.service import calculate_next_due_date


# ── calculate_next_due_date: monthly ──────────────────────────────────────

@pytest.mark.parametrize(
    "current,expected,note",
    [
        (date(2026, 1, 15), date(2026, 2, 15), "ordinary month step"),
        (date(2026, 12, 15), date(2027, 1, 15), "rolls into the next year"),
        (date(2026, 1, 31), date(2026, 2, 28), "clamps to a short month"),
        (date(2024, 1, 31), date(2024, 2, 29), "clamps to a leap February"),
        (date(2026, 3, 31), date(2026, 4, 30), "clamps 31 to a 30 day month"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_monthly_advance(current, expected, note):
    assert calculate_next_due_date(current, "monthly") == expected, note


def test_monthly_respects_day_of_month():
    assert calculate_next_due_date(
        date(2026, 1, 20), "monthly", day_of_month=5
    ) == date(2026, 2, 5)


def test_monthly_day_of_month_clamps_to_short_month():
    """A rule set to the 31st still fires in February, on the 28th."""
    assert calculate_next_due_date(
        date(2026, 1, 31), "monthly", day_of_month=31
    ) == date(2026, 2, 28)


def test_clamping_does_not_stick():
    """
    A 31st rule clamped to the 28th in February must return to the 31st in
    March, not stay on the 28th. It does, because day_of_month is read from
    the rule each time rather than from the clamped date — but only when
    day_of_month is actually set.
    """
    february = calculate_next_due_date(date(2026, 1, 31), "monthly", day_of_month=31)
    march = calculate_next_due_date(february, "monthly", day_of_month=31)
    assert february == date(2026, 2, 28)
    assert march == date(2026, 3, 31)


def test_clamping_is_permanent_without_day_of_month():
    """
    The same rule without day_of_month set drifts: once clamped to the 28th
    it keeps the 28th forever, because the target day is taken from the last
    due date. Recorded deliberately — this is why day_of_month exists.
    """
    february = calculate_next_due_date(date(2026, 1, 31), "monthly")
    march = calculate_next_due_date(february, "monthly")
    assert february == date(2026, 2, 28)
    assert march == date(2026, 3, 28)


# ── calculate_next_due_date: weekly ───────────────────────────────────────

def test_weekly_advance_is_seven_days():
    assert calculate_next_due_date(date(2026, 10, 5), "weekly") == date(2026, 10, 12)


def test_weekly_lands_on_the_target_weekday():
    #                Mon 5 Oct 2026 -> +7 = Mon 12 -> Friday of that week
    assert calculate_next_due_date(
        date(2026, 10, 5), "weekly", day_of_week=4
    ) == date(2026, 10, 16)


@pytest.mark.parametrize("start_offset", range(7))
@pytest.mark.parametrize("target", range(7))
def test_weekly_always_moves_forward(start_offset, target):
    """
    The weekday correction can subtract up to six days from the +7 step, so
    check every combination still lands strictly after the current date and
    on the requested weekday.
    """
    current = date(2026, 10, 5) + timedelta(days=start_offset)
    result = calculate_next_due_date(current, "weekly", day_of_week=target)
    assert result > current
    assert result.weekday() == target


# ── month_label ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "year,month,expected",
    [(2026, 1, "Jan 2026"), (2026, 10, "Oct 2026"), (2025, 12, "Dec 2025")],
)
def test_month_label(year, month, expected):
    assert month_label(year, month) == expected


# ── get_month_range ───────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [1, 3, 6, 12, 24])
def test_month_range_length_and_order(n):
    months = get_month_range(n)

    assert len(months) == n
    assert months == sorted(months), "must be oldest first"
    assert months[-1] == (date.today().year, date.today().month), "ends on today"
    assert len(set(months)) == n, "no repeats across a year boundary"


def test_month_range_steps_by_exactly_one_month():
    months = get_month_range(18)
    for (y1, m1), (y2, m2) in zip(months, months[1:]):
        assert (y2 - y1) * 12 + (m2 - m1) == 1


def test_month_range_docstring_example_is_wrong():
    """
    The docstring says months_back=3 returns four tuples and shows four.
    The loop runs exactly months_back times, so it returns three. The code
    is the sensible reading; the comment is the thing that is wrong.
    """
    assert len(get_month_range(3)) == 3


# ── get_period_date_range ─────────────────────────────────────────────────
# Both branches read date.today(), so these assert invariants rather than
# fixed dates — a test that hardcodes today's month stops working tomorrow.

def test_monthly_period_covers_the_whole_current_month():
    start, end = get_period_date_range("monthly")
    today = date.today()

    assert start.day == 1
    assert start.year == today.year and start.month == today.month
    assert end.month == today.month
    assert (end + timedelta(days=1)).month != end.month, "end is the last day"
    assert start <= today <= end


def test_weekly_period_is_monday_to_sunday_containing_today():
    start, end = get_period_date_range("weekly")
    today = date.today()

    assert start.weekday() == 0, "ISO week starts Monday"
    assert end.weekday() == 6
    assert (end - start).days == 6
    assert start <= today <= end


def test_unknown_period_falls_back_to_monthly():
    """Anything that is not 'weekly' takes the monthly branch."""
    assert get_period_date_range("fortnightly") == get_period_date_range("monthly")
