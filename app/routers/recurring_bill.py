import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.category import Category
from app.models.recurring_bill import RecurringBill
from app.models.user import User
from app.schemas.recurring_bill import (
    RecurringBillCreate, RecurringBillUpdate, RecurringBillResponse,
    RecurringBillListResponse, GenerateResponse,
)
from app.services.audit_log import add_audit_log
from app.services.recurring_bill import generate_due_bills

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recurring-bills", tags=["Recurring Bills"])


def _scope(db: Session, user_id: int, family_id: int, action: str):
    try:
        _, roles = require_permission(db=db, user_id=user_id, family_id=family_id, permission_code=f"recurring_bills.{action}")
        return require_data_scope(db=db, roles=roles, family_id=family_id, resource="recurring_bills")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _get_rule(db: Session, family_id: int, rule_id: int) -> RecurringBill:
    rule = db.query(RecurringBill).filter(RecurringBill.id == rule_id, RecurringBill.family_id == family_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="找不到此家庭定期帳單")
    return rule


def _check_owner(rule: RecurringBill, user: User, scope: str):
    if scope == "own" and rule.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此定期帳單")


def _check_category(db: Session, family_id: int, category_id: int | None):
    if category_id is None:
        return
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category or (category.family_id is not None and category.family_id != family_id):
        raise HTTPException(status_code=404, detail="找不到指定分類")
    if not category.is_active or category.category_type != "expense":
        raise HTTPException(status_code=422, detail="定期帳單只能使用有效的支出分類")


def _audit(rule: RecurringBill):
    return {k: getattr(rule, k) for k in (
        "title", "category_id", "frequency", "interval_count", "start_date",
        "end_date", "next_run_date", "due_days_after", "original_amount",
        "tax_amount", "discount_amount", "currency_code", "note", "is_active",
    )}


@router.post("", response_model=RecurringBillResponse, status_code=status.HTTP_201_CREATED)
def create_recurring_bill(payload: RecurringBillCreate, family_id: int = Query(..., gt=0),
                          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _scope(db, current_user.id, family_id, "create")
    _check_category(db, family_id, payload.category_id)
    data = payload.model_dump()
    data["next_run_date"] = data["next_run_date"] or data["start_date"]
    rule = RecurringBill(family_id=family_id, created_by=current_user.id, **data)
    db.add(rule)
    try:
        db.flush()
        add_audit_log(db, family_id=family_id, actor_user_id=current_user.id, action="create",
                      entity_type="recurring_bill", entity_id=rule.id, new_values=_audit(rule), description="新增定期帳單")
        db.commit()
        db.refresh(rule)
        return rule
    except IntegrityError:
        db.rollback()
        logger.exception("新增定期帳單失敗")
        raise HTTPException(status_code=409, detail="定期帳單資料不符合資料庫限制")


@router.get("", response_model=RecurringBillListResponse)
def list_recurring_bills(family_id: int = Query(..., gt=0), include_inactive: bool = False,
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _scope(db, current_user.id, family_id, "view")
    query = db.query(RecurringBill).filter(RecurringBill.family_id == family_id)
    if scope == "own":
        query = query.filter(RecurringBill.created_by == current_user.id)
    if not include_inactive:
        query = query.filter(RecurringBill.is_active.is_(True))
    rows = query.order_by(RecurringBill.id.desc()).all()
    return {"success": True, "total": len(rows), "recurring_bills": rows}


@router.get("/{rule_id}", response_model=RecurringBillResponse)
def get_recurring_bill(rule_id: int, family_id: int = Query(..., gt=0),
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _scope(db, current_user.id, family_id, "view")
    rule = _get_rule(db, family_id, rule_id)
    _check_owner(rule, current_user, scope)
    return rule


@router.patch("/{rule_id}", response_model=RecurringBillResponse)
def update_recurring_bill(rule_id: int, payload: RecurringBillUpdate, family_id: int = Query(..., gt=0),
                          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _scope(db, current_user.id, family_id, "update")
    rule = _get_rule(db, family_id, rule_id)
    _check_owner(rule, current_user, scope)
    if not rule.is_active:
        raise HTTPException(status_code=409, detail="定期帳單已停用")
    changes = payload.model_dump(exclude_unset=True)
    _check_category(db, family_id, changes.get("category_id", rule.category_id))
    old = _audit(rule)
    for key, value in changes.items():
        setattr(rule, key, value)
    if rule.end_date and rule.end_date < rule.start_date:
        raise HTTPException(status_code=422, detail="結束日期不可早於開始日期")
    if rule.next_run_date < rule.start_date:
        raise HTTPException(status_code=422, detail="下次產生日期不可早於開始日期")
    if rule.original_amount + rule.tax_amount - rule.discount_amount < 0:
        raise HTTPException(status_code=422, detail="折扣金額不可大於原始金額加稅額")
    rule.updated_by = current_user.id
    try:
        add_audit_log(db, family_id=family_id, actor_user_id=current_user.id, action="update",
                      entity_type="recurring_bill", entity_id=rule.id, old_values=old,
                      new_values=_audit(rule), description="修改定期帳單")
        db.commit()
        db.refresh(rule)
        return rule
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="定期帳單更新失敗")


@router.post("/{rule_id}/generate", response_model=GenerateResponse)
def generate_recurring_bills(rule_id: int, through_date: date = Query(...), family_id: int = Query(..., gt=0),
                             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _scope(db, current_user.id, family_id, "create")
    rule = db.query(RecurringBill).filter(RecurringBill.id == rule_id, RecurringBill.family_id == family_id).with_for_update().first()
    if not rule:
        raise HTTPException(status_code=404, detail="找不到此家庭定期帳單")
    _check_owner(rule, current_user, scope)
    if through_date < rule.next_run_date:
        return {"success": True, "generated_count": 0, "bill_ids": [], "next_run_date": rule.next_run_date}
    old_next = rule.next_run_date
    try:
        ids = generate_due_bills(db, rule, through_date, current_user.id)
        add_audit_log(db, family_id=family_id, actor_user_id=current_user.id, action="generate",
                      entity_type="recurring_bill", entity_id=rule.id,
                      old_values={"next_run_date": old_next}, new_values={"next_run_date": rule.next_run_date, "generated_bill_ids": ids},
                      description="依定期規則產生帳單")
        db.commit()
        return {"success": True, "generated_count": len(ids), "bill_ids": ids,
                "next_run_date": rule.next_run_date if rule.is_active else None}
    except IntegrityError:
        db.rollback()
        logger.exception("定期帳單產生衝突")
        raise HTTPException(status_code=409, detail="此期帳單已存在或產生資料衝突")


@router.delete("/{rule_id}")
def deactivate_recurring_bill(rule_id: int, family_id: int = Query(..., gt=0),
                               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _scope(db, current_user.id, family_id, "void")
    rule = _get_rule(db, family_id, rule_id)
    _check_owner(rule, current_user, scope)
    if not rule.is_active:
        raise HTTPException(status_code=409, detail="定期帳單已停用")
    old = _audit(rule)
    rule.is_active = False
    rule.updated_by = current_user.id
    add_audit_log(db, family_id=family_id, actor_user_id=current_user.id, action="void",
                  entity_type="recurring_bill", entity_id=rule.id, old_values=old,
                  new_values=_audit(rule), description="停用定期帳單")
    db.commit()
    return {"success": True, "message": "定期帳單已停用"}
