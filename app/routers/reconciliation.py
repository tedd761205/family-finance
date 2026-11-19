from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.account import Account
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.reconciliation import ReconciliationMatch, ReconciliationSession
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.reconciliation import ReconciliationSessionCreate
from app.services.audit_log import add_audit_log

router = APIRouter(prefix="/reconciliations", tags=["Reconciliations"])
TAIPEI = ZoneInfo("Asia/Taipei")


def _authorize(db: Session, user: User, family_id: int, permission: str) -> tuple[str, list]:
    try:
        _, roles = require_permission(db, user.id, family_id, permission)
        scope = require_data_scope(db, roles, family_id, "reconciliation")
        return scope, roles
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _require_scope(db: Session, roles: list, family_id: int, resource: str) -> str:
    try:
        return require_data_scope(db, roles, family_id, resource)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _period_bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    start = datetime.combine(period_start, time.min, tzinfo=TAIPEI).astimezone(timezone.utc)
    end_exclusive = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=TAIPEI
    ).astimezone(timezone.utc)
    return start, end_exclusive


def _session_summary(session: ReconciliationSession) -> dict:
    return {
        "id": session.id,
        "family_id": session.family_id,
        "account_id": session.account_id,
        "source_batch_id": session.source_batch_id,
        "period_start": session.period_start,
        "period_end": session.period_end,
        "currency_code": session.currency_code,
        "status": session.status,
        "opening_balance": str(session.opening_balance) if session.opening_balance is not None else None,
        "closing_balance": str(session.closing_balance) if session.closing_balance is not None else None,
        "statement_row_count": session.statement_row_count,
        "matched_row_count": session.matched_row_count,
        "difference_row_count": session.difference_row_count,
        "created_by": session.created_by,
        "completed_by": session.completed_by,
        "completed_at": session.completed_at,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _row_state(row: BankImportRow, allocated_amount: Decimal) -> dict:
    amount = row.amount or Decimal("0")
    allocated = allocated_amount or Decimal("0")
    remaining = amount - allocated
    if allocated <= 0:
        state = "unmatched"
    elif remaining == 0:
        state = "matched"
    else:
        state = "partially_matched"
    return {
        "id": row.id,
        "row_number": row.row_number,
        "transaction_date": row.transaction_date,
        "transaction_type": row.transaction_type,
        "amount": str(amount),
        "currency_code": row.currency_code,
        "description": row.description,
        "external_reference": row.external_reference,
        "reconciliation_status": state,
        "matched_amount": str(allocated),
        "remaining_amount": str(remaining),
    }


def _get_session(
    db: Session, family_id: int, session_id: int, scope: str, user: User
) -> ReconciliationSession:
    query = db.query(ReconciliationSession).filter(
        ReconciliationSession.id == session_id,
        ReconciliationSession.family_id == family_id,
    )
    if scope == "own":
        query = query.filter(ReconciliationSession.created_by == user.id)
    session = query.first()
    if session is None:
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    return session


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="建立銀行／信用卡對帳工作階段",
)
def create_reconciliation_session(
    data: ReconciliationSessionCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _, roles = require_permission(db, current_user.id, family_id, "reconciliation.create")
        require_data_scope(db, roles, family_id, "reconciliation")
        account_scope = _require_scope(db, roles, family_id, "accounts")
        import_scope = _require_scope(db, roles, family_id, "imports")
        transaction_scope = _require_scope(db, roles, family_id, "transactions")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    account_query = db.query(Account).filter(
        Account.id == data.account_id,
        Account.family_id == family_id,
        Account.is_active.is_(True),
    )
    if account_scope == "own":
        account_query = account_query.filter(Account.created_by == current_user.id)
    account = account_query.first()
    if account is None:
        raise HTTPException(status_code=404, detail="找不到可使用的家庭帳戶")

    batch_query = db.query(BankImportBatch).filter(
        BankImportBatch.id == data.source_batch_id,
        BankImportBatch.family_id == family_id,
        BankImportBatch.account_id == data.account_id,
    ).with_for_update()
    if import_scope == "own":
        batch_query = batch_query.filter(BankImportBatch.created_by == current_user.id)
    batch = batch_query.first()
    if batch is None:
        raise HTTPException(status_code=404, detail="找不到此家庭帳戶的匯入批次")
    if batch.status != "confirmed" or batch.confirmed_at is None:
        raise HTTPException(status_code=409, detail="只有已人工確認並正式入帳的匯入批次可以對帳")

    start_utc, end_utc = _period_bounds(data.period_start, data.period_end)
    row_query = db.query(BankImportRow.id).filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == batch.id,
        BankImportRow.status == "imported",
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    )
    statement_row_count = row_query.count()
    if statement_row_count == 0:
        raise HTTPException(status_code=422, detail="指定對帳期間沒有已入帳的銀行明細")
    if transaction_scope == "own":
        owned_transaction_count = db.query(Transaction.id).join(
            BankImportRow, Transaction.import_row_id == BankImportRow.id
        ).filter(
            Transaction.family_id == family_id,
            Transaction.account_id == account.id,
            Transaction.created_by == current_user.id,
            BankImportRow.family_id == family_id,
            BankImportRow.batch_id == batch.id,
            BankImportRow.status == "imported",
            BankImportRow.transaction_date >= start_utc,
            BankImportRow.transaction_date < end_utc,
        ).count()
        if owned_transaction_count != statement_row_count:
            raise HTTPException(status_code=404, detail="找不到完整的本人帳務資料範圍")

    session = ReconciliationSession(
        family_id=family_id,
        account_id=account.id,
        source_batch_id=batch.id,
        period_start=data.period_start,
        period_end=data.period_end,
        currency_code=account.currency_code,
        status="in_progress",
        opening_balance=data.opening_balance,
        closing_balance=data.closing_balance,
        statement_row_count=statement_row_count,
        matched_row_count=0,
        difference_row_count=statement_row_count,
        created_by=current_user.id,
    )
    db.add(session)
    try:
        db.flush()
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="reconciliation_session",
            entity_id=session.id,
            new_values={
                "account_id": account.id,
                "source_batch_id": batch.id,
                "period_start": data.period_start,
                "period_end": data.period_end,
                "statement_row_count": statement_row_count,
            },
            description="建立銀行／信用卡對帳工作階段",
        )
        db.commit()
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="此帳戶及對帳期間已存在工作階段，或此匯入批次已被使用",
        ) from exc

    return {"success": True, "session": _session_summary(session)}


@router.get("/sessions", summary="查詢家庭對帳工作階段")
def list_reconciliation_sessions(
    family_id: int = Query(..., gt=0),
    account_id: int | None = Query(None, gt=0),
    session_status: str | None = Query(None, alias="status", pattern="^(draft|in_progress|completed|cancelled)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    query = db.query(ReconciliationSession).filter(
        ReconciliationSession.family_id == family_id
    )
    if scope == "own":
        query = query.filter(ReconciliationSession.created_by == current_user.id)
    if account_scope == "own":
        query = query.join(
            Account,
            (Account.id == ReconciliationSession.account_id)
            & (Account.family_id == ReconciliationSession.family_id),
        ).filter(Account.created_by == current_user.id)
    if account_id is not None:
        query = query.filter(ReconciliationSession.account_id == account_id)
    if session_status is not None:
        query = query.filter(ReconciliationSession.status == session_status)

    total = query.count()
    sessions = query.order_by(
        ReconciliationSession.period_start.desc(),
        ReconciliationSession.id.desc(),
    ).offset(skip).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "sessions": [_session_summary(item) for item in sessions],
    }


@router.get("/sessions/{session_id}", summary="查詢對帳工作階段與銀行明細")
def get_reconciliation_session(
    session_id: int,
    family_id: int = Query(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user)
    if account_scope == "own":
        owned_account = db.query(Account.id).filter(
            Account.id == session.account_id,
            Account.family_id == family_id,
            Account.created_by == current_user.id,
        ).first()
        if owned_account is None:
            raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)

    row_query = db.query(BankImportRow)
    if transaction_scope == "own":
        row_query = row_query.join(Transaction, Transaction.import_row_id == BankImportRow.id).filter(
            Transaction.family_id == family_id,
            Transaction.created_by == current_user.id,
            Transaction.account_id == session.account_id,
        )
    row_query = row_query.filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status == "imported",
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    )
    total_rows = row_query.count()
    rows = row_query.order_by(BankImportRow.row_number.asc()).offset(skip).limit(limit).all()
    row_ids = [row.id for row in rows]
    allocations = {}
    if row_ids:
        values = db.query(
            ReconciliationMatch.bank_import_row_id,
            func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0),
        ).filter(
            ReconciliationMatch.family_id == family_id,
            ReconciliationMatch.session_id == session.id,
            ReconciliationMatch.bank_import_row_id.in_(row_ids),
            ReconciliationMatch.status == "active",
        ).group_by(ReconciliationMatch.bank_import_row_id).all()
        allocations = {row_id: amount for row_id, amount in values}

    row_items = [_row_state(row, allocations.get(row.id, Decimal("0"))) for row in rows]
    return {
        "success": True,
        "session": _session_summary(session),
        "total_rows": total_rows,
        "rows": row_items,
        "pagination": {"skip": skip, "limit": limit},
    }
