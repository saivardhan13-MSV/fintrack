from datetime import date

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_current_user, get_db, get_settings_dep
from ..errors import BadRequestError, PayloadTooLargeError
from ..models import Transaction, TxnKind, User
from ..schemas import ImportResult, Page, TransactionCreate, TransactionOut, TransactionUpdate
from ..services import transactions
from ..services.transactions import TransactionFilter

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Transaction:
    return transactions.create(db, user.id, data)


@router.get("", response_model=Page[TransactionOut])
def list_transactions(
    start: date | None = None,
    end: date | None = None,
    kind: TxnKind | None = None,
    category_id: int | None = None,
    merchant: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[TransactionOut]:
    if start and end and start > end:
        raise BadRequestError("start must be on or before end")
    filters = TransactionFilter(start, end, kind, category_id, merchant)
    items, total = transactions.search(db, user.id, filters, limit, offset)
    return Page[TransactionOut](
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/import", response_model=ImportResult)
async def import_transactions(
    file: UploadFile = File(..., description="CSV: date, description, amount[, category]"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> ImportResult:
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"File exceeds {settings.max_upload_bytes} bytes")
    try:
        content = raw.decode("utf-8-sig")  # tolerate the BOM Excel adds to CSV exports
    except UnicodeDecodeError:
        raise BadRequestError("File must be UTF-8 encoded CSV") from None
    return transactions.import_csv(db, user.id, content)


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(
    txn_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Transaction:
    return transactions.get(db, user.id, txn_id)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int,
    data: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transaction:
    return transactions.update(db, user.id, txn_id, data)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    txn_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    transactions.delete(db, user.id, txn_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
