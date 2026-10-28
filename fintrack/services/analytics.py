"""Reporting queries written in raw SQL to use CTEs and window functions directly.

All queries are parameterized (no string-built user input) and run on both SQLite
(>= 3.25, for window functions) and PostgreSQL; the only dialect difference is how a
date is truncated to its month.
"""

from datetime import date

from sqlalchemy import Date, bindparam, text
from sqlalchemy.orm import Session

from ..dates import add_months
from ..models import TxnKind
from ..schemas import CategorySpend, MerchantSpend, MonthlyTrendPoint


def _month_expr(db: Session, column: str) -> str:
    if db.get_bind().dialect.name == "postgresql":
        return f"to_char({column}, 'YYYY-MM')"
    return f"strftime('%Y-%m', {column})"


def monthly_trend(db: Session, user_id: int, today: date, months: int) -> list[MonthlyTrendPoint]:
    start = add_months(today.replace(day=1), -(months - 1))
    month = _month_expr(db, "occurred_on")
    sql = text(
        f"""
        WITH monthly AS (
            SELECT {month} AS month,
                   SUM(CASE WHEN kind = :expense THEN amount_cents ELSE 0 END) AS expense_cents,
                   SUM(CASE WHEN kind = :income  THEN amount_cents ELSE 0 END) AS income_cents
            FROM transactions
            WHERE user_id = :user_id AND occurred_on >= :start
            GROUP BY {month}
        )
        SELECT month,
               income_cents,
               expense_cents,
               income_cents - expense_cents AS net_cents,
               expense_cents - LAG(expense_cents) OVER (ORDER BY month) AS expense_change_cents
        FROM monthly
        ORDER BY month
        """
    ).bindparams(bindparam("start", type_=Date))
    rows = db.execute(
        sql,
        {
            "user_id": user_id,
            "start": start,
            "expense": TxnKind.EXPENSE.value,
            "income": TxnKind.INCOME.value,
        },
    ).mappings()
    return [MonthlyTrendPoint.model_validate(dict(r)) for r in rows]


def category_breakdown(db: Session, user_id: int, start: date, end: date) -> list[CategorySpend]:
    sql = text(
        """
        SELECT COALESCE(c.name, 'Uncategorized') AS category,
               SUM(t.amount_cents) AS total_cents,
               COUNT(*) AS transactions,
               -- share of total spend: an aggregate nested inside a window function
               ROUND(100.0 * SUM(t.amount_cents) / SUM(SUM(t.amount_cents)) OVER (), 2) AS percent
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = :user_id
          AND t.kind = :expense
          AND t.occurred_on BETWEEN :start AND :end
        GROUP BY COALESCE(c.name, 'Uncategorized')
        ORDER BY total_cents DESC, category
        """
    ).bindparams(bindparam("start", type_=Date), bindparam("end", type_=Date))
    rows = db.execute(
        sql, {"user_id": user_id, "expense": TxnKind.EXPENSE.value, "start": start, "end": end}
    ).mappings()
    return [CategorySpend.model_validate({**r, "percent": float(r["percent"])}) for r in rows]


def top_merchants(
    db: Session, user_id: int, start: date, end: date, limit: int
) -> list[MerchantSpend]:
    sql = text(
        """
        SELECT RANK() OVER (ORDER BY SUM(amount_cents) DESC) AS rank,
               merchant,
               SUM(amount_cents) AS total_cents,
               COUNT(*) AS transactions
        FROM transactions
        WHERE user_id = :user_id
          AND kind = :expense
          AND occurred_on BETWEEN :start AND :end
        GROUP BY merchant
        ORDER BY total_cents DESC, merchant
        LIMIT :limit
        """
    ).bindparams(bindparam("start", type_=Date), bindparam("end", type_=Date))
    rows = db.execute(
        sql,
        {
            "user_id": user_id,
            "expense": TxnKind.EXPENSE.value,
            "start": start,
            "end": end,
            "limit": limit,
        },
    ).mappings()
    return [MerchantSpend.model_validate(dict(r)) for r in rows]
