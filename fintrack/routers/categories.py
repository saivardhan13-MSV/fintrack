from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Category, User
from ..schemas import CategoryCreate, CategoryOut
from ..services import categories

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Category]:
    return categories.list_all(db, user.id)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Category:
    return categories.create(db, user.id, data.name)
