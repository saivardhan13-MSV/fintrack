import csv
import hashlib
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..dates import parse_date
from ..errors import BadRequestError, NotFoundError
from ..merchants import normalize_merchant
from ..models import Transaction, TxnKind
from ..money import parse_amount, to_cents
from ..schemas import ImportResult, RowError, TransactionCreate, TransactionUpdate
from . import categories

REQUIRED_COLUMNS = {"date", "description", "amount"}
_IN_CLAUSE_CHUNK = 500  # stay well under SQLite's bound-parameter limit


@dataclass
class TransactionFilter:
    start: date | None = None
    end: date | None = None
    kind: TxnKind | None = None
    category_id: int | None = None
    merchant: str | None = None


def create(db: Session, user_id: int, data: TransactionCreate) -> Transaction:
    txn = Transaction(
        user_id=user_id,
        kind=data.kind,
        amount_cents=to_cents(data.amount),
        occurred_on=data.occurred_on,
        description=data.description,
        merchant=normalize_merchant(data.merchant or data.description or "UNKNOWN"),
        category_id=categories.resolve(db, user_id, data.category),
    )
    db.add(txn)
    db.commit()
    return txn


def get(db: Session, user_id: int, txn_id: int) -> Transaction:
    txn = db.get(Transaction, txn_id)
    # Same 404 for "missing" and "someone else's" so ids can't be probed across tenants.
    if txn is None or txn.user_id != user_id:
        raise NotFoundError("Transaction not found")
    return txn


def update(db: Session, user_id: int, txn_id: int, data: TransactionUpdate) -> Transaction:
    txn = get(db, user_id, txn_id)
    changes = data.model_dump(exclude_unset=True)
    if "amount" in changes:
        if changes["amount"] is None:
            raise BadRequestError("amount cannot be null")
        txn.amount_cents = to_cents(changes.pop("amount"))
    if "merchant" in changes:
        merchant = changes.pop("merchant")
        txn.merchant = normalize_merchant(merchant or txn.description or "UNKNOWN")
    if "category" in changes:
        txn.category_id = categories.resolve(db, user_id, changes.pop("category"))
    for field, value in changes.items():
        if value is not None:
            setattr(txn, field, value)
    db.commit()
    return txn


def delete(db: Session, user_id: int, txn_id: int) -> None:
    db.delete(get(db, user_id, txn_id))
    db.commit()


def search(
    db: Session, user_id: int, filters: TransactionFilter, limit: int, offset: int
) -> tuple[list[Transaction], int]:
    query = select(Transaction).where(Transaction.user_id == user_id)
    if filters.start:
        query = query.where(Transaction.occurred_on >= filters.start)
    if filters.end:
        query = query.where(Transaction.occurred_on <= filters.end)
    if filters.kind:
        query = query.where(Transaction.kind == filters.kind)
    if filters.category_id:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.merchant:
        query = query.where(Transaction.merchant.ilike(f"%{filters.merchant}%"))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.options(selectinload(Transaction.category))  # avoids N+1 category lookups
        .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def import_csv(db: Session, user_id: int, content: str) -> ImportResult:
    """Bulk-import a bank statement CSV with columns date, description, amount[, category].

    Negative amounts are expenses, positive amounts income. The import is idempotent:
    each row gets a content hash, and rows whose hash already exists are skipped. The
    hash includes the row's occurrence count within the file, so two genuinely identical
    purchases on the same day are both kept while a re-upload of the file adds nothing.
    Invalid rows are reported back without aborting the rest of the import.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise BadRequestError("CSV file is empty")
    columns = {name.strip().lower(): name for name in reader.fieldnames}
    missing = REQUIRED_COLUMNS - columns.keys()
    if missing:
        raise BadRequestError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    def cell(row: dict[str, str | None], column: str) -> str:
        return (row.get(columns[column]) or "").strip() if column in columns else ""

    errors: list[RowError] = []
    pending: dict[str, Transaction] = {}
    pending_categories: dict[str, str] = {}
    occurrences: Counter[str] = Counter()

    for line_no, row in enumerate(reader, start=2):  # line 1 is the header
        try:
            occurred_on = parse_date(cell(row, "date"))
            amount = parse_amount(cell(row, "amount"))
            description = cell(row, "description")
            if not description:
                raise ValueError("description is required")
            if amount == 0:
                raise ValueError("amount must be non-zero")
        except ValueError as exc:
            errors.append(RowError(row=line_no, message=str(exc)))
            continue

        kind = TxnKind.EXPENSE if amount < 0 else TxnKind.INCOME
        cents = to_cents(abs(amount))
        base = f"{occurred_on.isoformat()}|{kind.value}|{cents}|{description.lower()}"
        occurrences[base] += 1
        key = hashlib.sha256(f"{base}|{occurrences[base]}".encode()).hexdigest()

        pending[key] = Transaction(
            user_id=user_id,
            kind=kind,
            amount_cents=cents,
            occurred_on=occurred_on,
            description=description[:255],
            merchant=normalize_merchant(description),
            dedupe_key=key,
        )
        if category := cell(row, "category"):
            pending_categories[key] = category

    existing: set[str] = set()
    keys = list(pending)
    for i in range(0, len(keys), _IN_CLAUSE_CHUNK):
        chunk = keys[i : i + _IN_CLAUSE_CHUNK]
        existing.update(
            db.scalars(
                select(Transaction.dedupe_key).where(
                    Transaction.user_id == user_id, Transaction.dedupe_key.in_(chunk)
                )
            )
        )

    category_ids: dict[str, int] = {}
    new_rows = []
    for key, txn in pending.items():
        if key in existing:
            continue
        if name := pending_categories.get(key):
            if name.lower() not in category_ids:
                category_ids[name.lower()] = categories.get_or_create(db, user_id, name).id
            txn.category_id = category_ids[name.lower()]
        new_rows.append(txn)

    db.add_all(new_rows)
    db.commit()
    return ImportResult(
        imported=len(new_rows), duplicates_skipped=len(existing), errors=errors
    )
