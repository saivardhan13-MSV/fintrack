from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

from .models import BillingCycle, SubscriptionStatus, TxnKind
from .money import from_cents

T = TypeVar("T")

# Incoming money: positive, at most 2 decimal places (e.g. 15.49).
MoneyIn = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
# Outgoing money: held as integer cents internally, serialized as an exact decimal string "15.49".
Cents = Annotated[int, PlainSerializer(lambda c: str(from_cents(c)), return_type=str)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth -----------------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Categories -----------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class CategoryOut(ORMModel):
    id: int
    name: str


# --- Transactions ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    kind: TxnKind = TxnKind.EXPENSE
    amount: MoneyIn
    occurred_on: date
    description: str = Field(default="", max_length=255)
    merchant: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=64)


class TransactionUpdate(BaseModel):
    kind: TxnKind | None = None
    amount: MoneyIn | None = None
    occurred_on: date | None = None
    description: str | None = Field(default=None, max_length=255)
    merchant: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=64)


class TransactionOut(ORMModel):
    id: int
    kind: TxnKind
    amount: Cents = Field(validation_alias="amount_cents")
    occurred_on: date
    merchant: str
    description: str
    category: str | None = Field(validation_alias="category_name")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class RowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    imported: int
    duplicates_skipped: int
    errors: list[RowError]


# --- Subscriptions --------------------------------------------------------------------------

class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    merchant: str | None = Field(default=None, max_length=128)
    amount: MoneyIn
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    next_renewal: date
    category: str | None = Field(default=None, max_length=64)


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    amount: MoneyIn | None = None
    billing_cycle: BillingCycle | None = None
    next_renewal: date | None = None
    status: SubscriptionStatus | None = None
    category: str | None = Field(default=None, max_length=64)


class SubscriptionOut(ORMModel):
    id: int
    name: str
    merchant: str
    amount: Cents = Field(validation_alias="amount_cents")
    monthly_cost: Cents = Field(validation_alias="monthly_cost_cents")
    billing_cycle: BillingCycle
    next_renewal: date
    status: SubscriptionStatus
    auto_detected: bool
    category: str | None = Field(validation_alias="category_name")


class UpcomingRenewal(BaseModel):
    subscription_id: int
    name: str
    amount: Cents = Field(validation_alias="amount_cents")
    renews_on: date
    days_until: int


class UpcomingRenewals(BaseModel):
    window_days: int
    total_due: Cents = Field(validation_alias="total_due_cents")
    renewals: list[UpcomingRenewal]


class SubscriptionSummary(BaseModel):
    active_count: int
    monthly_total: Cents = Field(validation_alias="monthly_total_cents")
    annual_total: Cents = Field(validation_alias="annual_total_cents")
    by_cycle: dict[BillingCycle, int]
    most_expensive: SubscriptionOut | None


class DetectedSubscriptionOut(ORMModel):
    merchant: str
    billing_cycle: BillingCycle
    amount: Cents = Field(validation_alias="amount_cents")
    occurrences: int
    last_charged_on: date
    next_renewal: date
    confidence: float
    price_change: Cents = Field(validation_alias="price_change_cents")
    already_tracked: bool


class DetectionResponse(BaseModel):
    detected: list[DetectedSubscriptionOut]
    created: int


# --- Budgets --------------------------------------------------------------------------------

class BudgetUpsert(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    monthly_limit: MoneyIn


class BudgetOut(BaseModel):
    id: int
    category: str
    monthly_limit: Cents = Field(validation_alias="monthly_limit_cents")


class BudgetStatus(BaseModel):
    budget_id: int
    category: str
    limit: Cents = Field(validation_alias="limit_cents")
    spent: Cents = Field(validation_alias="spent_cents")
    remaining: Cents = Field(validation_alias="remaining_cents")
    projected: Cents = Field(validation_alias="projected_cents")
    percent_used: float
    status: Literal["ok", "at_risk", "warning", "exceeded"]


# --- Reports --------------------------------------------------------------------------------

class MonthlyTrendPoint(BaseModel):
    month: str
    income: Cents = Field(validation_alias="income_cents")
    expenses: Cents = Field(validation_alias="expense_cents")
    net: Cents = Field(validation_alias="net_cents")
    expense_change: Cents | None = Field(validation_alias="expense_change_cents")


class CategorySpend(BaseModel):
    category: str
    total: Cents = Field(validation_alias="total_cents")
    transactions: int
    percent: float


class MerchantSpend(BaseModel):
    rank: int
    merchant: str
    total: Cents = Field(validation_alias="total_cents")
    transactions: int


class Dashboard(BaseModel):
    """Everything the dashboard page needs for one month, in a single round trip."""

    month: str
    income: Cents = Field(validation_alias="income_cents")
    expenses: Cents = Field(validation_alias="expense_cents")
    balance: Cents = Field(validation_alias="balance_cents")
    savings_rate: float | None
    subscriptions_monthly: Cents = Field(validation_alias="subscriptions_monthly_cents")
    categories: list[CategorySpend]
    budgets: list[BudgetStatus]
    upcoming_bills: UpcomingRenewals
