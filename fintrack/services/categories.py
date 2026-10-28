from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ConflictError
from ..models import Category


def find(db: Session, user_id: int, name: str) -> Category | None:
    return db.scalar(
        select(Category).where(
            Category.user_id == user_id, func.lower(Category.name) == name.strip().lower()
        )
    )


def get_or_create(db: Session, user_id: int, name: str) -> Category:
    """Categories are matched case-insensitively and created on first use."""
    category = find(db, user_id, name)
    if category is None:
        category = Category(user_id=user_id, name=name.strip())
        db.add(category)
        db.flush()
    return category


def resolve(db: Session, user_id: int, name: str | None) -> int | None:
    return get_or_create(db, user_id, name).id if name and name.strip() else None


def create(db: Session, user_id: int, name: str) -> Category:
    if find(db, user_id, name):
        raise ConflictError(f"Category '{name}' already exists")
    category = Category(user_id=user_id, name=name.strip())
    db.add(category)
    db.commit()
    return category


def list_all(db: Session, user_id: int) -> list[Category]:
    query = select(Category).where(Category.user_id == user_id).order_by(Category.name)
    return list(db.scalars(query))
