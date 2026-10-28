"""Realistic demo data: a year of bank activity for a demo user.

Used by `python -m scripts.seed_demo` locally, and at startup on hosted demos
(FINTRACK_SEED_DEMO=true) where the database is recreated on every restart.
"""

import csv
import io
import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .dates import add_months
from .models import User
from .money import from_cents
from .schemas import BudgetUpsert, DetectionResponse, ImportResult, SubscriptionCreate
from .security import hash_password
from .services import budgets, subscriptions, transactions

DEMO_EMAIL = "demo@fintrack.dev"
DEMO_PASSWORD = "demo-password-123"

# (description, amount, category, day of month, first month index, (month index, new price))
SUBSCRIPTIONS = [
    ("NETFLIX.COM 866-579-7172", 15.49, "Streaming", 3, 0, (9, 17.99)),
    ("SPOTIFY USA*P2A9F1", 10.99, "Streaming", 12, 0, None),
    ("APPLE.COM/BILL ICLOUD 866-712", 2.99, "Cloud", 21, 2, None),
    ("PAYPAL *HULU 402-935-7733", 7.99, "Streaming", 8, 0, None),
    ("ADOBE *CREATIVE CLOUD", 22.99, "Software", 15, 4, None),
]
# Limits chosen so the demo shows a mix of on-track, warning and over-budget states.
BUDGETS = [("Groceries", "1400"), ("Dining", "400"), ("Shopping", "400")]
# Tracked up front so the dashboard has bills to show; the rest are left for "Scan" to find.
PRE_TRACKED = {"OAKWOOD APARTMENTS": "Rent", "SPOTIFY USA": "Spotify"}


@dataclass
class SeedResult:
    rows: int
    imported: ImportResult
    detection: DetectionResponse


def generate_rows(today: date) -> list[tuple[str, str, str, str]]:
    rng = random.Random(42)  # deterministic demo data
    start = add_months(today.replace(day=1), -11)
    rows: list[tuple[date, str, float, str]] = []

    for m in range(12):
        month_start = add_months(start, m)
        rows.append((month_start, "PAYROLL ACME CORP", 5200.00, "Salary"))
        rows.append((month_start + timedelta(days=1), "ACH OAKWOOD APARTMENTS", -1850.00, "Rent"))
        rows.append(
            (month_start + timedelta(days=17), "CITY UTILITIES", -round(rng.uniform(60, 140), 2),
             "Utilities")
        )
        for desc, price, category, bill_day, first, change in SUBSCRIPTIONS:
            # Hulu was cancelled four months ago, so the detector should ignore it.
            if m < first or (desc.startswith("PAYPAL *HULU") and m > 7):
                continue
            amount = change[1] if change and m >= change[0] else price
            rows.append((month_start.replace(day=bill_day), desc, -amount, category))

    day = start
    while day <= today:
        if rng.random() < 0.35:
            store = rng.choice(["WHOLE FOODS #102", "TRADER JOES #55", "SAFEWAY 0412"])
            rows.append((day, f"POS {store}", -round(rng.uniform(25, 160), 2), "Groceries"))
        if rng.random() < 0.25:
            place = rng.choice(["SQ *BLUE BOTTLE COFFEE", "CHIPOTLE 1234", "TST* SWEETGREEN"])
            rows.append((day, place, -round(rng.uniform(6, 45), 2), "Dining"))
        if rng.random() < 0.08:
            rows.append((day, "AMAZON MKTPLACE PMTS", -round(rng.uniform(15, 220), 2), "Shopping"))
        day += timedelta(days=1)

    rows = [r for r in rows if r[0] <= today]
    rows.sort(key=lambda r: r[0])
    return [(d.isoformat(), desc, f"{amt:.2f}", cat) for d, desc, amt, cat in rows]


def statement_csv(rows: list[tuple[str, str, str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "description", "amount", "category"])
    writer.writerows(rows)
    return buffer.getvalue()


def seed(db: Session, settings: Settings, today: date) -> SeedResult:
    """Create the demo user and load their data. Safe to run repeatedly."""
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(
            email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD, settings.password_hash_iterations),
        )
        db.add(user)
        db.commit()

    rows = generate_rows(today)
    imported = transactions.import_csv(db, user.id, statement_csv(rows))
    for category, limit in BUDGETS:
        budgets.upsert(db, user.id, BudgetUpsert(category=category, monthly_limit=limit))

    detection = subscriptions.detect(db, user.id, today, apply=False)
    for item in detection.detected:
        if item.merchant in PRE_TRACKED and not item.already_tracked:
            subscriptions.create(db, user.id, SubscriptionCreate(
                name=PRE_TRACKED[item.merchant],
                merchant=item.merchant,
                amount=from_cents(item.amount),
                billing_cycle=item.billing_cycle,
                next_renewal=item.next_renewal,
            ))
    return SeedResult(rows=len(rows), imported=imported, detection=detection)
