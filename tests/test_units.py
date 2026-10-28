from datetime import date
from decimal import Decimal

import pytest

from fintrack.dates import add_cycle, add_months, parse_date, roll_forward
from fintrack.merchants import normalize_merchant
from fintrack.models import BillingCycle, monthly_cost_cents
from fintrack.money import from_cents, parse_amount, to_cents
from fintrack.security import hash_password, verify_password


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("-12.50", "-12.50"), ("$1,204.00", "1204.00"), ("(45.10)", "-45.10"), (" 7 ", "7")],
)
def test_parse_amount(raw: str, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "", "NaN", "1.2.3"])
def test_parse_amount_rejects_garbage(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_cents_round_trip_and_half_up_rounding() -> None:
    assert to_cents(Decimal("15.49")) == 1549
    assert to_cents("0.005") == 1
    assert from_cents(1549) == Decimal("15.49")


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap year
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)


def test_add_cycle_does_not_drift_after_short_month() -> None:
    anchor = date(2026, 1, 31)
    assert add_cycle(anchor, BillingCycle.MONTHLY, 1) == date(2026, 2, 28)
    assert add_cycle(anchor, BillingCycle.MONTHLY, 2) == date(2026, 3, 31)


def test_roll_forward() -> None:
    assert roll_forward(date(2026, 1, 10), BillingCycle.MONTHLY, date(2026, 10, 15)) == date(
        2026, 11, 10
    )
    assert roll_forward(date(2026, 10, 15), BillingCycle.WEEKLY, date(2026, 10, 15)) == date(
        2026, 10, 15
    )
    assert roll_forward(date(2024, 2, 29), BillingCycle.YEARLY, date(2026, 1, 1)) == date(
        2026, 2, 28
    )


def test_parse_date_formats() -> None:
    assert parse_date("2026-10-01") == date(2026, 10, 1)
    assert parse_date("10/01/2026") == date(2026, 10, 1)
    with pytest.raises(ValueError):
        parse_date("01.10.2026")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("POS NETFLIX.COM 866-579-7172", "NETFLIX.COM"),
        ("SPOTIFY USA*P2A9F1", "SPOTIFY USA"),
        ("PAYPAL *HULU 402-935-7733", "HULU"),
        ("SQ *BLUE BOTTLE COFFEE #12", "BLUE BOTTLE COFFEE"),
        ("Whole Foods Market", "WHOLE FOODS MARKET"),
        ("12345", "12345"),
    ],
)
def test_normalize_merchant(raw: str, expected: str) -> None:
    assert normalize_merchant(raw) == expected


def test_monthly_cost_normalisation() -> None:
    assert monthly_cost_cents(1200, BillingCycle.YEARLY) == 100
    assert monthly_cost_cents(300, BillingCycle.QUARTERLY) == 100
    assert monthly_cost_cents(1000, BillingCycle.WEEKLY) == 4333
    assert monthly_cost_cents(999, BillingCycle.MONTHLY) == 999


def test_password_hashing() -> None:
    stored = hash_password("s3cret-pass", iterations=1_000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("s3cret-pass", stored)
    assert not verify_password("wrong-pass", stored)
    assert not verify_password("s3cret-pass", "garbage")
    assert hash_password("s3cret-pass", 1_000) != stored  # unique salt per hash
