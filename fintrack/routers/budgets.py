from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_month, get_today
from ..models import User
from ..schemas import BudgetOut, BudgetStatus, BudgetUpsert
from ..services import budgets

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.put("", response_model=BudgetOut)
def upsert_budget(
    data: BudgetUpsert, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> BudgetOut:
    return budgets.upsert(db, user.id, data)


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[BudgetOut]:
    return budgets.list_all(db, user.id)


@router.get("/status", response_model=list[BudgetStatus])
def budget_status(
    month: tuple[int, int] = Depends(get_month),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> list[BudgetStatus]:
    return budgets.statuses(db, user.id, *month, today)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    budgets.delete(db, user.id, budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
