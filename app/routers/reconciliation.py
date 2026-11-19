from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import re
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
from app.models.reconciliation import ReconciliationExclusion, ReconciliationMatch, ReconciliationSession
from app.models.reconciliation_issue import ReconciliationIssue
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.reconciliation import (
    ReconciliationMatchCreate,
    ReconciliationMatchVoid,
    ReconciliationSessionCreate,
    ReconciliationExcludeCreate,
    ReconciliationExclusionVoid,
    ReconciliationLifecycleReason,
    ReconciliationIssueCreate,
    ReconciliationIssueResolve,
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
        "excluded_row_count": session.excluded_row_count,
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
    values = db.query(
        ReconciliationMatch.bank_import_row_id,
        func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0),
    ).filter(
        ReconciliationMatch.family_id == session.family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.status == "active",
    ).group_by(ReconciliationMatch.bank_import_row_id).all()
    totals = {row_id: amount for row_id, amount in values}
    excluded_ids = {
        item[0] for item in db.query(ReconciliationExclusion.bank_import_row_id).filter(
            ReconciliationExclusion.family_id == session.family_id,
            ReconciliationExclusion.session_id == session.id,
            ReconciliationExclusion.status == "active",
        ).all()
    }
    matched = sum(
        1 for row in rows
        if row.id not in excluded_ids
        and totals.get(row.id, Decimal("0")) == (row.amount or Decimal("0"))
    )
    session.statement_row_count = len(rows)
    session.matched_row_count = matched
    session.excluded_row_count = len(excluded_ids)
    session.difference_row_count = len(rows) - matched - len(excluded_ids)


def _normalize_description(value: str | None) -> str:
    return re.sub(r"[^\w]", "", (value or "").casefold(), flags=re.UNICODE)


def _score_reconciliation_candidate(
    row: BankImportRow, transaction: Transaction, remaining: Decimal
) -> dict | None:
    tx_date = transaction.transaction_date
    row_date = row.transaction_date
    if tx_date.tzinfo is None:
        tx_date = tx_date.replace(tzinfo=timezone.utc)
    if row_date.tzinfo is None:
        row_date = row_date.replace(tzinfo=timezone.utc)
    date_difference_days = abs(
        (tx_date.astimezone(TAIPEI).date() - row_date.astimezone(TAIPEI).date()).days
    )
    if date_difference_days > 7 or transaction.amount > remaining:
        return None

    score = 0
    reasons = []
    if transaction.import_row_id == row.id:
        score += 200
        reasons.append("此交易由同一筆銀行明細直接建立")
    if row.external_reference and transaction.external_reference:
        if row.external_reference.strip().casefold() == transaction.external_reference.strip().casefold():
            score += 100
            reasons.append("銀行交易序號完全相同")
    if transaction.amount == remaining:
        score += 50
        reasons.append("交易金額等於銀行明細剩餘金額")
    else:
        score += 20
        reasons.append("交易金額可納入銀行明細剩餘金額")
    if date_difference_days == 0:
        score += 30
        reasons.append("交易日期相同")
    elif date_difference_days == 1:
        score += 20
        reasons.append("交易日期相差 1 天")
    elif date_difference_days <= 3:
        score += 10
        reasons.append("交易日期相差不超過 3 天")
    else:
        score += 5
        reasons.append("交易日期相差 4 至 7 天")

    row_description = _normalize_description(row.description)
    tx_description = _normalize_description(transaction.description)
    if row_description and tx_description:
        if row_description == tx_description:
            score += 20
            reasons.append("交易說明完全相同")
        elif row_description in tx_description or tx_description in row_description:
            score += 10
            reasons.append("交易說明部分相符")

    confidence = "high" if score >= 150 else ("medium" if score >= 90 else "low")
    return {
        "transaction_id": transaction.id,
        "transaction_date": transaction.transaction_date,
        "transaction_type": transaction.transaction_type,
        "amount": str(transaction.amount),
        "currency_code": transaction.currency_code,
        "description": transaction.description,
        "external_reference": transaction.external_reference,
        "allocated_amount": str(transaction.amount),
        "date_difference_days": date_difference_days,
        "score": score,
        "confidence": confidence,
        "reasons": reasons,
    }


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

    exclusions = {}
    if row_ids:
        exclusions = {
            item.bank_import_row_id: item
            for item in db.query(ReconciliationExclusion).filter(
                ReconciliationExclusion.family_id == family_id,
                ReconciliationExclusion.session_id == session.id,
                ReconciliationExclusion.bank_import_row_id.in_(row_ids),
                ReconciliationExclusion.status == "active",
            ).all()
        }

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
        exclusion = exclusions.get(row.id)
        if exclusion is not None:
            item["reconciliation_status"] = "excluded"
            item["exclusion"] = {
                "id": exclusion.id, "reason": exclusion.reason,
                "created_by": exclusion.created_by, "created_at": exclusion.created_at,
            }
        else:
            item["exclusion"] = None
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
    if db.query(ReconciliationExclusion.id).filter(
        ReconciliationExclusion.family_id == family_id,
        ReconciliationExclusion.session_id == session.id,
        ReconciliationExclusion.bank_import_row_id == row.id,
        ReconciliationExclusion.status == "active",
    ).first():
        raise HTTPException(status_code=409, detail="此銀行明細已排除，請先解除排除再配對")

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


@router.post(
    "/sessions/{session_id}/suggestions",
    summary="產生銀行明細與正式交易的候選配對建議",
)
def suggest_reconciliation_matches(
    session_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.match")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以產生配對建議")

    if account_scope == "own":
        owned_account = db.query(Account.id).filter(
            Account.id == session.account_id,
            Account.family_id == family_id,
            Account.created_by == current_user.id,
        ).first()
        if owned_account is None:
            raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    rows = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status.in_(["imported", "duplicate"]),
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    ).order_by(BankImportRow.row_number.asc()).limit(500).all()
    if not rows:
        return {"success": True, "suggestions": [], "candidate_scan_limit": 2000}

    excluded_ids = {
        item[0] for item in db.query(ReconciliationExclusion.bank_import_row_id).filter(
            ReconciliationExclusion.family_id == family_id,
            ReconciliationExclusion.session_id == session.id,
            ReconciliationExclusion.status == "active",
        ).all()
    }
    rows = [row for row in rows if row.id not in excluded_ids]
    row_ids = [row.id for row in rows]
    allocations = db.query(
        ReconciliationMatch.bank_import_row_id,
        func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0),
    ).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.status == "active",
    ).group_by(ReconciliationMatch.bank_import_row_id).all()
    allocated_by_row = {row_id: amount for row_id, amount in allocations}

    active_transaction_ids = {
        item[0] for item in db.query(ReconciliationMatch.transaction_id).filter(
            ReconciliationMatch.family_id == family_id,
            ReconciliationMatch.status == "active",
        ).all()
    }
    transaction_types = sorted({row.transaction_type for row in rows if row.transaction_type})
    search_start = start_utc - timedelta(days=7)
    search_end = end_utc + timedelta(days=7)
    transaction_query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.is_voided.is_(False),
        Transaction.currency_code == session.currency_code,
        Transaction.transaction_type.in_(transaction_types),
        Transaction.transaction_date >= search_start,
        Transaction.transaction_date < search_end,
    )
    if transaction_scope == "own":
        transaction_query = transaction_query.filter(Transaction.created_by == current_user.id)
    candidate_transactions = transaction_query.order_by(
        Transaction.transaction_date.desc(), Transaction.id.desc()
    ).limit(2000).all()

    suggestion_rows = []
    occurrences = {}
    for row in rows:
        allocated = allocated_by_row.get(row.id, Decimal("0"))
        remaining = (row.amount or Decimal("0")) - allocated
        candidates = []
        if remaining > 0:
            for transaction in candidate_transactions:
                if transaction.id in active_transaction_ids:
                    continue
                if transaction.import_row_id not in (None, row.id):
                    continue
                if transaction.transaction_type != row.transaction_type:
                    continue
                if transaction.currency_code != row.currency_code:
                    continue
                candidate = _score_reconciliation_candidate(row, transaction, remaining)
                if candidate is None:
                    continue
                candidates.append(candidate)
                occurrences.setdefault(transaction.id, set()).add(row.id)
        candidates.sort(
            key=lambda item: (
                -item["score"],
                item["date_difference_days"],
                -item["transaction_id"],
            )
        )
        suggestion_rows.append({
            "bank_import_row": _row_state(row, allocated),
            "remaining_amount": str(remaining),
            "candidates": candidates[:5],
        })

    for item in suggestion_rows:
        for candidate in item["candidates"]:
            competing_rows = sorted(occurrences.get(candidate["transaction_id"], set()))
            candidate["ambiguous_across_rows"] = len(competing_rows) > 1
            candidate["competing_bank_row_ids"] = competing_rows if len(competing_rows) > 1 else []

    return {
        "success": True,
        "session_id": session.id,
        "suggestions": suggestion_rows,
        "candidate_scan_limit": 2000,
        "automatic_matches_created": 0,
    }


@router.post(
    "/sessions/{session_id}/exclude",
    status_code=status.HTTP_201_CREATED,
    summary="排除一筆銀行明細並保留原因",
)
def exclude_reconciliation_row(
    session_id: int,
    data: ReconciliationExcludeCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.exclude")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以排除明細")
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
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
    allocated = db.query(func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0)).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.bank_import_row_id == row.id,
        ReconciliationMatch.status == "active",
    ).scalar() or Decimal("0")
    if allocated > 0:
        raise HTTPException(status_code=409, detail="已有配對的明細不可直接排除，請先解除配對")
    existing = db.query(ReconciliationExclusion.id).filter(
        ReconciliationExclusion.family_id == family_id,
        ReconciliationExclusion.session_id == session.id,
        ReconciliationExclusion.bank_import_row_id == row.id,
        ReconciliationExclusion.status == "active",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="此銀行明細已排除")
    exclusion = ReconciliationExclusion(
        family_id=family_id, session_id=session.id, account_id=session.account_id,
        batch_id=session.source_batch_id, bank_import_row_id=row.id,
        reason=data.reason, status="active", created_by=current_user.id,
    )
    db.add(exclusion)
    try:
        db.flush()
        _refresh_session_counts(db, session)
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="exclude", entity_type="reconciliation_exclusion", entity_id=exclusion.id,
            new_values={"session_id": session.id, "bank_import_row_id": row.id, "reason": data.reason},
            description="排除銀行對帳明細並保留原因",
        )
        db.commit()
        db.refresh(exclusion)
        db.refresh(session)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="此明細已被其他操作排除，請重新整理") from exc
    return {
        "success": True,
        "exclusion": {"id": exclusion.id, "bank_import_row_id": row.id,
                      "reason": exclusion.reason, "status": exclusion.status,
                      "created_by": exclusion.created_by, "created_at": exclusion.created_at},
        "session": _session_summary(session),
    }


@router.post(
    "/sessions/{session_id}/exclusions/{exclusion_id}/void",
    summary="解除銀行明細排除並保留歷史",
)
def void_reconciliation_exclusion(
    session_id: int,
    exclusion_id: int,
    data: ReconciliationExclusionVoid,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.exclude")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以解除排除")
    exclusion = db.query(ReconciliationExclusion).filter(
        ReconciliationExclusion.id == exclusion_id,
        ReconciliationExclusion.family_id == family_id,
        ReconciliationExclusion.session_id == session.id,
        ReconciliationExclusion.status == "active",
    ).with_for_update().first()
    if exclusion is None:
        raise HTTPException(status_code=404, detail="找不到有效的排除紀錄")
    old_values = {"status": exclusion.status, "reason": exclusion.reason}
    exclusion.status = "voided"
    exclusion.voided_by = current_user.id
    exclusion.voided_at = datetime.now(timezone.utc)
    exclusion.void_reason = data.reason
    db.flush()
    _refresh_session_counts(db, session)
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="void", entity_type="reconciliation_exclusion", entity_id=exclusion.id,
        old_values=old_values,
        new_values={"status": exclusion.status, "void_reason": exclusion.void_reason},
        description="解除銀行明細排除；保留排除及解除歷史",
    )
    db.commit()
    db.refresh(session)
    return {"success": True, "message": "已解除排除，可重新配對", "session": _session_summary(session)}


@router.post(
    "/sessions/{session_id}/complete",
    summary="檢查差異並完成對帳",
)
def complete_reconciliation_session(
    session_id: int,
    data: ReconciliationLifecycleReason,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.close")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    if transaction_scope != "family":
        raise HTTPException(status_code=403, detail="完成整個帳戶對帳需要家庭層級的交易資料範圍")
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以完成")
    _refresh_session_counts(db, session)
    if session.difference_row_count != 0:
        raise HTTPException(
            status_code=409,
            detail={"message": "仍有未核對或部分核對的銀行明細，不能完成對帳",
                    "statement_row_count": session.statement_row_count,
                    "matched_row_count": session.matched_row_count,
                    "excluded_row_count": session.excluded_row_count,
                    "difference_row_count": session.difference_row_count},
        )
    # Full two-way validation: bank rows, ledger-only transactions, unresolved issues,
    # and statement opening/closing balances must all be accounted for.
    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    explained_ledger_ids = db.query(ReconciliationIssue.transaction_id).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session.id,
        ReconciliationIssue.category.in_(["ledger_only", "explained"]),
        ReconciliationIssue.status == "resolved",
        ReconciliationIssue.transaction_id.isnot(None),
    )
    active_match_transaction_ids = db.query(ReconciliationMatch.transaction_id).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.status == "active",
    )
    ledger_only_count = db.query(Transaction.id).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
        ~Transaction.id.in_(active_match_transaction_ids),
        ~Transaction.id.in_(explained_ledger_ids),
    ).count()
    open_issue_count = db.query(ReconciliationIssue.id).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session.id,
        ReconciliationIssue.status == "open",
    ).count()

    account = db.query(Account).filter(
        Account.id == session.account_id, Account.family_id == family_id
    ).first()
    from app.services.reconciliation_balance import calculate_reconciliation_balance_check

    balance_query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
    )
    opening_ledger = balance_query.filter(
        Transaction.transaction_type == "opening_balance"
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    prior_values = balance_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date < start_utc,
    ).with_entities(
        Transaction.transaction_type, func.coalesce(func.sum(Transaction.amount), 0)
    ).group_by(Transaction.transaction_type).all()
    period_values = balance_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
    ).with_entities(
        Transaction.transaction_type, func.coalesce(func.sum(Transaction.amount), 0)
    ).group_by(Transaction.transaction_type).all()
    prior_totals = {kind: Decimal(str(amount or 0)) for kind, amount in prior_values}
    period_totals = {kind: Decimal(str(amount or 0)) for kind, amount in period_values}
    balance_result = calculate_reconciliation_balance_check(
        account_type=account.account_type,
        opening_balance=Decimal(str(opening_ledger or 0)),
        prior_income=prior_totals.get("income", Decimal("0")),
        prior_expense=prior_totals.get("expense", Decimal("0")),
        period_income=period_totals.get("income", Decimal("0")),
        period_expense=period_totals.get("expense", Decimal("0")),
        statement_opening_balance=session.opening_balance,
        statement_closing_balance=session.closing_balance,
    )
    from app.services.reconciliation_completion import evaluate_reconciliation_completion

    completion = evaluate_reconciliation_completion(
        unresolved_bank_rows=session.difference_row_count,
        unmatched_ledger_transactions=ledger_only_count,
        open_issues=open_issue_count,
        opening_balance_matches=balance_result["opening_matches"],
        closing_balance_matches=balance_result["closing_matches"],
    )
    if not completion["ready_to_complete"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "雙向對帳仍有未處理項目，不能完成對帳",
                **completion["completion_blockers"],
                "opening_difference": (
                    str(balance_result["opening_difference"])
                    if balance_result["opening_difference"] is not None else None
                ),
                "closing_difference": (
                    str(balance_result["closing_difference"])
                    if balance_result["closing_difference"] is not None else None
                ),
            },
        )

    old_values = {"status": session.status}
    session.status = "completed"
    session.completed_by = current_user.id
    session.completed_at = datetime.now(timezone.utc)
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="complete", entity_type="reconciliation_session", entity_id=session.id,
        old_values=old_values,
        new_values={"status": session.status, "reason": data.reason,
                    "matched_row_count": session.matched_row_count,
                    "excluded_row_count": session.excluded_row_count},
        description="完成銀行／信用卡對帳工作階段",
    )
    db.commit()
    db.refresh(session)
    return {"success": True, "message": "對帳已完成", "session": _session_summary(session)}


@router.post(
    "/sessions/{session_id}/reopen",
    summary="重新開啟已完成的對帳",
)
def reopen_reconciliation_session(
    session_id: int,
    data: ReconciliationLifecycleReason,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.reopen")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="只有已完成的對帳工作階段可以重新開啟")
    old_values = {"status": session.status, "completed_by": session.completed_by,
                  "completed_at": session.completed_at}
    session.status = "in_progress"
    session.completed_by = None
    session.completed_at = None
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="reopen", entity_type="reconciliation_session", entity_id=session.id,
        old_values=old_values,
        new_values={"status": session.status, "reason": data.reason},
        description="重新開啟已完成的銀行／信用卡對帳",
    )
    db.commit()
    db.refresh(session)
    return {"success": True, "message": "對帳已重新開啟", "session": _session_summary(session)}


@router.get(
    "/sessions/{session_id}/ledger-only",
    summary="查詢對帳期間尚未配對的帳務交易",
)
def list_ledger_only_transactions(
    session_id: int,
    family_id: int = Query(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出此帳戶及期間內尚未出現在任何有效對帳配對的正式交易。

    此查詢不建立配對、不修改交易，也不將未配對直接判定為錯帳；
    交易可能因入帳時間差、未兌現或銀行批次尚未匯入而暫時未配對。
    """
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user)

    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id,
        Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    active_match_transaction_ids = db.query(
        ReconciliationMatch.transaction_id
    ).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.status == "active",
    )

    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
        ~Transaction.id.in_(active_match_transaction_ids),
    )
    if transaction_scope == "own":
        query = query.filter(Transaction.created_by == current_user.id)

    total = query.count()
    transactions = query.order_by(
        Transaction.transaction_date.asc(),
        Transaction.id.asc(),
    ).offset(skip).limit(limit).all()

    return {
        "success": True,
        "session_id": session.id,
        "account_id": session.account_id,
        "period_start": session.period_start,
        "period_end": session.period_end,
        "currency_code": session.currency_code,
        "total": total,
        "transactions": [
            {
                "id": item.id,
                "transaction_date": item.transaction_date,
                "transaction_type": item.transaction_type,
                "amount": str(item.amount),
                "currency_code": item.currency_code,
                "description": item.description,
                "external_reference": item.external_reference,
                "created_by": item.created_by,
                "import_row_id": item.import_row_id,
                "status": "ledger_only",
            }
            for item in transactions
        ],
        "pagination": {"skip": skip, "limit": limit},
        "notice": "未配對不代表錯帳；請確認是否為入帳時間差、未兌現或尚未匯入的銀行明細。",
    }


@router.get(
    "/sessions/{session_id}/balance-check",
    summary="核對對帳期間期初與期末餘額",
)
def get_reconciliation_balance_check(
    session_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compare statement balances with ledger balances without changing financial records."""
    from app.services.reconciliation_balance import calculate_reconciliation_balance_check

    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user)

    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id,
        Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    if transaction_scope != "family":
        raise HTTPException(
            status_code=403,
            detail="期初／期末餘額核對需要家庭層級的交易資料範圍，避免以個人資料誤判整個帳戶差異",
        )

    account = db.query(Account).filter(
        Account.id == session.account_id,
        Account.family_id == family_id,
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="找不到此家庭帳戶")

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)

    def totals_for(query):
        values = query.with_entities(
            Transaction.transaction_type,
            func.coalesce(func.sum(Transaction.amount), 0),
        ).group_by(Transaction.transaction_type).all()
        return {kind: Decimal(str(amount or 0)) for kind, amount in values}

    base_query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
    )
    opening_balance = (
        base_query.filter(Transaction.transaction_type == "opening_balance")
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )
    prior_totals = totals_for(base_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date < start_utc,
    ))
    period_totals = totals_for(base_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
    ))

    result = calculate_reconciliation_balance_check(
        account_type=account.account_type,
        opening_balance=Decimal(str(opening_balance or 0)),
        prior_income=prior_totals.get("income", Decimal("0")),
        prior_expense=prior_totals.get("expense", Decimal("0")),
        period_income=period_totals.get("income", Decimal("0")),
        period_expense=period_totals.get("expense", Decimal("0")),
        statement_opening_balance=session.opening_balance,
        statement_closing_balance=session.closing_balance,
    )

    return {
        "success": True,
        "session_id": session.id,
        "account_id": account.id,
        "account_name": account.name,
        "account_type": account.account_type,
        "currency_code": session.currency_code,
        "period_start": session.period_start,
        "period_end": session.period_end,
        "balance_convention": (
            "positive_is_debt" if account.account_type == "credit_card"
            else "positive_is_asset"
        ),
        "calculation_scope": "family",
        "result": {key: str(value) if isinstance(value, Decimal) else value
                   for key, value in result.items()},
        "notice": (
            "此結果為唯讀比較；差異不會自動修改交易。"
            "信用卡餘額以正數代表欠款，資產帳戶以正數代表資產。"
            "未提供對帳單期初或期末餘額時，該項差異會回傳 null。"
        ),
    }


def _issue_summary(item: ReconciliationIssue) -> dict:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "account_id": item.account_id,
        "bank_import_row_id": item.bank_import_row_id,
        "transaction_id": item.transaction_id,
        "category": item.category,
        "status": item.status,
        "reason": item.reason,
        "resolution_note": item.resolution_note,
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "resolved_at": item.resolved_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("/sessions/{session_id}/issues", summary="查詢對帳差異及處理歷史")
def list_reconciliation_issues(
    session_id: int,
    family_id: int = Query(..., gt=0),
    issue_status: str | None = Query(None, alias="status", pattern="^(open|resolved)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    session = _get_session(db, family_id, session_id, scope, current_user)
    account_scope = _require_scope(db, roles, family_id, "accounts")
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    query = db.query(ReconciliationIssue).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session_id,
    )
    if issue_status:
        query = query.filter(ReconciliationIssue.status == issue_status)
    total = query.count()
    items = query.order_by(ReconciliationIssue.created_at.desc(), ReconciliationIssue.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "issues": [_issue_summary(item) for item in items],
            "pagination": {"skip": skip, "limit": limit}}


@router.post(
    "/sessions/{session_id}/issues",
    status_code=status.HTTP_201_CREATED,
    summary="建立人工分類的對帳差異",
)
def create_reconciliation_issue(
    data: ReconciliationIssueCreate,
    session_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.create")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以新增差異")
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id, Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    bank_row = None
    transaction = None
    if data.bank_import_row_id is not None:
        bank_row = db.query(BankImportRow).filter(
            BankImportRow.id == data.bank_import_row_id,
            BankImportRow.family_id == family_id,
            BankImportRow.batch_id == session.source_batch_id,
            BankImportRow.transaction_date >= start_utc,
            BankImportRow.transaction_date < end_utc,
            BankImportRow.currency_code == session.currency_code,
        ).first()
        if bank_row is None:
            raise HTTPException(status_code=404, detail="銀行明細不屬於此對帳工作階段")
    if data.transaction_id is not None:
        transaction_scope = _require_scope(db, roles, family_id, "transactions")
        if transaction_scope != "family":
            raise HTTPException(status_code=403, detail="建立帳務差異需要家庭層級交易資料範圍")
        transaction = db.query(Transaction).filter(
            Transaction.id == data.transaction_id,
            Transaction.family_id == family_id,
            Transaction.account_id == session.account_id,
            Transaction.currency_code == session.currency_code,
            Transaction.is_voided.is_(False),
            Transaction.transaction_type.in_(["income", "expense"]),
            Transaction.transaction_date >= start_utc,
            Transaction.transaction_date < end_utc,
        ).first()
        if transaction is None:
            raise HTTPException(status_code=404, detail="正式交易不屬於此對帳帳戶及期間")
    if data.category == "amount_mismatch" and (bank_row is None or transaction is None):
        raise HTTPException(status_code=422, detail="金額差異必須同時關聯銀行明細與正式交易")
    if data.category == "date_mismatch" and (bank_row is None or transaction is None):
        raise HTTPException(status_code=422, detail="日期差異必須同時關聯銀行明細與正式交易")

    item = ReconciliationIssue(
        family_id=family_id, session_id=session.id, account_id=session.account_id,
        batch_id=session.source_batch_id, bank_import_row_id=data.bank_import_row_id,
        transaction_id=data.transaction_id, category=data.category, status="open",
        reason=data.reason, created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(item)
    db.flush()
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id, action="create",
        entity_type="reconciliation_issue", entity_id=item.id,
        new_values={"category": item.category, "status": item.status,
                    "bank_import_row_id": item.bank_import_row_id,
                    "transaction_id": item.transaction_id, "reason": item.reason},
        description="建立對帳差異分類",
    )
    db.commit()
    db.refresh(item)
    return {"success": True, "issue": _issue_summary(item)}


@router.post(
    "/sessions/{session_id}/issues/{issue_id}/resolve",
    summary="結案對帳差異並保留處理說明",
)
def resolve_reconciliation_issue(
    data: ReconciliationIssueResolve,
    session_id: int,
    issue_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.update")
    session = _get_session(db, family_id, session_id, scope, current_user, lock=True)
    if session.status != "in_progress":
        raise HTTPException(status_code=409, detail="只有進行中的對帳工作階段可以處理差異")
    item = db.query(ReconciliationIssue).filter(
        ReconciliationIssue.id == issue_id,
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session_id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此對帳差異")
    if item.status == "resolved":
        raise HTTPException(status_code=409, detail="此差異已結案")
    old_values = {"status": item.status, "resolution_note": item.resolution_note}
    item.status = "resolved"
    item.resolution_note = data.resolution_note
    item.updated_by = current_user.id
    item.resolved_at = datetime.now(timezone.utc)
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id, action="resolve",
        entity_type="reconciliation_issue", entity_id=item.id,
        old_values=old_values,
        new_values={"status": item.status, "resolution_note": item.resolution_note,
                    "resolved_at": item.resolved_at.isoformat()},
        description="結案對帳差異並記錄處理說明",
    )
    db.commit()
    db.refresh(item)
    return {"success": True, "issue": _issue_summary(item)}


@router.get(
    "/sessions/{session_id}/final-report",
    summary="取得雙向對帳驗收報告",
)
def get_reconciliation_final_report(
    session_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read-only final report for bank rows, ledger-only entries, issues and balances."""
    scope, roles = _authorize(db, current_user, family_id, "reconciliation.view")
    account_scope = _require_scope(db, roles, family_id, "accounts")
    transaction_scope = _require_scope(db, roles, family_id, "transactions")
    session = _get_session(db, family_id, session_id, scope, current_user)
    if account_scope == "own" and not db.query(Account.id).filter(
        Account.id == session.account_id,
        Account.family_id == family_id,
        Account.created_by == current_user.id,
    ).first():
        raise HTTPException(status_code=404, detail="找不到此家庭對帳工作階段")
    if transaction_scope != "family":
        raise HTTPException(
            status_code=403,
            detail="完整驗收報告需要家庭層級交易資料範圍",
        )

    start_utc, end_utc = _period_bounds(session.period_start, session.period_end)
    bank_rows = db.query(BankImportRow).filter(
        BankImportRow.family_id == family_id,
        BankImportRow.batch_id == session.source_batch_id,
        BankImportRow.status.in_(["imported", "duplicate"]),
        BankImportRow.transaction_date >= start_utc,
        BankImportRow.transaction_date < end_utc,
    ).all()
    bank_allocations = db.query(
        ReconciliationMatch.bank_import_row_id,
        func.coalesce(func.sum(ReconciliationMatch.allocated_amount), 0),
    ).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.session_id == session.id,
        ReconciliationMatch.status == "active",
    ).group_by(ReconciliationMatch.bank_import_row_id).all()
    allocation_totals = {row_id: Decimal(str(amount or 0)) for row_id, amount in bank_allocations}
    excluded_bank_ids = {
        row_id for (row_id,) in db.query(ReconciliationExclusion.bank_import_row_id).filter(
            ReconciliationExclusion.family_id == family_id,
            ReconciliationExclusion.session_id == session.id,
            ReconciliationExclusion.status == "active",
        ).all()
    }
    matched_bank_count = sum(
        1 for row in bank_rows
        if row.id not in excluded_bank_ids
        and allocation_totals.get(row.id, Decimal("0")) == (row.amount or Decimal("0"))
    )
    excluded_bank_count = len(excluded_bank_ids)
    unresolved_bank_count = len(bank_rows) - matched_bank_count - excluded_bank_count
    report_session = _session_summary(session)
    report_session.update({
        "statement_row_count": len(bank_rows),
        "matched_row_count": matched_bank_count,
        "excluded_row_count": excluded_bank_count,
        "difference_row_count": unresolved_bank_count,
    })
    active_match_transaction_ids = db.query(ReconciliationMatch.transaction_id).filter(
        ReconciliationMatch.family_id == family_id,
        ReconciliationMatch.status == "active",
    )
    explained_ledger_ids = db.query(ReconciliationIssue.transaction_id).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session.id,
        ReconciliationIssue.category.in_(["ledger_only", "explained"]),
        ReconciliationIssue.status == "resolved",
        ReconciliationIssue.transaction_id.isnot(None),
    )
    ledger_only_query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
        ~Transaction.id.in_(active_match_transaction_ids),
        ~Transaction.id.in_(explained_ledger_ids),
    )
    ledger_only_count = ledger_only_query.count()
    open_issues = db.query(ReconciliationIssue).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session.id,
        ReconciliationIssue.status == "open",
    ).order_by(ReconciliationIssue.created_at.asc(), ReconciliationIssue.id.asc()).all()
    resolved_issue_count = db.query(ReconciliationIssue.id).filter(
        ReconciliationIssue.family_id == family_id,
        ReconciliationIssue.session_id == session.id,
        ReconciliationIssue.status == "resolved",
    ).count()
    issue_counts = {
        category: db.query(ReconciliationIssue.id).filter(
            ReconciliationIssue.family_id == family_id,
            ReconciliationIssue.session_id == session.id,
            ReconciliationIssue.category == category,
        ).count()
        for category in (
            "bank_only", "ledger_only", "amount_mismatch",
            "date_mismatch", "pending", "explained",
        )
    }

    account = db.query(Account).filter(
        Account.id == session.account_id, Account.family_id == family_id
    ).first()
    from app.services.reconciliation_balance import calculate_reconciliation_balance_check

    base_query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == session.account_id,
        Transaction.currency_code == session.currency_code,
        Transaction.is_voided.is_(False),
    )
    opening_ledger = base_query.filter(
        Transaction.transaction_type == "opening_balance"
    ).with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    def grouped_totals(query):
        return {
            kind: Decimal(str(amount or 0))
            for kind, amount in query.with_entities(
                Transaction.transaction_type,
                func.coalesce(func.sum(Transaction.amount), 0),
            ).group_by(Transaction.transaction_type).all()
        }
    prior = grouped_totals(base_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date < start_utc,
    ))
    period = grouped_totals(base_query.filter(
        Transaction.transaction_type.in_(["income", "expense"]),
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date < end_utc,
    ))
    balance = calculate_reconciliation_balance_check(
        account_type=account.account_type,
        opening_balance=Decimal(str(opening_ledger or 0)),
        prior_income=prior.get("income", Decimal("0")),
        prior_expense=prior.get("expense", Decimal("0")),
        period_income=period.get("income", Decimal("0")),
        period_expense=period.get("expense", Decimal("0")),
        statement_opening_balance=session.opening_balance,
        statement_closing_balance=session.closing_balance,
    )
    balance_mismatch = (
        balance["opening_matches"] is False or balance["closing_matches"] is False
    )
    from app.services.reconciliation_completion import evaluate_reconciliation_completion

    completion = evaluate_reconciliation_completion(
        unresolved_bank_rows=unresolved_bank_count,
        unmatched_ledger_transactions=ledger_only_count,
        open_issues=len(open_issues),
        opening_balance_matches=balance["opening_matches"],
        closing_balance_matches=balance["closing_matches"],
    )
    return {
        "success": True,
        "session": report_session,
        "bank_side": {
            "statement_rows": len(bank_rows),
            "matched_rows": matched_bank_count,
            "excluded_rows": excluded_bank_count,
            "unresolved_rows": unresolved_bank_count,
        },
        "ledger_side": {
            "unmatched_transactions": ledger_only_count,
            "notice": "未配對帳務交易可能是入帳時間差；需人工說明並結案，不會自動補帳",
        },
        "issues": {
            "open_count": len(open_issues),
            "resolved_count": resolved_issue_count,
            "category_counts": issue_counts,
            "open_items": [_issue_summary(item) for item in open_issues],
        },
        "balance_check": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in balance.items()
        },
        "ready_to_complete": completion["ready_to_complete"],
        "completion_blockers": completion["completion_blockers"],
        "read_only": True,
    }
