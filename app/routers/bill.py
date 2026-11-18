import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.bill import Bill
from app.models.bill_payment import BillPayment
from app.models.category import Category
from app.models.user import User
from app.schemas.bill import (
    BillCreate, BillUpdate, BillResponse, BillListResponse, BillMessageResponse,
)
from app.services.audit_log import add_audit_log
from app.services.bill import bill_to_dict
from app.services.bill_payment import get_bill_paid_amount, get_bill_paid_amounts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bills", tags=["Bills"])


def _authorize(db: Session, user_id: int, family_id: int, action: str):
    try:
        _, roles = require_permission(
            db=db, user_id=user_id, family_id=family_id,
            permission_code=f"bills.{action}",
        )
        scope = require_data_scope(
            db=db, roles=roles, family_id=family_id, resource="bills",
        )
        return scope
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _get_bill(db: Session, family_id: int, bill_id: int) -> Bill:
    bill = db.query(Bill).filter(
        Bill.id == bill_id, Bill.family_id == family_id,
    ).first()
    if bill is None:
        raise HTTPException(status_code=404, detail="找不到此家庭帳單")
    return bill


def _check_owner(bill: Bill, user: User, scope: str):
    if scope == "own" and bill.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此帳單")


def _check_category(db: Session, family_id: int, category_id: int | None):
    if category_id is None:
        return
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="找不到指定分類")
    if not category.is_active:
        raise HTTPException(status_code=400, detail="指定分類已停用")
    if category.category_type != "expense":
        raise HTTPException(status_code=422, detail="帳單只能使用支出分類")
    if category.family_id is not None and category.family_id != family_id:
        raise HTTPException(status_code=404, detail="找不到指定分類")


def _audit_values(bill: Bill) -> dict:
    return {
        "bill_number": bill.bill_number,
        "title": bill.title,
        "category_id": bill.category_id,
        "bill_date": bill.bill_date,
        "billing_period_start": bill.billing_period_start,
        "billing_period_end": bill.billing_period_end,
        "due_date": bill.due_date,
        "original_amount": bill.original_amount,
        "tax_amount": bill.tax_amount,
        "discount_amount": bill.discount_amount,
        "currency_code": bill.currency_code,
        "note": bill.note,
        "is_voided": bill.is_voided,
    }


@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
def create_bill(
    payload: BillCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "create")
    _check_category(db, family_id, payload.category_id)

    data = payload.model_dump()
    bill = Bill(
        family_id=family_id,
        **data,
        created_by=current_user.id,
    )
    try:
        db.add(bill)
        db.flush()
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="create", entity_type="bill", entity_id=bill.id,
            new_values=_audit_values(bill), description="新增帳單",
        )
        db.commit()
        db.refresh(bill)
        return bill_to_dict(bill)
    except IntegrityError:
        db.rollback()
        logger.exception("新增帳單時發生資料完整性錯誤")
        raise HTTPException(
            status_code=409,
            detail="帳單編號重複，或帳單資料違反資料庫限制",
        )


@router.get("", response_model=BillListResponse)
def list_bills(
    family_id: int = Query(..., gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    include_voided: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    query = db.query(Bill).filter(Bill.family_id == family_id)
    if scope == "own":
        query = query.filter(Bill.created_by == current_user.id)
    if not include_voided:
        query = query.filter(Bill.is_voided.is_(False))
    if start_date is not None:
        query = query.filter(Bill.bill_date >= start_date)
    if end_date is not None:
        query = query.filter(Bill.bill_date <= end_date)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="開始日期不可晚於結束日期")

    total = query.count()
    rows = query.order_by(Bill.bill_date.desc(), Bill.id.desc()).offset(skip).limit(limit).all()
    return {
        "success": True, "total": total, "skip": skip, "limit": limit,
        "bills": [bill_to_dict(item, paid_amounts.get(item.id, Decimal("0"))) for item in rows],
    }


@router.get("/{bill_id}", response_model=BillResponse)
def get_bill(
    bill_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    bill = _get_bill(db, family_id, bill_id)
    _check_owner(bill, current_user, scope)
    return bill_to_dict(bill)


@router.patch("/{bill_id}", response_model=BillResponse)
def update_bill(
    bill_id: int,
    payload: BillUpdate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "update")
    bill = _get_bill(db, family_id, bill_id)
    _check_owner(bill, current_user, scope)
    if bill.is_voided:
        raise HTTPException(status_code=409, detail="帳單已作廢，不可修改")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="沒有提供任何修改內容")

    new_category_id = changes.get("category_id", bill.category_id)
    _check_category(db, family_id, new_category_id)

    merged = {
        "billing_period_start": changes.get("billing_period_start", bill.billing_period_start),
        "billing_period_end": changes.get("billing_period_end", bill.billing_period_end),
        "original_amount": changes.get("original_amount", bill.original_amount),
        "tax_amount": changes.get("tax_amount", bill.tax_amount),
        "discount_amount": changes.get("discount_amount", bill.discount_amount),
    }
    if (merged["billing_period_start"] is None) != (merged["billing_period_end"] is None):
        raise HTTPException(status_code=422, detail="帳單期間起日與迄日必須同時提供")
    if merged["billing_period_start"] and merged["billing_period_start"] > merged["billing_period_end"]:
        raise HTTPException(status_code=422, detail="帳單期間起日不可晚於迄日")
    if merged["original_amount"] + merged["tax_amount"] - merged["discount_amount"] < 0:
        raise HTTPException(status_code=422, detail="折扣金額不可大於原始金額加稅額")

    old_values = {key: getattr(bill, key) for key in changes}
    try:
        for key, value in changes.items():
            setattr(bill, key, value)
        bill.updated_by = current_user.id
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="update", entity_type="bill", entity_id=bill.id,
            old_values=old_values,
            new_values={key: getattr(bill, key) for key in changes},
            description="修改帳單",
        )
        db.commit()
        db.refresh(bill)
        return bill_to_dict(bill)
    except IntegrityError:
        db.rollback()
        logger.exception("修改帳單時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="帳單編號重複或資料關聯不合法")


@router.delete("/{bill_id}", response_model=BillMessageResponse)
def void_bill(
    bill_id: int,
    family_id: int = Query(..., gt=0),
    reason: str | None = Query(default=None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "void")
    bill = _get_bill(db, family_id, bill_id)
    _check_owner(bill, current_user, scope)
    if bill.is_voided:
        raise HTTPException(status_code=409, detail="帳單已經作廢")

    old_values = _audit_values(bill)
    bill.is_voided = True
    bill.voided_at = datetime.now(timezone.utc)
    bill.voided_by = current_user.id
    bill.void_reason = reason.strip() if reason and reason.strip() else None
    try:
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="void", entity_type="bill", entity_id=bill.id,
            old_values=old_values, new_values=_audit_values(bill),
            description="作廢帳單",
        )
        db.commit()
        db.refresh(bill)
        return {"success": True, "message": "帳單已作廢", "bill": bill_to_dict(bill, get_bill_paid_amount(db, family_id, bill.id))}
    except IntegrityError:
        db.rollback()
        logger.exception("作廢帳單時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="帳單作廢失敗")
