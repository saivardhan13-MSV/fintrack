"""Recurring-charge detection: finds subscriptions hidden in a transaction history.

Pure functions with no database access, so the algorithm is unit-testable in isolation.

Algorithm, for n charges across m merchants (O(n log n) overall, dominated by sorting):
  1. Group expense charges by normalized merchant.
  2. Sort each group by date and compute the gaps between consecutive charges.
  3. Classify the median gap as weekly / monthly / quarterly / yearly (median is robust
     to a single late or skipped payment, unlike the mean).
  4. Score confidence = 0.6 * (share of gaps within the cycle's tolerance)
                      + 0.4 * (share of amounts within 15% of the median amount).
  5. Drop series whose last charge is older than one cycle plus slack: probably cancelled.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from statistics import median

from ..dates import CYCLE_DAYS, roll_forward
from ..models import BillingCycle

# Allowed deviation (days) from the average cycle length for a gap to count as "on schedule".
CYCLE_TOLERANCE_DAYS: dict[BillingCycle, float] = {
    BillingCycle.WEEKLY: 1,
    BillingCycle.MONTHLY: 4,
    BillingCycle.QUARTERLY: 8,
    BillingCycle.YEARLY: 12,
}


@dataclass(frozen=True)
class Charge:
    merchant: str
    occurred_on: date
    amount_cents: int


@dataclass(frozen=True)
class DetectedSubscription:
    merchant: str
    billing_cycle: BillingCycle
    amount_cents: int
    occurrences: int
    last_charged_on: date
    next_renewal: date
    confidence: float
    price_change_cents: int


def classify_interval(days: float) -> BillingCycle | None:
    for cycle, expected in CYCLE_DAYS.items():
        if abs(days - expected) <= CYCLE_TOLERANCE_DAYS[cycle]:
            return cycle
    return None


def detect_recurring(
    charges: Iterable[Charge],
    today: date,
    *,
    min_occurrences: int = 3,
    min_confidence: float = 0.7,
    amount_tolerance: float = 0.15,
) -> list[DetectedSubscription]:
    by_merchant: dict[str, list[Charge]] = defaultdict(list)
    for charge in charges:
        by_merchant[charge.merchant].append(charge)

    detected: list[DetectedSubscription] = []
    for merchant, group in by_merchant.items():
        if len(group) < min_occurrences:
            continue
        group.sort(key=lambda c: c.occurred_on)
        dates = [c.occurred_on for c in group]
        amounts = [c.amount_cents for c in group]
        gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:], strict=False)]

        cycle = classify_interval(median(gaps))
        if cycle is None:
            continue
        expected, tolerance = CYCLE_DAYS[cycle], CYCLE_TOLERANCE_DAYS[cycle]

        on_schedule = sum(abs(g - expected) <= tolerance for g in gaps) / len(gaps)
        typical_amount = median(amounts)
        stable = sum(abs(a - typical_amount) <= amount_tolerance * typical_amount for a in amounts)
        confidence = round(0.6 * on_schedule + 0.4 * stable / len(amounts), 2)
        if confidence < min_confidence:
            continue

        if (today - dates[-1]).days > expected + 2 * tolerance:
            continue  # stopped charging: likely already cancelled

        detected.append(
            DetectedSubscription(
                merchant=merchant,
                billing_cycle=cycle,
                amount_cents=amounts[-1],
                occurrences=len(group),
                last_charged_on=dates[-1],
                next_renewal=roll_forward(dates[-1], cycle, today),
                confidence=confidence,
                price_change_cents=amounts[-1] - amounts[-2],
            )
        )

    detected.sort(key=lambda d: (-d.confidence, d.merchant))
    return detected
