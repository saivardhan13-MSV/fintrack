from datetime import date, timedelta

from fintrack.dates import add_months
from fintrack.models import BillingCycle
from fintrack.services.recurrence import Charge, classify_interval, detect_recurring

TODAY = date(2026, 10, 15)


def monthly(merchant: str, first: date, count: int, cents: int) -> list[Charge]:
    return [Charge(merchant, add_months(first, i), cents) for i in range(count)]


def test_classify_interval() -> None:
    assert classify_interval(7) is BillingCycle.WEEKLY
    assert classify_interval(28) is BillingCycle.MONTHLY
    assert classify_interval(31) is BillingCycle.MONTHLY
    assert classify_interval(92) is BillingCycle.QUARTERLY
    assert classify_interval(365) is BillingCycle.YEARLY
    assert classify_interval(14) is None
    assert classify_interval(50) is None


def test_detects_monthly_subscription_and_predicts_next_renewal() -> None:
    charges = monthly("NETFLIX.COM", date(2026, 4, 3), 7, 1549)
    [found] = detect_recurring(charges, TODAY)
    assert found.merchant == "NETFLIX.COM"
    assert found.billing_cycle is BillingCycle.MONTHLY
    assert found.occurrences == 7
    assert found.last_charged_on == date(2026, 10, 3)
    assert found.next_renewal == date(2026, 11, 3)
    assert found.confidence == 1.0
    assert found.price_change_cents == 0


def test_detects_weekly_subscription() -> None:
    charges = [Charge("GYM", TODAY - timedelta(weeks=w), 1200) for w in range(6)]
    [found] = detect_recurring(charges, TODAY)
    assert found.billing_cycle is BillingCycle.WEEKLY
    assert found.next_renewal == TODAY


def test_reports_price_increase() -> None:
    charges = monthly("SPOTIFY USA", date(2026, 5, 20), 4, 1099)
    charges += [Charge("SPOTIFY USA", date(2026, 9, 20), 1199)]
    [found] = detect_recurring(charges, TODAY)
    assert found.amount_cents == 1199
    assert found.price_change_cents == 100


def test_tolerates_one_late_payment() -> None:
    dates = [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 9), date(2026, 8, 1),
             date(2026, 9, 1), date(2026, 10, 1)]
    [found] = detect_recurring([Charge("ICLOUD", d, 299) for d in dates], TODAY)
    assert found.billing_cycle is BillingCycle.MONTHLY
    assert 0.7 <= found.confidence < 1.0


def test_ignores_irregular_spending() -> None:
    dates = [date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 20), date(2026, 10, 2),
             date(2026, 10, 4)]
    assert detect_recurring([Charge("WHOLE FOODS", d, 8000) for d in dates], TODAY) == []


def test_ignores_wildly_varying_amounts() -> None:
    amounts = [500, 9000, 1500, 30000, 200]
    charges = [Charge("UTILITY", add_months(date(2026, 5, 10), i), a)
               for i, a in enumerate(amounts)]
    assert detect_recurring(charges, TODAY) == []


def test_ignores_cancelled_series() -> None:
    charges = monthly("HULU", date(2025, 11, 5), 5, 799)  # last charge March 2026
    assert detect_recurring(charges, TODAY) == []


def test_requires_minimum_occurrences() -> None:
    assert detect_recurring(monthly("NEW APP", date(2026, 9, 1), 2, 499), TODAY) == []


def test_groups_by_merchant_and_sorts_by_confidence() -> None:
    charges = monthly("B SERVICE", date(2026, 5, 1), 6, 1000)
    charges += monthly("A SERVICE", date(2026, 5, 2), 6, 2000)
    found = detect_recurring(charges, TODAY)
    assert [f.merchant for f in found] == ["A SERVICE", "B SERVICE"]
