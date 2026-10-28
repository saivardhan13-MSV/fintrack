from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_current_user, get_db, get_settings_dep
from ..errors import ConflictError, UnauthorizedError
from ..models import User
from ..schemas import Token, UserCreate, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    data: UserCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("Email is already registered")
    user = User(
        email=email,
        hashed_password=hash_password(data.password, settings.password_hash_iterations),
    )
    db.add(user)
    db.commit()
    return user


@router.post("/token", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Token:
    """OAuth2 password flow: send `username` (your email) and `password` as form fields."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    # One generic message whether the email or the password was wrong (no user enumeration).
    if user is None or not verify_password(form.password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password")
    return Token(access_token=create_access_token(user.id, settings))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
