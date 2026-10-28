from __future__ import annotations

import enum
from datetime import date, datetime
from fractions import Fraction

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TxnKind(enum.StrEnum):
    EXPENSE = "expense"
    INCOME = "income"


class BillingCycle(enum.StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SubscriptionStatus(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


def _enum(cls: type[enum.Enum]) -> Enum:
    # Store the lowercase value as VARCHAR: portable across SQLite/Postgres and readable in raw SQL.
    return Enum(
        cls,
        native_enum=False,
        length=16,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_category_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Makes CSV import idempotent: re-uploading the same statement inserts nothing.
        UniqueConstraint("user_id", "dedupe_key", name="uq_txn_user_dedupe"),
        # Covers the hot paths: date-range listing/reports and per-merchant recurrence scans.
        Index("ix_txn_user_date", "user_id", "occurred_on"),
        Index("ix_txn_user_merchant", "user_id", "merchant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[TxnKind] = mapped_column(_enum(TxnKind))
    # Money is stored as integer cents to avoid floating-point rounding errors.
    amount_cents: Mapped[int] = mapped_column(Integer)
    merchant: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(255), default="")
    occurred_on: Mapped[date] = mapped_column(Date)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category | None] = relationship()

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_sub_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128))
    merchant: Mapped[str] = mapped_column(String(128))
    amount_cents: Mapped[int] = mapped_column(Integer)
    billing_cycle: Mapped[BillingCycle] = mapped_column(_enum(BillingCycle))
    next_renewal: Mapped[date] = mapped_column(Date)
    status: Mapped[SubscriptionStatus] = mapped_column(
        _enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category | None] = relationship()

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    @property
    def monthly_cost_cents(self) -> int:
        return monthly_cost_cents(self.amount_cents, self.billing_cycle)


# How many times per month each cycle bills, as exact fractions (weekly = 52 / 12).
_PER_MONTH = {
    BillingCycle.WEEKLY: Fraction(52, 12),
    BillingCycle.MONTHLY: Fraction(1),
    BillingCycle.QUARTERLY: Fraction(1, 3),
    BillingCycle.YEARLY: Fraction(1, 12),
}


def monthly_cost_cents(amount_cents: int, cycle: BillingCycle) -> int:
    """Normalise any billing cycle to an equivalent monthly cost so plans are comparable."""
    return round(amount_cents * _PER_MONTH[cycle])


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_budget_user_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    monthly_limit_cents: Mapped[int] = mapped_column(Integer)

    category: Mapped[Category] = relationship()
