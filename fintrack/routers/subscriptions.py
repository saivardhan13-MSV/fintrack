from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_today
from ..models import Subscription, SubscriptionStatus, User
from ..schemas import (
    DetectionResponse,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionSummary,
    SubscriptionUpdate,
    UpcomingRenewals,
)
from ..services import subscriptions

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(
    data: SubscriptionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Subscription:
    return subscriptions.create(db, user.id, data)


@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(
    status_filter: SubscriptionStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Subscription]:
    return subscriptions.list_all(db, user.id, status_filter)


# Static paths are declared before /{sub_id} so they aren't parsed as an id.
@router.get("/upcoming", response_model=UpcomingRenewals)
def upcoming_renewals(
    days: int = Query(default=30, ge=1, le=366),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> UpcomingRenewals:
    return subscriptions.upcoming(db, user.id, today, days)


@router.get("/summary", response_model=SubscriptionSummary)
def subscription_summary(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SubscriptionSummary:
    return subscriptions.summary(db, user.id)


@router.post("/detect", response_model=DetectionResponse)
def detect_subscriptions(
    apply: bool = Query(default=False, description="Start tracking newly detected subscriptions"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
) -> DetectionResponse:
    return subscriptions.detect(db, user.id, today, apply)


@router.get("/{sub_id}", response_model=SubscriptionOut)
def get_subscription(
    sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Subscription:
    return subscriptions.get(db, user.id, sub_id)


@router.patch("/{sub_id}", response_model=SubscriptionOut)
def update_subscription(
    sub_id: int,
    data: SubscriptionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Subscription:
    return subscriptions.update(db, user.id, sub_id, data)


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(
    sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    subscriptions.delete(db, user.id, sub_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
