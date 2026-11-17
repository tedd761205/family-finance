
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
    roles: list = Depends(
        require_permission("reports.view")
    ),
):
    """
    查詢家庭帳戶總覽。

    包含：
    1. 家庭所有帳戶。
    2. 各帳戶目前餘額。
    3. 依幣別統計資產與信用卡負債。
    """

    scope = require_data_scope(
        resource="transactions",
    )(
        db=db,
        current_user=current_user,
        family_id=family_id,
        roles=roles,
    )

    if not scope:
        raise HTTPException(
            status_code=403,
            detail="無權查看此家庭帳戶資料",
        )

    result = calculate_account_overview(
        db=db,
        family_id=family_id,
        active_only=active_only,
    )

    return result
