from collections.abc import Iterator
from datetime import date

from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import Settings
from .errors import UnauthorizedError
from .models import User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    """One session per request, always closed; services decide when to commit."""
    db: Session = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_today() -> date:
    """Injected 'today' so date-dependent business logic is deterministic under test."""
    return date.today()


def get_month(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="YYYY-MM; defaults to the current month",
    ),
    today: date = Depends(get_today),
) -> tuple[int, int]:
    """Shared `?month=YYYY-MM` query parameter, resolved to (year, month)."""
    if month is None:
        return today.year, today.month
    year, mon = month.split("-")
    return int(year), int(mon)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    user_id = decode_access_token(token, settings)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise UnauthorizedError("Invalid or expired token")
    return user
