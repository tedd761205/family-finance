
import logging
from datetime import datetime, timezone
from decimal import Decimal

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
from app.models.transfer import Transfer
from app.models.transaction import Transaction
from app.services.audit_log import add_audit_log
from app.schemas.transfer import (
    TransferCreate,
    TransferUpdate,
    TransferResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/transfers",
    tags=["Transfers"],
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


def check_transfer_scope(
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


def check_transfer_owner(
    transfer: Transfer,
    user_id: int,
):
    if transfer.created_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權操作其他成員建立的轉帳",
        )


def check_transfer_active(
    transfer: Transfer,
):
    if transfer.is_voided:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此轉帳已作廢，無法再修改",
        )


# ============================================================
# 轉帳查詢
# ============================================================

def get_family_transfer(
    db: Session,
    transfer_id: int,
    family_id: int,
):
    transfer = (
        db.query(Transfer)
        .filter(
            Transfer.id == transfer_id,
            Transfer.family_id == family_id,
        )
        .first()
    )

    if transfer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此家庭的轉帳紀錄",
        )

    return transfer


def get_transfer_transactions(
    db: Session,
    transfer: Transfer,
):
    return (
        db.query(Transaction)
        .filter(
            Transaction.family_id == transfer.family_id,
            Transaction.transfer_id == transfer.id,
        )
        .order_by(Transaction.id.asc())
        .all()
    )


# ============================================================
# 帳戶驗證
# ============================================================

def validate_transfer_accounts(
    db: Session,
    family_id: int,
    from_account_id: int,
    to_account_id: int,
    currency_code: str,
    fee_amount: Decimal,
    fee_account_id: int | None,
):
    if from_account_id == to_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="轉出帳戶與轉入帳戶不可相同",
        )

    account_ids = {
        from_account_id,
        to_account_id,
    }

    if fee_amount > 0:
        if fee_account_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="有手續費時必須指定手續費扣款帳戶",
            )

        account_ids.add(fee_account_id)

    accounts = (
        db.query(Account)
        .filter(
            Account.family_id == family_id,
            Account.id.in_(account_ids),
        )
        .all()
    )

    account_map = {
        account.id: account
        for account in accounts
    }

    for account_id in account_ids:
        account = account_map.get(account_id)

        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的家庭帳戶",
            )

        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="轉帳使用的帳戶必須為啟用狀態",
            )

        if account.currency_code != currency_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="轉帳幣別必須與所有使用帳戶的幣別一致",
            )

    return account_map


# ============================================================
# 建立轉帳交易明細
# ============================================================

def create_transfer_transactions(
    db: Session,
    transfer: Transfer,
):
    """
    建立轉帳所需交易：

    1. 轉出帳戶：expense
    2. 轉入帳戶：income
    3. 手續費帳戶：expense（有手續費時）

    轉出與轉入交易互相關聯。
    """

    outgoing = Transaction(
        family_id=transfer.family_id,
        account_id=transfer.from_account_id,
        transaction_type="expense",
        amount=transfer.amount,
        currency_code=transfer.currency_code,
        transaction_date=transfer.transfer_date,
        description=transfer.description,
        transfer_id=transfer.id,
        created_by=transfer.created_by,
        note=transfer.note,
    )

    incoming = Transaction(
        family_id=transfer.family_id,
        account_id=transfer.to_account_id,
        transaction_type="income",
        amount=transfer.amount,
        currency_code=transfer.currency_code,
        transaction_date=transfer.transfer_date,
        description=transfer.description,
        transfer_id=transfer.id,
        created_by=transfer.created_by,
        note=transfer.note,
    )

    db.add_all([outgoing, incoming])
    db.flush()

    outgoing.related_transaction_id = incoming.id
    incoming.related_transaction_id = outgoing.id

    if transfer.fee_amount > 0:
        fee_transaction = Transaction(
            family_id=transfer.family_id,
            account_id=transfer.fee_account_id,
            transaction_type="expense",
            amount=transfer.fee_amount,
            currency_code=transfer.currency_code,
            transaction_date=transfer.transfer_date,
            description=f"{transfer.description}（轉帳手續費）",
            transfer_id=transfer.id,
            created_by=transfer.created_by,
            note=transfer.note,
        )

        db.add(fee_transaction)

    db.flush()


# ============================================================
# 新增轉帳
# ============================================================

@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增轉帳",
)
def create_transfer(
    payload: TransferCreate,
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

    check_transfer_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    validate_transfer_accounts(
        db=db,
        family_id=family_id,
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        currency_code=payload.currency_code,
        fee_amount=payload.fee_amount,
        fee_account_id=payload.fee_account_id,
    )

    transfer = Transfer(
        family_id=family_id,
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount=payload.amount,
        currency_code=payload.currency_code,
        transfer_date=payload.transfer_date,
        description=payload.description,
        fee_amount=payload.fee_amount,
        fee_account_id=payload.fee_account_id,
        note=payload.note,
        created_by=current_user.id,
    )

    try:
        db.add(transfer)
        db.flush()

        create_transfer_transactions(
            db=db,
            transfer=transfer,
        )

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="create",
            entity_type="transfer",
            entity_id=transfer.id,
            new_values={
                "from_account_id": transfer.from_account_id,
                "to_account_id": transfer.to_account_id,
                "amount": transfer.amount,
                "currency_code": transfer.currency_code,
                "transfer_date": transfer.transfer_date,
                "description": transfer.description,
                "fee_amount": transfer.fee_amount,
                "fee_account_id": transfer.fee_account_id,
                "note": transfer.note,
            },
            description="新增轉帳（含自動產生的交易明細）",
        )

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="update",
            entity_type="transfer",
            entity_id=transfer.id,
            old_values=old_values,
            new_values={
                "from_account_id": transfer.from_account_id,
                "to_account_id": transfer.to_account_id,
                "amount": transfer.amount,
                "currency_code": transfer.currency_code,
                "transfer_date": transfer.transfer_date,
                "description": transfer.description,
                "fee_amount": transfer.fee_amount,
                "fee_account_id": transfer.fee_account_id,
                "note": transfer.note,
            },
            description="修改轉帳及其交易明細",
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except IntegrityError:
        db.rollback()
        logger.exception("新增轉帳時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="轉帳資料關聯不合法或違反資料庫限制",
        )

    except Exception:
        db.rollback()
        raise


# ============================================================
# 查詢轉帳列表
# ============================================================

@router.get(
    "",
    summary="查詢轉帳列表",
)
def get_transfers(
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

    scope = check_transfer_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(Transfer).filter(
        Transfer.family_id == family_id,
    )

    if scope == "own":
        query = query.filter(
            Transfer.created_by == current_user.id,
        )

    if not include_voided:
        query = query.filter(
            Transfer.is_voided.is_(False),
        )

    if account_id is not None:
        query = query.filter(
            (
                (Transfer.from_account_id == account_id)
                | (Transfer.to_account_id == account_id)
                | (Transfer.fee_account_id == account_id)
            ),
        )

    if start_date is not None:
        query = query.filter(
            Transfer.transfer_date >= start_date,
        )

    if end_date is not None:
        query = query.filter(
            Transfer.transfer_date <= end_date,
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

    transfers = (
        query
        .order_by(
            Transfer.transfer_date.desc(),
            Transfer.id.desc(),
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
        "transfers": transfers,
    }


# ============================================================
# 查詢單筆轉帳
# ============================================================

@router.get(
    "/{transfer_id}",
    summary="查詢單筆轉帳",
)
def get_transfer(
    transfer_id: int,
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

    scope = check_transfer_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transfer = get_family_transfer(
        db=db,
        transfer_id=transfer_id,
        family_id=family_id,
    )

    if scope == "own":
        check_transfer_owner(
            transfer=transfer,
            user_id=current_user.id,
        )

    transactions = get_transfer_transactions(
        db=db,
        transfer=transfer,
    )

    return {
        "success": True,
        "transfer": transfer,
        "transactions": transactions,
    }


# ============================================================
# 修改轉帳
# ============================================================

@router.patch(
    "/{transfer_id}",
    response_model=TransferResponse,
    summary="修改轉帳",
)
def update_transfer(
    transfer_id: int,
    payload: TransferUpdate,
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

    scope = check_transfer_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transfer = get_family_transfer(
        db=db,
        transfer_id=transfer_id,
        family_id=family_id,
    )

    check_transfer_active(transfer)

    if scope == "own":
        check_transfer_owner(
            transfer=transfer,
            user_id=current_user.id,
        )

    changes = payload.model_dump(exclude_unset=True)

    new_values = {
        "from_account_id": transfer.from_account_id,
        "to_account_id": transfer.to_account_id,
        "amount": transfer.amount,
        "currency_code": transfer.currency_code,
        "transfer_date": transfer.transfer_date,
        "description": transfer.description,
        "fee_amount": transfer.fee_amount,
        "fee_account_id": transfer.fee_account_id,
        "note": transfer.note,
    }

    new_values.update(changes)

    validate_transfer_accounts(
        db=db,
        family_id=family_id,
        from_account_id=new_values["from_account_id"],
        to_account_id=new_values["to_account_id"],
        currency_code=new_values["currency_code"],
        fee_amount=new_values["fee_amount"],
        fee_account_id=new_values["fee_account_id"],
    )

    transactions = get_transfer_transactions(
        db=db,
        transfer=transfer,
    )

    primary_transactions = [
        item
        for item in transactions
        if item.related_transaction_id is not None
    ]

    fee_transactions = [
        item
        for item in transactions
        if item.related_transaction_id is None
    ]

    outgoing = next(
        (
            item
            for item in primary_transactions
            if item.transaction_type == "expense"
        ),
        None,
    )

    incoming = next(
        (
            item
            for item in primary_transactions
            if item.transaction_type == "income"
        ),
        None,
    )

    if (
        len(primary_transactions) != 2
        or outgoing is None
        or incoming is None
        or outgoing.related_transaction_id != incoming.id
        or incoming.related_transaction_id != outgoing.id
        or outgoing.is_voided
        or incoming.is_voided
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="轉帳交易明細不完整，無法修改",
        )

    if len(fee_transactions) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="轉帳手續費明細異常，無法修改",
        )

    fee_transaction = (
        fee_transactions[0]
        if fee_transactions
        else None
    )

    old_values = {
        "from_account_id": transfer.from_account_id,
        "to_account_id": transfer.to_account_id,
        "amount": transfer.amount,
        "currency_code": transfer.currency_code,
        "transfer_date": transfer.transfer_date,
        "description": transfer.description,
        "fee_amount": transfer.fee_amount,
        "fee_account_id": transfer.fee_account_id,
        "note": transfer.note,
    }

    try:
        for field, value in new_values.items():
            setattr(transfer, field, value)

        # 同步轉出交易
        outgoing.account_id = transfer.from_account_id
        outgoing.amount = transfer.amount
        outgoing.currency_code = transfer.currency_code
        outgoing.transaction_date = transfer.transfer_date
        outgoing.description = transfer.description
        outgoing.note = transfer.note

        # 同步轉入交易
        incoming.account_id = transfer.to_account_id
        incoming.amount = transfer.amount
        incoming.currency_code = transfer.currency_code
        incoming.transaction_date = transfer.transfer_date
        incoming.description = transfer.description
        incoming.note = transfer.note

        if transfer.fee_amount > 0:
            fee_description = (
                f"{transfer.description}（轉帳手續費）"
            )

            if fee_transaction is None:
                fee_transaction = Transaction(
                    family_id=transfer.family_id,
                    account_id=transfer.fee_account_id,
                    transaction_type="expense",
                    amount=transfer.fee_amount,
                    currency_code=transfer.currency_code,
                    transaction_date=transfer.transfer_date,
                    description=fee_description,
                    transfer_id=transfer.id,
                    created_by=transfer.created_by,
                    note=transfer.note,
                )
                db.add(fee_transaction)

            else:
                fee_transaction.account_id = transfer.fee_account_id
                fee_transaction.amount = transfer.fee_amount
                fee_transaction.currency_code = transfer.currency_code
                fee_transaction.transaction_date = transfer.transfer_date
                fee_transaction.description = fee_description
                fee_transaction.note = transfer.note
                fee_transaction.is_voided = False
                fee_transaction.voided_at = None

        elif fee_transaction is not None:
            if not fee_transaction.is_voided:
                fee_transaction.is_voided = True
                fee_transaction.voided_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(transfer)

        return transfer

    except IntegrityError:
        db.rollback()
        logger.exception("修改轉帳時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="轉帳修改失敗，可能違反資料關聯或限制",
        )

    except Exception:
        db.rollback()
        raise


# ============================================================
# 作廢整筆轉帳
# ============================================================

@router.delete(
    "/{transfer_id}",
    summary="作廢轉帳",
)
def void_transfer(
    transfer_id: int,
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

    scope = check_transfer_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    transfer = get_family_transfer(
        db=db,
        transfer_id=transfer_id,
        family_id=family_id,
    )

    check_transfer_active(transfer)

    if scope == "own":
        check_transfer_owner(
            transfer=transfer,
            user_id=current_user.id,
        )

    transactions = get_transfer_transactions(
        db=db,
        transfer=transfer,
    )

    now = datetime.now(timezone.utc)

    old_values = {
        "is_voided": transfer.is_voided,
        "voided_at": transfer.voided_at,
    }

    try:
        transfer.is_voided = True
        transfer.voided_at = now

        for transaction in transactions:
            if not transaction.is_voided:
                transaction.is_voided = True
                transaction.voided_at = now

        add_audit_log(
            db,
            family_id=family_id,
            actor_user_id=current_user.id,
            action="void",
            entity_type="transfer",
            entity_id=transfer.id,
            old_values=old_values,
            new_values={
                "is_voided": transfer.is_voided,
                "voided_at": transfer.voided_at,
                "voided_transaction_count": len(transactions),
            },
            description="作廢轉帳及其交易明細",
        )

        db.commit()
        db.refresh(transfer)

        return {
            "success": True,
            "message": "轉帳及其交易明細已成功作廢",
            "transfer": transfer,
            "voided_transaction_count": len(transactions),
        }

    except IntegrityError:
        db.rollback()
        logger.exception("作廢轉帳時發生資料完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="轉帳作廢失敗",
        )

    except Exception:
        db.rollback()
        raise
