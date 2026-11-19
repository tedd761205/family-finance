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
from app.schemas.reconciliation import (
    ReconciliationMatchCreate,
    ReconciliationMatchVoid,
    ReconciliationSessionCreate,
)
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


def _refresh_session_counts(db: Session, session: ReconciliationSession) -> None:
    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    rows = db.query(BankImportRow).filter(
        BankImportRow.family_id == session.family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status.in_(["imported", "duplicate"]),
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    ).all()
    totals = {}
    if rows:
        values = db.query(
            ReconciliationMatch.bank_import_row_id,
            func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0),
        ).filter(
            ReconciliationMatch.family_id == session.family_id,
            ReconciliationMatch.session_id == session.id,
            ReconciliationMatch.status == "active",
        ).group_by(ReconciliationMatch.bank_import_row_id).all()
        totals = {row_id: amount for row_id, amount in values}
    matched = sum(
        1 for row in rows
        if totals.get(row.id, Decimal("0")) == (row.amount or Decimal("0"))
    )
    session.statement_row_count = len(rows)
    session.matched_row_count = matched
    session.difference_row_count = len(rows) - matched


def _get_session(
    db: Session, family_id: int, session_id: int, scope: str, user: User,
    lock: bool = False,
) -> ReconciliationSession:
    query = db.query(ReconciliationSession).filter(
        ReconciliationSession.id == session_id,
        ReconciliationSession.family_id == family_id,
    )
    if scope == "own":
        query = query.filter(ReconciliationSession.created_by == user.id)
    if lock:
        query = query.with_for_update()
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
        raise HTTPException(status_code=409, detail="只有已確認匯入的銀行明細批次可以對帳")

    start_utc, end_utc = _period_bounds(data.period_start, data.period_end)
    row_query = db.query(BankImportRow.id).filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == batch.id,
        BankImportRow.status.in_(["imported", "duplicate"]),
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    )
    statement_row_count = row_query.count()
    if statement_row_count == 0:
        raise HTTPException(status_code=422, detail="指定對帳期間沒有已入帳的銀行明細")

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

    row_query = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status.in_(["imported", "duplicate"]),
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

    match_query = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.bank_import_row_id.in_(row_ids),
        ReconciliationMatch.status == "active",
    )
    if transaction_scope == "own":
        match_query = match_query.join(
            Transaction, Transaction.id == ReconciliationMatch.transaction_id
        ).filter(Transaction.created_by == current_user.id)
    match_items = match_query.order_by(ReconciliationMatch.id.asc()).all()
    matches_by_row = {}
    for match in match_items:
        matches_by_row.setdefault(match.bank_import_row_id, []).append({
            "id": match.id,
            "transaction_id": match.transaction_id,
            "allocated_amount": str(match.allocated_amount),
            "matched_by": match.matched_by,
            "matched_at": match.matched_at,
        })

    row_items = []
    for row in rows:
        item = _row_state(row, allocations.get(row.id, Decimal("0")))
        item["matches"] = matches_by_row.get(row.id, [])
        row_items.append(item)
    return {
        "success": True,
        "session": _session_summary(session),
        "total_rows": total_rows,
        "rows": row_items,
        "pagination": {"skip": skip, "limit": limit},
    }


@router.post(
    "/sessions/{session_id}/matches",
    status_code=status.HTTP_201_CREATED,
    summary="人工配對銀行明細與正式交易",
)
def create_reconciliation_match(
    session_id: int,
    data: ReconciliationMatchCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.match")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以新增配對")

    if account_scope == "own":
        owned_account = db.query(Account.id).filter(
            Account.id == session.account_id,
            Account.family_id == family_id,
            Account.created_by == current_user.id,
        ).first()
        if owned_account is None:
            raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    row = db.query(BankImportRow).filter(
        BankImportRow.id == data.bank_import_row_id,
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status.in_(["imported", "duplicate"]),
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到此對帳期間的銀行明細")

    transaction_query = db.query(Transaction).filter(
        Transaction.id == data.transaction_id,
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.is_voided.is_(False),
    )
    if transaction_scope == "own":
        transaction_query = transaction_query.filter(Transaction.created_by == current_user.id)
    transaction = transaction_query.with_for_update().first()
    if transaction is None:
        raise HTTPException(status_code=404, detail="找不到可配對的家庭正式交易")

    if transaction.import_row_id not in (None, row.id):
        raise HTTPException(status_code=409, detail="此正式交易已連結其他銀行匯入明細")
    if row.transaction_type != transaction.transaction_type:
        raise HTTPException(status_code=422, detail="銀行明細與正式交易的收支方向不同")
    if row.currency_code != session.currency_code or transaction.currency_code != session.currency_code:
        raise HTTPException(status_code=422, detail="銀行明細與正式交易的幣別必須與對帳帳戶一致")
    if row.currency_code != transaction.currency_code:
        raise HTTPException(status_code=422, detail="銀行明細與正式交易的幣別不同")
    if data.allocated_amount != transaction.amount:
        raise HTTPException(
            status_code=422,
            detail="配對金額必須等於正式交易完整金額；如需拆分銀行明細，請配對多筆完整交易",
        )

    existing_transaction_match = db.query(ReconciliationMatch.id).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.transaction_id == transaction.id,
        ReconciliationMatch.status == "active",
    ).first()
    if existing_transaction_match is not None:
        raise HTTPException(status_code=409, detail="此正式交易已與其他銀行明細配對")

    allocated_before = db.query(
        func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0)
    ).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.bank_import_row_id == row.id,
        ReconciliationMatch.status == "active",
    ).scalar() or Decimal("0")
    remaining = (row.amount or Decimal("0")) - allocated_before
    if data.allocated_amount > remaining:
        raise HTTPException(
            status_code=409,
            detail=f"配對金額超過銀行明細剩餘金額（剩餘 {remaining} {row.currency_code}）",
        )

    match = ReconciliationMatch(
        family_id=family_id,
        session_id=session.id,
        account_id=session.account_id,
        batch_id=session.source_batch_id,
        bank_import_row_id=row.id,
        transaction_id=transaction.id,
        allocated_amount=data.allocated_amount,
        status="active",
        matched_by=current_user.id,
    )
    db.add(match)
    try:
        db.flush()
        _refresh_session_counts(db, session)
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="reconciliation_match",
            entity_id=match.id,
            new_values={
                "session_id": session.id,
                "bank_import_row_id": row.id,
                "transaction_id": transaction.id,
                "allocated_amount": data.allocated_amount,
                "date_difference_days": abs(
                    (transaction.transaction_date.astimezone(TAIPEI).date()
                     - row.transaction_date.astimezone(TAIPEI).date()).days
                ),
            },
            description="人工配對銀行明細與家庭正式交易",
        )
        db.commit()
        db.refresh(match)
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="此交易或銀行明細已被其他配對占用，請重新整理") from exc

    date_difference_days = abs(
        (transaction.transaction_date.astimezone(TAIPEI).date()
         - row.transaction_date.astimezone(TAIPEI).date()).days
    )
    return {
        "success": True,
        "match": {
            "id": match.id,
            "session_id": match.session_id,
            "bank_import_row_id": match.bank_import_row_id,
            "transaction_id": match.transaction_id,
            "allocated_amount": str(match.allocated_amount),
            "status": match.status,
            "matched_by": match.matched_by,
            "matched_at": match.matched_at,
        },
        "bank_row": _row_state(row, allocated_before + data.allocated_amount),
        "date_difference_days": date_difference_days,
        "session": _session_summary(session),
    }


@router.post(
    "/sessions/{session_id}/matches/{match_id}/void",
    summary="解除銀行明細與正式交易的配對",
)
def void_reconciliation_match(
    session_id: int,
    match_id: int,
    data: ReconciliationMatchVoid,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.unmatch")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以解除配對")

    if account_scope == "own":
        owned_account = db.query(Account.id).filter(
            Account.id == session.account_id,
            Account.family_id == family_id,
            Account.created_by == current_user.id,
        ).first()
        if owned_account is None:
            raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")

    initial_match = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.id == match_id,
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.status == "active",
    ).first()
    if initial_match is None:
        raise HTTPException(status_code=404, detail="找不到有效的對帳配對")

    row = db.query(BankImportRow).filter(
        BankImportRow.id == initial_match.bank_import_row_id,
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到原始銀行明細")

    transaction_query = db.query(Transaction).filter(
        Transaction.id == initial_match.transaction_id,
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
    )
    if transaction_scope == "own":
        transaction_query = transaction_query.filter(Transaction.created_by == current_user.id)
    transaction = transaction_query.with_for_update().first()
    if transaction is None:
        raise HTTPException(status_code=404, detail="找不到可解除配對的正式交易")

    match = db.query(ReconciliationMatch).filter(
        ReconciliationMatch.id == match_id,
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.status == "active",
    ).with_for_update().first()
    if match is None:
        raise HTTPException(status_code=409, detail="此配對已被其他操作解除")

    old_values = {
        "status": match.status,
        "allocated_amount": match.allocated_amount,
        "bank_import_row_id": match.bank_import_row_id,
        "transaction_id": match.transaction_id,
    }
    match.status = "voided"
    match.voided_by = current_user.id
    match.voided_at = datetime.now(timezone.utc)
    match.void_reason = data.reason
    try:
        db.flush()
        _refresh_session_counts(db, session)
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="void",
            entity_type="reconciliation_match",
            entity_id=match.id,
            old_values=old_values,
            new_values={
                "status": match.status,
                "void_reason": match.void_reason,
                "voided_by": match.voided_by,
            },
            description="解除銀行明細與正式交易配對；保留原配對紀錄",
        )
        db.commit()
        db.refresh(match)
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="解除配對時發生資料衝突，請重新整理") from exc

    allocated_after = db.query(
        func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0)
    ).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.bank_import_row_id == row.id,
        ReconciliationMatch.status == "active",
    ).scalar() or Decimal("0")
    return {
        "success": True,
        "message": "配對已解除，原紀錄與原因已保留",
        "match": {
            "id": match.id,
            "status": match.status,
            "voided_by": match.voided_by,
            "voided_at": match.voided_at,
            "void_reason": match.void_reason,
        },
        "bank_row": _row_state(row, allocated_after),
        "session": _session_summary(session),
    }
