
"""
家庭記帳系統：帳戶總覽 API
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.schemas.account_overview import AccountOverviewResponse
from app.services.account_overview import (
    calculate_account_overview,
)


router = APIRouter(
    prefix="/reports",
    tags=["Account Reports"],
)


@router.get(
    "/account-overview",
    response_model=AccountOverviewResponse,
    summary="查詢家庭帳戶總覽",
)
def get_account_overview(
    family_id: int = Query(..., gt=0),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢家庭帳戶總覽。

    權限：
    - reports.view

    資料範圍：
    - family：使用家庭全部有效交易計算餘額。
    - own：只使用目前登入者建立的有效交易計算餘額。
    """

    try:
        _, roles = require_permission(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
            permission_code="reports.view",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        )

    try:
        account_scope = require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="accounts",
        )
        transaction_scope = require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="transactions",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        )

    try:
        result = calculate_account_overview(
            db=db,
            family_id=family_id,
            active_only=active_only,
            account_created_by=(
                current_user.id if account_scope == "own" else None
            ),
            transaction_created_by=(
                current_user.id if transaction_scope == "own" else None
            ),
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
