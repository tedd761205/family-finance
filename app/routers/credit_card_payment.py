
import logging
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.models.account import Account
from app.models.credit_card_payment import CreditCardPayment
from app.models.transaction import Transaction
from app.services.audit_log import add_audit_log
from app.schemas.credit_card_payment import (
    CreditCardPaymentCreate,
    CreditCardPaymentUpdate,
    CreditCardPaymentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/credit-card-payments",
    tags=["Credit Card Payments"],
)


# ============================================================
# 權限檢查
# ============================================================

def check_family_permission(
    db: Session,
    user_id: int,
    family_id: int,
    permission_code: str,
):
    try:
        return require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code=permission_code,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def check_payment_scope(
    db: Session,
    roles: list,
    family_id: int,
):
    try:
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="transactions",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def check_payment_owner(
    payment: CreditCardPayment,
    user_id: int,
):
    if payment.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權操作其他成員建立的信用卡繳款",
        )


def check_payment_active(
    payment: CreditCardPayment,
):
    if payment.is_voided:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此筆信用卡繳款已作廢，無法再修改",
        )


# ============================================================
# 繳款查詢
# ============================================================

def get_family_payment(
    db: Session,
    payment_id: int,
    family_id: int,
):
    payment = (
        db.query(CreditCardPayment)
        .filter(
            CreditCardPayment.id == payment_id,
            CreditCardPayment.family_id == family_id,
        )
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此家庭的信用卡繳款紀錄",
        )

    return payment


def get_payment_transactions(
    db: Session,
    payment: CreditCardPayment,
):
    return (
        db.query(Transaction)
        .filter(
            Transaction.family_id == payment.family_id,
            Transaction.credit_card_payment_id == payment.id,
        )
        .order_by(Transaction.id.asc())
        .all()
    )


# ============================================================
# 帳戶驗證
# ============================================================

def validate_payment_accounts(
    db: Session,
    family_id: int,
    from_account_id: int,
    credit_card_account_id: int,
    currency_code: str,
):
    if from_account_id == credit_card_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="扣款帳戶不可與信用卡帳戶相同",
        )

    accounts = (
        db.query(Account)
        .filter(
            Account.family_id == family_id,
            Account.id.in_([
                from_account_id,
                credit_card_account_id,
            ]),
        )
        .all()
    )

    account_map = {
        account.id: account
        for account in accounts
    }

    from_account = account_map.get(from_account_id)
    credit_card_account = account_map.get(
        credit_card_account_id
    )

    if from_account is None or credit_card_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到指定的家庭帳戶",
        )

    if not from_account.is_active or not credit_card_account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="繳款使用的帳戶必須為啟用狀態",
        )

    if from_account.account_type not in (
        "bank",
        "cash",
        "e_payment",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="來源帳戶必須為銀行、現金或電子支付帳戶",
        )

    if credit_card_account.account_type != "credit_card":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="繳款目標必須為信用卡帳戶",
        )

    if (
        from_account.currency_code != currency_code
        or credit_card_account.currency_code != currency_code
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="繳款幣別必須與來源帳戶及信用卡帳戶一致",
        )

    return account_map


# ============================================================
# 建立信用卡繳款交易明細
# ============================================================

def create_payment_transactions(
    db: Session,
    payment: CreditCardPayment,
):
    """
    建立信用卡繳款的兩筆交易：

    1. 來源帳戶：expense
    2. 信用卡帳戶：income

    兩筆交易使用相同的 credit_card_payment_id，
    並透過 related_transaction_id 互相關聯。

    注意：
    信用卡帳戶的 income 是償還負債，
    不是家庭收入。
    """

    outgoing = Transaction(
        family_id=payment.family_id,
        account_id=payment.from_account_id,
        transaction_type="expense",
        amount=payment.amount,
        currency_code=payment.currency_code,
        transaction_date=payment.payment_date,
        description=payment.description,
        credit_card_payment_id=payment.id,
        created_by=payment.created_by,
        note=payment.note,
    )

    incoming = Transaction(
        family_id=payment.family_id,
        account_id=payment.credit_card_account_id,
        transaction_type="income",
        amount=payment.amount,
        currency_code=payment.currency_code,
        transaction_date=payment.payment_date,
        description=payment.description,
        credit_card_payment_id=payment.id,
        created_by=payment.created_by,
        note=payment.note,
    )

    db.add_all([outgoing, incoming])
    db.flush()

    outgoing.related_transaction_id = incoming.id
    incoming.related_transaction_id = outgoing.id

    db.flush()


# ============================================================
# 驗證繳款交易明細
# ============================================================

def validate_payment_transactions(
    transactions: list[Transaction],
):
    if len(transactions) != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="信用卡繳款交易明細不完整，無法操作",
        )

    outgoing = next(
        (
            item
            for item in transactions
            if item.transaction_type == "expense"
        ),
        None,
    )

    incoming = next(
        (
            item
            for item in transactions
            if item.transaction_type == "income"
        ),
        None,
    )

    if (
        outgoing is None
        or incoming is None
        or outgoing.related_transaction_id != incoming.id
        or incoming.related_transaction_id != outgoing.id
        or outgoing.is_voided
        or incoming.is_voided
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="信用卡繳款交易明細異常，無法操作",
        )

    return outgoing, incoming


# ============================================================
# 新增信用卡繳款
# ============================================================

@router.post(
    "",
    response_model=CreditCardPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增信用卡繳款",
)
def create_credit_card_payment(
    payload: CreditCardPaymentCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.transfer",
    )

    check_payment_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    validate_payment_accounts(
        db=db,
        family_id=family_id,
        from_account_id=payload.from_account_id,
        credit_card_account_id=payload.credit_card_account_id,
        currency_code=payload.currency_code,
    )

    payment = CreditCardPayment(
        family_id=family_id,
        from_account_id=payload.from_account_id,
        credit_card_account_id=payload.credit_card_account_id,
        amount=payload.amount,
        currency_code=payload.currency_code,
        payment_date=payload.payment_date,
        description=payload.description,
        note=payload.note,
        created_by=current_user.id,
    )

    try:
        db.add(payment)
        db.flush()

        create_payment_transactions(
            db=db,
            payment=payment,
        )

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="credit_card_payment",
            entity_id=payment.id,
            new_values={
                "from_account_id": payment.from_account_id,
                "credit_card_account_id": payment.credit_card_account_id,
                "amount": payment.amount,
                "currency_code": payment.currency_code,
                "payment_date": payment.payment_date,
                "description": payment.description,
                "note": payment.note,
            },
            description="新增信用卡繳款（含自動產生的交易明細）",
        )

        db.commit()
        db.refresh(payment)

        return payment

    except IntegrityError:
        db.rollback()
        logger.exception("新增信用卡繳款時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="信用卡繳款資料關聯不合法或違反資料庫限制",
        )

    except Exception:
        db.rollback()
        raise


# ============================================================
# 查詢信用卡繳款列表
# ============================================================

@router.get(
    "",
    summary="查詢信用卡繳款列表",
)
def get_credit_card_payments(
    family_id: int = Query(..., gt=0),
    account_id: int | None = Query(default=None, gt=0),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    include_voided: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="transactions.view",
    )

    scope = check_payment_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(CreditCardPayment).filter(
        CreditCardPayment.family_id == family_id,
    )

    if scope == "own":
        query = query.filter(
            CreditCardPayment.created_by == current_user.id,
        )

    if not include_voided:
        query = query.filter(
            CreditCardPayment.is_voided.is_(False),
        )

    if account_id is not None:
        query = query.filter(
            (
                (CreditCardPayment.from_account_id == account_id)
                | (
                    CreditCardPayment.credit_card_account_id
                    == account_id
                )
            ),
        )

    if start_date is not None:
        query = query.filter(
            CreditCardPayment.payment_date >= start_date,
        )

    if end_date is not None:
        query = query.filter(
            CreditCardPayment.payment_date <= end_date,
        )

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="開始日期不可晚於結束日期",
        )

    total = query.count()

    payments = (
        query
        .order_by(
            CreditCardPayment.payment_date.desc(),
            CreditCardPayment.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "payments": payments,
    }


# ============================================================
# 查詢單筆信用卡繳款
# ============================================================

@router.get(
    "/{payment_id}",
    summary="查詢單筆信用卡繳款",
)
def get_credit_card_payment(
    payment_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="transactions.view",
    )

    scope = check_payment_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    payment = get_family_payment(
        db=db,
        payment_id=payment_id,
        family_id=family_id,
    )

    if scope == "own":
        check_payment_owner(
            payment=payment,
            user_id=current_user.id,
        )

    transactions = get_payment_transactions(
        db=db,
        payment=payment,
    )

    return {
        "success": True,
        "payment": payment,
        "transactions": transactions,
    }


# ============================================================
# 修改信用卡繳款
# ============================================================

@router.patch(
    "/{payment_id}",
    response_model=CreditCardPaymentResponse,
    summary="修改信用卡繳款",
)
def update_credit_card_payment(
    payment_id: int,
    payload: CreditCardPaymentUpdate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="transactions.update",
    )

    scope = check_payment_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    payment = get_family_payment(
        db=db,
        payment_id=payment_id,
        family_id=family_id,
    )

    check_payment_active(payment)

    if scope == "own":
        check_payment_owner(
            payment=payment,
            user_id=current_user.id,
        )

    transactions = get_payment_transactions(
        db=db,
        payment=payment,
    )

    outgoing, incoming = validate_payment_transactions(
        transactions
    )

    changes = payload.model_dump(exclude_unset=True)

    old_values = {
        field: getattr(payment, field)
        for field in changes
    }

    try:
        for field, value in changes.items():
            setattr(payment, field, value)

        # 同步來源帳戶交易
        outgoing.amount = payment.amount
        outgoing.transaction_date = payment.payment_date
        outgoing.description = payment.description
        outgoing.note = payment.note

        # 同步信用卡帳戶交易
        incoming.amount = payment.amount
        incoming.transaction_date = payment.payment_date
        incoming.description = payment.description
        incoming.note = payment.note

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="update",
            entity_type="credit_card_payment",
            entity_id=payment.id,
            old_values=old_values,
            new_values={
                field: getattr(payment, field)
                for field in changes
            },
            description="修改信用卡繳款及其交易明細",
        )

        db.commit()
        db.refresh(payment)

        return payment

    except IntegrityError:
        db.rollback()
        logger.exception("修改信用卡繳款時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="信用卡繳款修改失敗，可能違反資料關聯或限制",
        )

    except Exception:
        db.rollback()
        raise


# ============================================================
# 作廢整筆信用卡繳款
# ============================================================

@router.delete(
    "/{payment_id}",
    summary="作廢信用卡繳款",
)
def void_credit_card_payment(
    payment_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="transactions.void",
    )

    scope = check_payment_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    payment = get_family_payment(
        db=db,
        payment_id=payment_id,
        family_id=family_id,
    )

    check_payment_active(payment)

    if scope == "own":
        check_payment_owner(
            payment=payment,
            user_id=current_user.id,
        )

    transactions = get_payment_transactions(
        db=db,
        payment=payment,
    )

    validate_payment_transactions(transactions)

    now = datetime.now(timezone.utc)
    old_values = {
        "is_voided": payment.is_voided,
        "voided_at": payment.voided_at,
    }

    try:
        payment.is_voided = True
        payment.voided_at = now

        for transaction in transactions:
            transaction.is_voided = True
            transaction.voided_at = now

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="void",
            entity_type="credit_card_payment",
            entity_id=payment.id,
            old_values=old_values,
            new_values={
                "is_voided": payment.is_voided,
                "voided_at": payment.voided_at,
                "voided_transaction_count": len(transactions),
            },
            description="作廢信用卡繳款及其交易明細",
        )

        db.commit()
        db.refresh(payment)

        return {
            "success": True,
            "message": "信用卡繳款及其交易明細已成功作廢",
            "payment": payment,
            "voided_transaction_count": len(transactions),
        }

    except IntegrityError:
        db.rollback()
        logger.exception("作廢信用卡繳款時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="信用卡繳款作廢失敗",
        )

    except Exception:
        db.rollback()
        raise
