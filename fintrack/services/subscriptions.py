from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..dates import add_cycle, roll_forward
from ..errors import BadRequestError, NotFoundError
from ..merchants import normalize_merchant
from ..models import Subscription, SubscriptionStatus, Transaction, TxnKind
from ..money import to_cents
from ..schemas import (
    DetectedSubscriptionOut,
    DetectionResponse,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionSummary,
    SubscriptionUpdate,
    UpcomingRenewal,
    UpcomingRenewals,
)
from . import categories
from .recurrence import Charge, detect_recurring

DETECTION_LOOKBACK_DAYS = 400  # enough history to see a yearly plan renew once


def create(db: Session, user_id: int, data: SubscriptionCreate) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        name=data.name,
        merchant=normalize_merchant(data.merchant or data.name),
        amount_cents=to_cents(data.amount),
        billing_cycle=data.billing_cycle,
        next_renewal=data.next_renewal,
        category_id=categories.resolve(db, user_id, data.category),
    )
    db.add(sub)
    db.commit()
    return sub


def get(db: Session, user_id: int, sub_id: int) -> Subscription:
    sub = db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user_id:
        raise NotFoundError("Subscription not found")
    return sub


def list_all(
    db: Session, user_id: int, status: SubscriptionStatus | None = None
) -> list[Subscription]:
    query = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .options(selectinload(Subscription.category))
        .order_by(Subscription.next_renewal, Subscription.name)
    )
    if status:
        query = query.where(Subscription.status == status)
    return list(db.scalars(query))


def update(db: Session, user_id: int, sub_id: int, data: SubscriptionUpdate) -> Subscription:
    sub = get(db, user_id, sub_id)
    changes = data.model_dump(exclude_unset=True)
    if "amount" in changes:
        if changes["amount"] is None:
            raise BadRequestError("amount cannot be null")
        sub.amount_cents = to_cents(changes.pop("amount"))
    if "category" in changes:
        sub.category_id = categories.resolve(db, user_id, changes.pop("category"))
    for field, value in changes.items():
        if value is not None:
            setattr(sub, field, value)
    db.commit()
    return sub


def delete(db: Session, user_id: int, sub_id: int) -> None:
    db.delete(get(db, user_id, sub_id))
    db.commit()


def upcoming(db: Session, user_id: int, today: date, within_days: int) -> UpcomingRenewals:
    """Every renewal due in [today, today + within_days], including repeats (a weekly plan
    renews ~4 times in a 30-day window). Stale next_renewal dates are rolled forward on
    the fly, so this read endpoint never has to write."""
    horizon = today + timedelta(days=within_days)
    renewals: list[UpcomingRenewal] = []
    for sub in list_all(db, user_id, SubscriptionStatus.ACTIVE):
        first = roll_forward(sub.next_renewal, sub.billing_cycle, today)
        n = 0
        while (renews_on := add_cycle(first, sub.billing_cycle, n)) <= horizon:
            renewals.append(
                UpcomingRenewal(
                    subscription_id=sub.id,
                    name=sub.name,
                    amount_cents=sub.amount_cents,
                    renews_on=renews_on,
                    days_until=(renews_on - today).days,
                )
            )
            n += 1
    renewals.sort(key=lambda r: (r.renews_on, r.name))
    return UpcomingRenewals(
        window_days=within_days,
        total_due_cents=sum(r.amount for r in renewals),
        renewals=renewals,
    )


def summary(db: Session, user_id: int) -> SubscriptionSummary:
    active = list_all(db, user_id, SubscriptionStatus.ACTIVE)
    monthly_total = sum(s.monthly_cost_cents for s in active)
    most_expensive = max(active, key=lambda s: s.monthly_cost_cents, default=None)
    return SubscriptionSummary(
        active_count=len(active),
        monthly_total_cents=monthly_total,
        annual_total_cents=monthly_total * 12,
        by_cycle=dict(Counter(s.billing_cycle for s in active)),
        most_expensive=SubscriptionOut.model_validate(most_expensive) if most_expensive else None,
    )


def detect(db: Session, user_id: int, today: date, apply: bool) -> DetectionResponse:
    """Scan recent expenses for recurring charges; optionally start tracking new ones."""
    since = today - timedelta(days=DETECTION_LOOKBACK_DAYS)
    rows = db.execute(
        select(Transaction.merchant, Transaction.occurred_on, Transaction.amount_cents).where(
            Transaction.user_id == user_id,
            Transaction.kind == TxnKind.EXPENSE,
            Transaction.occurred_on >= since,
        )
    ).all()
    found = detect_recurring((Charge(*row) for row in rows), today)

    # Any existing subscription for the merchant, including cancelled ones, counts as
    # tracked: a user who cancelled a plan shouldn't see it re-created automatically.
    tracked = {
        m.upper()
        for m in db.scalars(select(Subscription.merchant).where(Subscription.user_id == user_id))
    }

    detected, created = [], 0
    for item in found:
        already_tracked = item.merchant.upper() in tracked
        if apply and not already_tracked:
            db.add(
                Subscription(
                    user_id=user_id,
                    name=item.merchant.title(),
                    merchant=item.merchant,
                    amount_cents=item.amount_cents,
                    billing_cycle=item.billing_cycle,
                    next_renewal=item.next_renewal,
                    auto_detected=True,
                )
            )
            created += 1
        detected.append(
            DetectedSubscriptionOut.model_validate(
                {**item.__dict__, "already_tracked": already_tracked}
            )
        )
    if created:
        db.commit()
    return DetectionResponse(detected=detected, created=created)
