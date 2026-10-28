import calendar
from datetime import date, datetime, timedelta

from .models import BillingCycle

# Average cycle length in days, used for recurrence detection and cost normalisation.
CYCLE_DAYS: dict[BillingCycle, float] = {
    BillingCycle.WEEKLY: 7.0,
    BillingCycle.MONTHLY: 30.44,
    BillingCycle.QUARTERLY: 91.31,
    BillingCycle.YEARLY: 365.25,
}

_CYCLE_MONTHS = {BillingCycle.MONTHLY: 1, BillingCycle.QUARTERLY: 3, BillingCycle.YEARLY: 12}

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d")


def add_months(d: date, months: int) -> date:
    """Calendar-aware month arithmetic; clamps to month end (Jan 31 + 1 month -> Feb 28/29)."""
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_cycle(anchor: date, cycle: BillingCycle, n: int = 1) -> date:
    """The n-th renewal after `anchor`. Always computed from the anchor, so month-end
    clamping never accumulates (Jan 31 -> Feb 28 -> Mar 31, not Mar 28)."""
    if cycle is BillingCycle.WEEKLY:
        return anchor + timedelta(weeks=n)
    return add_months(anchor, _CYCLE_MONTHS[cycle] * n)


def roll_forward(anchor: date, cycle: BillingCycle, on_or_after: date) -> date:
    """First renewal date on or after `on_or_after` in the series starting at `anchor`."""
    n = 0
    while (candidate := add_cycle(anchor, cycle, n)) < on_or_after:
        n += 1
    return candidate


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def parse_date(raw: str) -> date:
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date '{raw}' (use YYYY-MM-DD or MM/DD/YYYY)")
