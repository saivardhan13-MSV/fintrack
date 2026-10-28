from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..dates import month_bounds
from ..models import Transaction, TxnKind
from ..schemas import Dashboard
from . import analytics, budgets, subscriptions

UPCOMING_BILLS_DAYS = 30


def build(db: Session, user_id: int, year: int, month: int, today: date) -> Dashboard:
    start, end = month_bounds(year, month)
    rows = db.execute(
        select(Transaction.kind, func.sum(Transaction.amount_cents))
        .where(Transaction.user_id == user_id, Transaction.occurred_on.between(start, end))
        .group_by(Transaction.kind)
    )
    totals = {kind: int(total or 0) for kind, total in rows}
    income = totals.get(TxnKind.INCOME, 0)
    expenses = totals.get(TxnKind.EXPENSE, 0)
    balance = income - expenses

    return Dashboard(
        month=f"{year:04d}-{month:02d}",
        income_cents=income,
        expense_cents=expenses,
        balance_cents=balance,
        savings_rate=round(balance * 100 / income, 1) if income else None,
        subscriptions_monthly_cents=subscriptions.summary(db, user_id).monthly_total,
        categories=analytics.category_breakdown(db, user_id, start, end),
        budgets=budgets.statuses(db, user_id, year, month, today),
        upcoming_bills=subscriptions.upcoming(db, user_id, today, UPCOMING_BILLS_DAYS),
    )
