
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.purchase_line_item import PurchaseLineItem
from app.services.audit_log import add_audit_log
from app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    PurchaseLineItemCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"],
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
    """確認使用者具有指定家庭的功能權限"""

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


def check_transaction_scope(
    db: Session,
    roles: list,
    family_id: int,
):
    """取得交易資料範圍：own 或 family"""

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


# ============================================================
# 交易資料查詢
# ============================================================

def get_family_transaction(
    db: Session,
    transaction_id: int,
    family_id: int,
):
    """取得指定家庭的交易，防止跨家庭存取"""

    transaction = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.family_id == family_id,
        )
        .first()
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此交易紀錄",
        )

    return transaction


def check_transaction_owner(
    transaction: Transaction,
    user_id: int,
):
    """own 資料範圍只能操作自己建立的交易"""

    if transaction.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權操作其他成員建立的交易",
        )


def check_transaction_active(
    transaction: Transaction,
):
    """確認交易尚未作廢"""

    if transaction.is_voided:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此交易已作廢，無法再修改",
        )


def check_transaction_not_managed(
    transaction: Transaction,
):
    """
    防止透過一般交易 API 修改或作廢由專用 API 管理的交易。

    1. transfer_id 不為空：
       必須透過 /transfers 管理。

    2. credit_card_payment_id 不為空：
       必須透過 /credit-card-payments 管理。
    """

    if transaction.transfer_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此交易屬於轉帳紀錄，請透過轉帳管理 API 操作",
        )

    if transaction.credit_card_payment_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此交易屬於信用卡繳款紀錄，請透過信用卡繳款管理 API 操作",
        )

    if transaction.bill_payment_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此交易屬於帳單付款／退款紀錄，請透過帳單付款管理 API 操作",
        )


# ============================================================
# 期初餘額驗證
# ============================================================

def check_opening_balance_exists(
    db: Session,
    family_id: int,
    account_id: int,
):
    """確認帳戶是否已有有效期初餘額"""

    exists = (
        db.query(Transaction.id)
        .filter(
            Transaction.family_id == family_id,
            Transaction.account_id == account_id,
            Transaction.transaction_type == "opening_balance",
            Transaction.is_voided.is_(False),
        )
        .first()
    )

    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此帳戶已存在有效的期初餘額，請勿重複新增",
        )


def is_opening_balance_unique_violation(
    exc: IntegrityError,
) -> bool:
    """辨識期初餘額唯一索引衝突"""

    original_error = getattr(exc, "orig", None)
    diagnostic = getattr(original_error, "diag", None)

    constraint_name = getattr(
        diagnostic,
        "constraint_name",
        None,
    )

    return (
        constraint_name
        == "uq_transactions_active_opening_balance"
    )


# ============================================================
# 交易類型轉換驗證
# ============================================================

def validate_transaction_type_transition(
    old_type: str,
    new_type: str,
):
    """防止期初餘額與一般收入、支出互相轉換"""

    if old_type == new_type:
        return

    if (
        old_type == "opening_balance"
        or new_type == "opening_balance"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="期初餘額不可與一般收入或支出交易互相轉換",
        )


# ============================================================
# 帳戶及分類驗證
# ============================================================

def validate_account(
    db: Session,
    account_id: int,
    family_id: int,
    currency_code: str,
):
    """確認帳戶存在、屬於同一家庭且仍啟用"""

    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.family_id == family_id,
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此家庭帳戶",
        )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此帳戶已停用",
        )

    if account.currency_code != currency_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="交易幣別必須與帳戶幣別一致",
        )

    return account


def validate_category(
    db: Session,
    category_id: int | None,
    family_id: int,
    transaction_type: str,
):
    """確認分類存在、啟用且屬於同一家庭"""

    if category_id is None:
        return None

    if transaction_type == "opening_balance":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="期初餘額不可指定收入或支出分類",
        )

    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.is_active.is_(True),
            (
                (Category.family_id == family_id)
                | (Category.family_id.is_(None))
            ),
        )
        .first()
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此家庭可使用的啟用中分類",
        )

    if category.category_type != transaction_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分類類型與交易類型不一致",
        )

    return category




# ============================================================
# 採買商品明細
# ============================================================

PURCHASE_AMOUNT_QUANTUM = Decimal("0.0001")
PURCHASE_AMOUNT_LIMIT = Decimal("10000000000000000")


def validate_purchase_items(
    transaction_type: str,
    purchase_items: list[PurchaseLineItemCreate],
):
    """商品明細只允許掛在一般支出交易。"""

    if purchase_items and transaction_type != "expense":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商品明細只能附加在支出紀錄",
        )


def build_purchase_line_items(
    *,
    family_id: int,
    user_id: int,
    purchase_items: list[PurchaseLineItemCreate],
) -> list[PurchaseLineItem]:
    """計算明細小計並建立同一家庭範圍的 ORM 子資料。"""

    records = []
    for index, item in enumerate(purchase_items):
        quantity = Decimal(item.quantity)
        unit_price = Decimal(item.unit_price)
        raw_line_total = quantity * unit_price
        if raw_line_total >= PURCHASE_AMOUNT_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="商品小計超出可儲存的金額範圍",
            )
        line_total = raw_line_total.quantize(
            PURCHASE_AMOUNT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        records.append(
            PurchaseLineItem(
                family_id=family_id,
                item_name=item.item_name,
                quantity=quantity,
                unit=item.unit,
                unit_price=unit_price,
                line_total=line_total,
                sort_order=index,
                created_by=user_id,
            )
        )

    return records


def purchase_items_audit_values(purchase_items) -> list[dict]:
    """產生可寫入 JSONB 稽核紀錄的商品明細快照。"""

    return [
        {
            "item_name": item.item_name,
            "quantity": item.quantity,
            "unit": item.unit,
            "unit_price": item.unit_price,
            "line_total": item.line_total,
            "sort_order": item.sort_order,
        }
        for item in purchase_items
    ]


# ============================================================
# 新增交易
# ============================================================

@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增交易",
)
def create_transaction(
    payload: TransactionCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="transactions.create",
    )

    check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transaction_type = payload.transaction_type.value

    validate_purchase_items(
        transaction_type=transaction_type,
        purchase_items=payload.purchase_items,
    )

    validate_account(
        db=db,
        account_id=payload.account_id,
        family_id=family_id,
        currency_code=payload.currency_code,
    )

    validate_category(
        db=db,
        category_id=payload.category_id,
        family_id=family_id,
        transaction_type=transaction_type,
    )

    if transaction_type == "opening_balance":
        check_opening_balance_exists(
            db=db,
            family_id=family_id,
            account_id=payload.account_id,
        )

    transaction = Transaction(
        family_id=family_id,
        account_id=payload.account_id,
        transaction_type=transaction_type,
        amount=payload.amount,
        currency_code=payload.currency_code,
        transaction_date=payload.transaction_date,
        description=payload.description,
        category_id=payload.category_id,
        external_reference=payload.external_reference,
        note=payload.note,
        created_by=current_user.id,
        purchase_items=build_purchase_line_items(
            family_id=family_id,
            user_id=current_user.id,
            purchase_items=payload.purchase_items,
        ),
    )

    try:
        db.add(transaction)
        db.flush()

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="transaction",
            entity_id=transaction.id,
            new_values={
                "account_id": transaction.account_id,
                "transaction_type": transaction.transaction_type,
                "amount": transaction.amount,
                "currency_code": transaction.currency_code,
                "transaction_date": transaction.transaction_date,
                "description": transaction.description,
                "category_id": transaction.category_id,
                "external_reference": transaction.external_reference,
                "note": transaction.note,
                "purchase_items": purchase_items_audit_values(
                    transaction.purchase_items
                ),
            },
            description="新增交易",
        )

        db.commit()
        db.refresh(transaction)

        return transaction

    except IntegrityError as exc:
        db.rollback()
        logger.exception("新增交易時發生資料完整性錯誤")

        if is_opening_balance_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此帳戶已存在有效的期初餘額，請勿重複新增",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="交易資料關聯不合法或違反資料庫限制",
        )


# ============================================================
# 查詢交易列表
# ============================================================

@router.get(
    "",
    summary="查詢交易列表",
)
def get_transactions(
    family_id: int = Query(..., gt=0),
    account_id: int | None = Query(default=None, gt=0),
    category_id: int | None = Query(default=None, gt=0),
    transaction_type: str | None = Query(
        default=None,
        pattern="^(income|expense|opening_balance)$",
    ),
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

    scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(Transaction).options(
        selectinload(Transaction.purchase_items),
    ).filter(
        Transaction.family_id == family_id,
    )

    if scope == "own":
        query = query.filter(
            Transaction.created_by == current_user.id,
        )

    if not include_voided:
        query = query.filter(
            Transaction.is_voided.is_(False),
        )

    if account_id is not None:
        query = query.filter(
            Transaction.account_id == account_id,
        )

    if category_id is not None:
        query = query.filter(
            Transaction.category_id == category_id,
        )

    if transaction_type is not None:
        query = query.filter(
            Transaction.transaction_type == transaction_type,
        )

    if start_date is not None:
        query = query.filter(
            Transaction.transaction_date >= start_date,
        )

    if end_date is not None:
        query = query.filter(
            Transaction.transaction_date <= end_date,
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

    transactions = (
        query
        .order_by(
            Transaction.transaction_date.desc(),
            Transaction.id.desc(),
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
        "transactions": transactions,
    }


# ============================================================
# 查詢單筆交易
# ============================================================

@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="查詢單筆交易",
)
def get_transaction(
    transaction_id: int,
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

    scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transaction = get_family_transaction(
        db=db,
        transaction_id=transaction_id,
        family_id=family_id,
    )

    if scope == "own":
        check_transaction_owner(
            transaction=transaction,
            user_id=current_user.id,
        )

    return transaction


# ============================================================
# 修改交易
# ============================================================

@router.patch(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="修改交易",
)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
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

    scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transaction = get_family_transaction(
        db=db,
        transaction_id=transaction_id,
        family_id=family_id,
    )

    check_transaction_active(transaction)

    check_transaction_not_managed(transaction)

    if scope == "own":
        check_transaction_owner(
            transaction=transaction,
            user_id=current_user.id,
        )

    changes = payload.model_dump(exclude_unset=True)
    purchase_items_were_provided = "purchase_items" in changes
    changes.pop("purchase_items", None)
    purchase_items_payload = (
        payload.purchase_items
        if purchase_items_were_provided
        else []
    )

    new_type = changes.get(
        "transaction_type",
        transaction.transaction_type,
    )

    if hasattr(new_type, "value"):
        new_type = new_type.value

    validate_transaction_type_transition(
        old_type=transaction.transaction_type,
        new_type=new_type,
    )

    if new_type != "expense" and transaction.purchase_items and not purchase_items_were_provided:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此交易已有商品明細；轉為非支出前請先清除商品明細",
        )

    validate_purchase_items(
        transaction_type=new_type,
        purchase_items=purchase_items_payload,
    )

    new_category_id = changes.get(
        "category_id",
        transaction.category_id,
    )

    validate_category(
        db=db,
        category_id=new_category_id,
        family_id=family_id,
        transaction_type=new_type,
    )

    if "transaction_type" in changes:
        changes["transaction_type"] = new_type

    old_values = {
        field: getattr(transaction, field)
        for field in changes
    }
    new_values = {}

    for field, value in changes.items():
        setattr(transaction, field, value)

    try:
        if purchase_items_were_provided:
            old_values["purchase_items"] = purchase_items_audit_values(
                transaction.purchase_items
            )
            transaction.purchase_items.clear()
            transaction.purchase_items.extend(
                build_purchase_line_items(
                    family_id=family_id,
                    user_id=current_user.id,
                    purchase_items=purchase_items_payload,
                )
            )
            db.flush()
            new_values["purchase_items"] = purchase_items_audit_values(
                transaction.purchase_items
            )

        new_values.update({
            field: getattr(transaction, field)
            for field in changes
        })

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="update",
            entity_type="transaction",
            entity_id=transaction.id,
            old_values=old_values,
            new_values=new_values,
            description="修改交易",
        )

        db.commit()
        db.refresh(transaction)

        return transaction

    except IntegrityError:
        db.rollback()
        logger.exception("修改交易時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="交易資料修改失敗，可能違反資料關聯或限制",
        )


# ============================================================
# 作廢交易
# ============================================================

@router.delete(
    "/{transaction_id}",
    summary="作廢交易",
)
def void_transaction(
    transaction_id: int,
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

    scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transaction = get_family_transaction(
        db=db,
        transaction_id=transaction_id,
        family_id=family_id,
    )

    check_transaction_active(transaction)

    check_transaction_not_managed(transaction)

    if scope == "own":
        check_transaction_owner(
            transaction=transaction,
            user_id=current_user.id,
        )

    old_values = {
        "is_voided": transaction.is_voided,
        "voided_at": transaction.voided_at,
    }
    transaction.is_voided = True
    transaction.voided_at = datetime.now(timezone.utc)

    try:
        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="void",
            entity_type="transaction",
            entity_id=transaction.id,
            old_values=old_values,
            new_values={
                "is_voided": transaction.is_voided,
                "voided_at": transaction.voided_at,
            },
            description="作廢交易",
        )

        db.commit()
        db.refresh(transaction)

        return {
            "success": True,
            "message": "交易已成功作廢",
            "transaction": transaction,
        }

    except IntegrityError:
        db.rollback()
        logger.exception("作廢交易時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="交易作廢失敗",
        )
