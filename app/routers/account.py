
"""
家庭記帳系統：帳戶管理 API

功能：
1. 新增家庭帳戶。
2. 查詢家庭帳戶列表。
3. 查詢單一帳戶明細。
4. 修改帳戶資料。
5. 作廢帳戶（軟刪除）。
6. 查詢家庭所有帳戶餘額。
7. 查詢單一帳戶餘額。

安全機制：
- JWT 登入驗證。
- 家庭成員身分驗證。
- 角色功能權限驗證。
- own / family 資料範圍驗證。
- 家庭資料隔離。
- 作廢不實際刪除資料。
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)

from app.models.user import User
from app.models.account import Account

from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountListResponse,
    AccountMessageResponse,
)

from app.schemas.account_balance import (
    AccountBalanceResponse,
    AccountBalanceListResponse,
)

from app.services.account_balance import (
    calculate_account_balance,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"],
)


# =========================================================
# 共用權限檢查
# =========================================================

def check_family_permission(
    db: Session,
    user_id: int,
    family_id: int,
    permission_code: str,
):
    """檢查使用者是否具有指定家庭的功能權限。"""

    try:
        family_member, roles = require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code=permission_code,
        )

        return family_member, roles

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def check_account_scope(
    db: Session,
    roles: list,
    family_id: int,
):
    """取得帳戶資料範圍。"""

    try:
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="accounts",
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
    """取得交易資料範圍；帳戶餘額必須依交易範圍計算。"""

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


def get_family_account(
    db: Session,
    account_id: int,
    family_id: int,
) -> Account:
    """只允許取得指定家庭所屬的帳戶。"""

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
            detail="找不到此帳戶",
        )

    return account


def check_account_owner(
    account: Account,
    current_user: User,
    scope: str,
):
    """own 範圍只能操作自己建立的帳戶。"""

    if (
        scope == "own"
        and account.created_by != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此帳戶",
        )


def check_account_active(account: Account):
    """一般操作不允許使用已作廢帳戶。"""

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此帳戶已作廢，無法進行此操作",
        )


def validate_account_type_fields(
    account_type: str,
    credit_limit,
    statement_day,
    payment_due_day,
):
    """檢查信用卡專用欄位是否與帳戶類型一致。"""

    has_credit_card_fields = any(
        value is not None
        for value in (
            credit_limit,
            statement_day,
            payment_due_day,
        )
    )

    if (
        has_credit_card_fields
        and account_type != "credit_card"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="信用卡額度、結帳日及繳款日只能用於信用卡帳戶",
        )


# =========================================================
# 1. 新增帳戶
# =========================================================

@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    data: AccountCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新增家庭帳戶。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.create",
    )

    check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    validate_account_type_fields(
        account_type=data.account_type,
        credit_limit=data.credit_limit,
        statement_day=data.statement_day,
        payment_due_day=data.payment_due_day,
    )

    try:
        account = Account(
            family_id=family_id,
            name=data.name,
            account_type=data.account_type,
            currency_code=data.currency_code,
            institution_name=data.institution_name,
            account_number_last4=data.account_number_last4,
            credit_limit=data.credit_limit,
            statement_day=data.statement_day,
            payment_due_day=data.payment_due_day,
            note=data.note,
            created_by=current_user.id,
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return account

    except IntegrityError:
        db.rollback()

        logger.exception("新增帳戶時發生資料庫完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="帳戶資料與現有資料發生衝突",
        )

    except Exception:
        db.rollback()

        logger.exception("新增帳戶失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="新增帳戶失敗，請稍後再試",
        )


# =========================================================
# 2. 查詢家庭帳戶列表
# =========================================================

@router.get(
    "",
    response_model=AccountListResponse,
)
def get_accounts(
    family_id: int = Query(..., gt=0),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢指定家庭的帳戶列表。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.view",
    )

    scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(Account).filter(
        Account.family_id == family_id,
    )

    if not include_inactive:
        query = query.filter(
            Account.is_active.is_(True),
        )

    if scope == "own":
        query = query.filter(
            Account.created_by == current_user.id,
        )

    accounts = (
        query
        .order_by(
            Account.created_at.desc(),
            Account.id.desc(),
        )
        .all()
    )

    return AccountListResponse(
        success=True,
        total=len(accounts),
        accounts=accounts,
    )


# =========================================================
# 3. 查詢家庭所有帳戶餘額
# =========================================================

@router.get(
    "/balances",
    response_model=AccountBalanceListResponse,
)
def get_account_balances(
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢指定家庭所有有效帳戶的餘額。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.view",
    )

    # 帳戶列表使用 accounts 資料範圍
    account_scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    # 餘額計算使用 transactions 資料範圍
    transaction_scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(Account).filter(
        Account.family_id == family_id,
        Account.is_active.is_(True),
    )

    if account_scope == "own":
        query = query.filter(
            Account.created_by == current_user.id,
        )

    accounts = (
        query
        .order_by(
            Account.created_at.desc(),
            Account.id.desc(),
        )
        .all()
    )

    balances = [
        AccountBalanceResponse(
            **calculate_account_balance(
                db,
                account,
                created_by=(
                    current_user.id
                    if transaction_scope == "own"
                    else None
                ),
            )
        )
        for account in accounts
    ]

    return AccountBalanceListResponse(
        success=True,
        total=len(balances),
        balances=balances,
    )


# =========================================================
# 4. 查詢單一帳戶餘額
# =========================================================

@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
)
def get_single_account_balance(
    account_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢單一有效帳戶的目前餘額。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.view",
    )

    # 帳戶本身的查看權限
    account_scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    # 餘額內的交易資料範圍
    transaction_scope = check_transaction_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    account = get_family_account(
        db=db,
        account_id=account_id,
        family_id=family_id,
    )

    check_account_owner(
        account=account,
        current_user=current_user,
        scope=account_scope,
    )

    check_account_active(account)

    return AccountBalanceResponse(
        **calculate_account_balance(
            db,
            account,
            created_by=(
                current_user.id
                if transaction_scope == "own"
                else None
            ),
        )
    )


# =========================================================
# 5. 查詢單一帳戶
# =========================================================

@router.get(
    "/{account_id}",
    response_model=AccountResponse,
)
def get_account(
    account_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢單一有效帳戶明細。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.view",
    )

    scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    account = get_family_account(
        db=db,
        account_id=account_id,
        family_id=family_id,
    )

    check_account_owner(
        account=account,
        current_user=current_user,
        scope=scope,
    )

    check_account_active(account)

    return account


# =========================================================
# 6. 修改帳戶
# =========================================================

@router.patch(
    "/{account_id}",
    response_model=AccountResponse,
)
def update_account(
    account_id: int,
    data: AccountUpdate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改帳戶資料。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.update",
    )

    scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    account = get_family_account(
        db=db,
        account_id=account_id,
        family_id=family_id,
    )

    check_account_owner(
        account=account,
        current_user=current_user,
        scope=scope,
    )

    check_account_active(account)

    changes = data.model_dump(
        exclude_unset=True,
    )

    # 作廢只能透過 DELETE API 執行
    if "is_active" in changes:
        if changes["is_active"] is False:
            check_family_permission(
                db=db,
                user_id=current_user.id,
                family_id=family_id,
                permission_code="accounts.void",
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="請使用 DELETE API 作廢帳戶",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目前不開放透過修改 API 重新啟用帳戶",
        )

    # 使用修改後的完整資料進行驗證
    new_account_type = changes.get(
        "account_type",
        account.account_type,
    )

    new_credit_limit = changes.get(
        "credit_limit",
        account.credit_limit,
    )

    new_statement_day = changes.get(
        "statement_day",
        account.statement_day,
    )

    new_payment_due_day = changes.get(
        "payment_due_day",
        account.payment_due_day,
    )

    validate_account_type_fields(
        account_type=new_account_type,
        credit_limit=new_credit_limit,
        statement_day=new_statement_day,
        payment_due_day=new_payment_due_day,
    )

    try:
        for field, value in changes.items():
            setattr(account, field, value)

        db.commit()
        db.refresh(account)

        return account

    except IntegrityError:
        db.rollback()

        logger.exception("修改帳戶時發生資料庫完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="帳戶資料與現有資料發生衝突",
        )

    except Exception:
        db.rollback()

        logger.exception("修改帳戶失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改帳戶失敗，請稍後再試",
        )


# =========================================================
# 7. 作廢帳戶（軟刪除）
# =========================================================

@router.delete(
    "/{account_id}",
    response_model=AccountMessageResponse,
)
def deactivate_account(
    account_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """作廢帳戶，不實際刪除資料。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="accounts.void",
    )

    scope = check_account_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    account = get_family_account(
        db=db,
        account_id=account_id,
        family_id=family_id,
    )

    check_account_owner(
        account=account,
        current_user=current_user,
        scope=scope,
    )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此帳戶已經作廢",
        )

    try:
        account.is_active = False

        db.commit()
        db.refresh(account)

        return AccountMessageResponse(
            success=True,
            message="帳戶已成功作廢",
            account=account,
        )

    except Exception:
        db.rollback()

        logger.exception("作廢帳戶失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="作廢帳戶失敗，請稍後再試",
        )
