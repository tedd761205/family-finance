import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission, require_data_scope
from app.models.account import Account
from app.models.bill import Bill
from app.models.bill_payment import BillPayment
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.bill_payment import (
    BillPaymentCreate, BillRefundCreate, BillPaymentResponse,
    BillPaymentListResponse, BillPaymentMessageResponse,
)
from app.services.audit_log import add_audit_log
from app.services.bill_payment import (
    get_bill_paid_amount, get_payment_refunded_amount,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bill-payments", tags=["Bill Payments"])


def _authorize(db: Session, user_id: int, family_id: int, action: str):
    try:
        _, roles = require_permission(
            db=db, user_id=user_id, family_id=family_id,
            permission_code=f"payments.{action}",
        )
        scope = require_data_scope(
            db=db, roles=roles, family_id=family_id, resource="payments",
        )
        return scope
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _get_bill(db: Session, family_id: int, bill_id: int, lock: bool = False):
    query = db.query(Bill).filter(Bill.family_id == family_id, Bill.id == bill_id)
    if lock:
        query = query.with_for_update()
    bill = query.first()
    if bill is None:
        raise HTTPException(status_code=404, detail="找不到此家庭帳單")
    return bill


def _get_payment(db: Session, family_id: int, payment_id: int, lock: bool = False):
    query = db.query(BillPayment).filter(
        BillPayment.family_id == family_id, BillPayment.id == payment_id,
    )
    if lock:
        query = query.with_for_update()
    payment = query.first()
    if payment is None:
        raise HTTPException(status_code=404, detail="找不到此家庭付款紀錄")
    return payment


def _check_owner(payment: BillPayment, user: User, scope: str):
    if scope == "own" and payment.created_by != user.id:
        raise HTTPException(status_code=404, detail="找不到此付款紀錄")


def _validate_account(db: Session, family_id: int, account_id: int, currency_code: str):
    account = db.query(Account).filter(
        Account.family_id == family_id, Account.id == account_id,
    ).first()
    if account is None:
        raise HTTPException(status_code=404, detail="找不到此家庭帳戶")
    if not account.is_active:
        raise HTTPException(status_code=409, detail="付款帳戶已停用")
    if account.currency_code != currency_code:
        raise HTTPException(status_code=422, detail="付款幣別必須與帳戶幣別一致")
    return account


def _audit_values(payment: BillPayment):
    return {
        "bill_id": payment.bill_id,
        "account_id": payment.account_id,
        "payment_type": payment.payment_type,
        "original_payment_id": payment.original_payment_id,
        "amount": payment.amount,
        "currency_code": payment.currency_code,
        "payment_date": payment.payment_date,
        "is_voided": payment.is_voided,
    }


def _create_linked_transaction(db: Session, payment: BillPayment, bill: Bill):
    transaction = Transaction(
        family_id=payment.family_id,
        account_id=payment.account_id,
        transaction_type="expense" if payment.payment_type == "payment" else "income",
        amount=payment.amount,
        currency_code=payment.currency_code,
        transaction_date=payment.payment_date,
        description=payment.description or (
            f"帳單付款：{bill.title}" if payment.payment_type == "payment"
            else f"帳單退款：{bill.title}"
        ),
        category_id=bill.category_id if payment.payment_type == "payment" else None,
        bill_payment_id=payment.id,
        created_by=payment.created_by,
        note=payment.note,
    )
    db.add(transaction)
    db.flush()
    return transaction


@router.post("", response_model=BillPaymentResponse, status_code=status.HTTP_201_CREATED)
def create_bill_payment(
    payload: BillPaymentCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "create")
    try:
        bill = _get_bill(db, family_id, payload.bill_id, lock=True)
        if bill.is_voided:
            raise HTTPException(status_code=409, detail="帳單已作廢，不可付款")
        if payload.currency_code != bill.currency_code:
            raise HTTPException(status_code=422, detail="付款幣別必須與帳單幣別一致")
        _validate_account(db, family_id, payload.account_id, payload.currency_code)

        total = bill.original_amount + bill.tax_amount - bill.discount_amount
        paid = get_bill_paid_amount(db, family_id, bill.id)
        remaining = total - paid
        if payload.amount > remaining:
            raise HTTPException(
                status_code=409,
                detail=f"付款金額超過帳單未付餘額（剩餘 {remaining}）",
            )

        payment = BillPayment(
            family_id=family_id, bill_id=bill.id, account_id=payload.account_id,
            payment_type="payment", amount=payload.amount,
            currency_code=payload.currency_code, payment_date=payload.payment_date,
            description=payload.description, note=payload.note,
            created_by=current_user.id,
        )
        db.add(payment)
        db.flush()
        transaction = _create_linked_transaction(db, payment, bill)
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="create", entity_type="bill_payment", entity_id=payment.id,
            new_values={**_audit_values(payment), "transaction_id": transaction.id},
            description="新增帳單付款及對應帳戶交易",
        )
        db.commit()
        db.refresh(payment)
        return payment
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        logger.exception("新增帳單付款時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="付款資料關聯不合法或違反資料庫限制")
    except Exception:
        db.rollback()
        raise


@router.post("/{payment_id}/refund", response_model=BillPaymentResponse, status_code=status.HTTP_201_CREATED)
def refund_bill_payment(
    payment_id: int,
    payload: BillRefundCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "create")
    try:
        original = _get_payment(db, family_id, payment_id)
        bill = _get_bill(db, family_id, original.bill_id, lock=True)
        original = _get_payment(db, family_id, payment_id, lock=True)
        if original.payment_type != "payment":
            raise HTTPException(status_code=409, detail="只能針對原始付款建立退款")
        if original.is_voided:
            raise HTTPException(status_code=409, detail="原始付款已作廢，不可退款")
        if bill.is_voided:
            raise HTTPException(status_code=409, detail="帳單已作廢，不可退款")
        if payload.currency_code != original.currency_code or payload.currency_code != bill.currency_code:
            raise HTTPException(status_code=422, detail="退款幣別必須與原始付款及帳單一致")
        _validate_account(db, family_id, payload.account_id, payload.currency_code)

        refunded = get_payment_refunded_amount(db, family_id, original.id)
        refundable = original.amount - refunded
        if payload.amount > refundable:
            raise HTTPException(
                status_code=409,
                detail=f"退款金額超過可退餘額（剩餘 {refundable}）",
            )

        refund = BillPayment(
            family_id=family_id, bill_id=bill.id, account_id=payload.account_id,
            payment_type="refund", original_payment_id=original.id,
            amount=payload.amount, currency_code=payload.currency_code,
            payment_date=payload.payment_date, description=payload.description,
            note=payload.note, created_by=current_user.id,
        )
        db.add(refund)
        db.flush()
        transaction = _create_linked_transaction(db, refund, bill)
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="create", entity_type="bill_payment", entity_id=refund.id,
            new_values={**_audit_values(refund), "transaction_id": transaction.id},
            description="新增帳單退款及對應帳戶收入交易",
        )
        db.commit()
        db.refresh(refund)
        return refund
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        logger.exception("新增帳單退款時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="退款資料關聯不合法或違反資料庫限制")
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=BillPaymentListResponse)
def list_bill_payments(
    family_id: int = Query(..., gt=0),
    bill_id: int | None = Query(default=None, gt=0),
    include_voided: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    query = db.query(BillPayment).filter(BillPayment.family_id == family_id)
    if scope == "own":
        query = query.filter(BillPayment.created_by == current_user.id)
    if bill_id is not None:
        query = query.filter(BillPayment.bill_id == bill_id)
    if not include_voided:
        query = query.filter(BillPayment.is_voided.is_(False))
    total = query.count()
    payments = query.order_by(BillPayment.payment_date.desc(), BillPayment.id.desc()).offset(skip).limit(limit).all()
    return {"success": True, "total": total, "skip": skip, "limit": limit, "payments": payments}


@router.get("/{payment_id}")
def get_bill_payment(
    payment_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "view")
    payment = _get_payment(db, family_id, payment_id)
    _check_owner(payment, current_user, scope)
    transactions = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.bill_payment_id == payment.id,
    ).all()
    return {"success": True, "payment": payment, "transactions": transactions}


@router.delete("/{payment_id}", response_model=BillPaymentMessageResponse)
def void_bill_payment(
    payment_id: int,
    family_id: int = Query(..., gt=0),
    reason: str | None = Query(default=None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _authorize(db, current_user.id, family_id, "void")
    try:
        existing = _get_payment(db, family_id, payment_id)
        _get_bill(db, family_id, existing.bill_id, lock=True)
        payment = _get_payment(db, family_id, payment_id, lock=True)
        _check_owner(payment, current_user, scope)
        if payment.is_voided:
            raise HTTPException(status_code=409, detail="此付款紀錄已作廢")
        if payment.payment_type == "payment":
            active_refunds = db.query(BillPayment.id).filter(
                BillPayment.family_id == family_id,
                BillPayment.original_payment_id == payment.id,
                BillPayment.is_voided.is_(False),
            ).first()
            if active_refunds is not None:
                raise HTTPException(status_code=409, detail="此付款已有有效退款，請先作廢退款紀錄")

        transactions = db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.bill_payment_id == payment.id,
        ).with_for_update().all()
        if len(transactions) != 1 or transactions[0].is_voided:
            raise HTTPException(status_code=409, detail="付款對應交易不存在或狀態異常，無法作廢")
        now = datetime.now(timezone.utc)
        old_values = _audit_values(payment)
        payment.is_voided = True
        payment.voided_at = now
        payment.voided_by = current_user.id
        payment.void_reason = reason.strip() if reason and reason.strip() else None
        transactions[0].is_voided = True
        transactions[0].voided_at = now
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="void", entity_type="bill_payment", entity_id=payment.id,
            old_values=old_values,
            new_values={**_audit_values(payment), "void_reason": payment.void_reason},
            description="作廢帳單付款／退款及其對應帳戶交易",
        )
        db.commit()
        db.refresh(payment)
        return {"success": True, "message": "付款／退款紀錄及對應交易已作廢", "payment": payment}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        logger.exception("作廢帳單付款時發生資料完整性錯誤")
        raise HTTPException(status_code=409, detail="付款紀錄作廢失敗")
    except Exception:
        db.rollback()
        raise
