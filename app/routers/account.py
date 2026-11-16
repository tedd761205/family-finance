

"""
家庭記帳系統：帳戶管理 API

功能：
1. 新增家庭帳戶。
2. 查詢家庭帳戶列表。
3. 查詢單一帳戶明細。
4. 修改帳戶資料。
5. 作廢帳戶（軟刪除）。

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
# 3. 查詢單一帳戶
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
    """查詢單一帳戶明細。"""

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

    return account


# =========================================================
# 4. 修改帳戶
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

    changes = data.model_dump(
        exclude_unset=True,
    )

    # 作廢帳戶必須另外具備 accounts.void 權限
    if changes.get("is_active") is False:
        check_family_permission(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
            permission_code="accounts.void",
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
# 5. 作廢帳戶（軟刪除）
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
