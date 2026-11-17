
from fastapi import APIRouter, Depends, HTTPException, Query
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
)
def get_account_overview(
    family_id: int = Query(..., gt=0),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查詢家庭帳戶總覽。

    功能：
    1. 查詢家庭帳戶。
    2. 計算各帳戶目前餘額。
    3. 區分資產與信用卡負債。
    4. 依幣別分組統計。
    5. 支援啟用帳戶篩選。
    """

    try:
        _, roles = require_permission(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
            permission_code="reports.view",
        )

        scope = require_data_scope(
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

    result = calculate_account_overview(
        db=db,
        family_id=family_id,
        active_only=active_only,
    )

    return result
