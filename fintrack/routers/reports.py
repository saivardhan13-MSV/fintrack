from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dates import month_bounds
from ..deps import get_current_user, get_db, get_month, get_today
from ..errors import BadRequestError
from ..models import User
from ..schemas import CategorySpend, Dashboard, MerchantSpend, MonthlyTrendPoint
from ..services import analytics, dashboard

router = APIRouter(prefix="/reports", tags=["reports"])


def _range(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Defaults to the current calendar month."""
    month_start, month_end = month_bounds(today.year, today.month)
    start, end = start or month_start, end or month_end
    if start > end:
        raise BadRequestError("start must be on or before end")
    return start, end


@router.get("/dashboard", response_model=Dashboard)
def dashboard_summary(
    month: tuple[int, int] = Depends(get_month),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> Dashboard:
    """Income, expenses, balance, category spend, budget usage and upcoming bills."""
    return dashboard.build(db, user.id, *month, today)


@router.get("/monthly-trend", response_model=list[MonthlyTrendPoint])
def monthly_trend(
    months: int = Query(default=12, ge=1, le=60),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> list[MonthlyTrendPoint]:
    return analytics.monthly_trend(db, user.id, today, months)


@router.get("/category-breakdown", response_model=list[CategorySpend])
def category_breakdown(
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> list[CategorySpend]:
    return analytics.category_breakdown(db, user.id, *_range(start, end, today))


@router.get("/top-merchants", response_model=list[MerchantSpend])
def top_merchants(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> list[MerchantSpend]:
    return analytics.top_merchants(db, user.id, *_range(start, end, today), limit)
