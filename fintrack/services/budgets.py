from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..dates import month_bounds
from ..errors import NotFoundError
from ..models import Budget, Transaction, TxnKind
from ..money import to_cents
from ..schemas import BudgetOut, BudgetStatus, BudgetUpsert
from . import categories

WARNING_THRESHOLD_PCT = 80.0


def _out(budget: Budget) -> BudgetOut:
    return BudgetOut(
        id=budget.id,
        category=budget.category.name,
        monthly_limit_cents=budget.monthly_limit_cents,
    )


def upsert(db: Session, user_id: int, data: BudgetUpsert) -> BudgetOut:
    """PUT semantics: one budget per category, created or replaced."""
    category = categories.get_or_create(db, user_id, data.category)
    budget = db.scalar(
        select(Budget).where(Budget.user_id == user_id, Budget.category_id == category.id)
    )
    if budget is None:
        budget = Budget(user_id=user_id, category_id=category.id, monthly_limit_cents=0)
        db.add(budget)
    budget.monthly_limit_cents = to_cents(data.monthly_limit)
    db.commit()
    return _out(budget)


def list_all(db: Session, user_id: int) -> list[BudgetOut]:
    budgets = db.scalars(
        select(Budget).where(Budget.user_id == user_id).options(selectinload(Budget.category))
    )
    return sorted((_out(b) for b in budgets), key=lambda b: b.category.lower())


def delete(db: Session, user_id: int, budget_id: int) -> None:
    budget = db.get(Budget, budget_id)
    if budget is None or budget.user_id != user_id:
        raise NotFoundError("Budget not found")
    db.delete(budget)
    db.commit()


def classify(spent: int, limit: int, projected: int) -> str:
    if spent > limit:
        return "exceeded"
    if limit and spent * 100 >= limit * WARNING_THRESHOLD_PCT:
        return "warning"
    if projected > limit:
        return "at_risk"  # under budget today, but on pace to overspend by month end
    return "ok"


def statuses(db: Session, user_id: int, year: int, month: int, today: date) -> list[BudgetStatus]:
    start, end = month_bounds(year, month)
    # One grouped aggregate for all categories instead of a query per budget.
    rows = db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount_cents))
        .where(
            Transaction.user_id == user_id,
            Transaction.kind == TxnKind.EXPENSE,
            Transaction.occurred_on.between(start, end),
        )
        .group_by(Transaction.category_id)
    )
    spent_by_category = {category_id: total for category_id, total in rows}

    result = []
    for b in db.scalars(
        select(Budget).where(Budget.user_id == user_id).options(selectinload(Budget.category))
    ):
        spent = int(spent_by_category.get(b.category_id) or 0)
        limit = b.monthly_limit_cents
        if start <= today <= end:
            # Linear run-rate projection: spend so far scaled to the full month.
            projected = round(spent * end.day / today.day)
        else:
            projected = spent
        result.append(
            BudgetStatus(
                budget_id=b.id,
                category=b.category.name,
                limit_cents=limit,
                spent_cents=spent,
                remaining_cents=limit - spent,
                projected_cents=projected,
                percent_used=round(spent * 100 / limit, 1) if limit else 0.0,
                status=classify(spent, limit, projected),
            )
        )
    result.sort(key=lambda s: -s.percent_used)
    return result
