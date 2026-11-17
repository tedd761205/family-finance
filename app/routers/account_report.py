
"""
家庭記帳系統：帳戶收支統計 API
"""

from datetime import date

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
from app.schemas.account_report import AccountReportResponse
from app.services.account_report import calculate_account_summary


router = APIRouter(
    prefix="/reports",
    tags=["Account Reports"],
)


@router.get(
    "/account-summary",
    response_model=AccountReportResponse,
    summary="查詢家庭帳戶收支統計",
)
def get_account_summary(
    family_id: int = Query(..., gt=0),
    account_id: int = Query(..., gt=0),
    start_date: date | None = Query(
        None,
        description="統計開始日期，台灣當地日期",
    ),
    end_date: date | None = Query(
        None,
        description="統計結束日期，台灣當地日期",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢指定帳戶的收支統計。

    支援：
    - 銀行帳戶
    - 現金帳戶
    - 信用卡帳戶
    - 電子支付帳戶
    - 不限日期
    - 單日統計
    - 月份統計
    - 年度統計
    - 自訂日期區間

    權限：
    - reports.view

    資料範圍：
    - family：查看整個家庭的交易
    - own：只查看自己建立的交易
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

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=422,
            detail="start_date 不可晚於 end_date",
        )

    try:
        result = calculate_account_summary(
            db=db,
            family_id=family_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            created_by=(
                current_user.id if scope == "own" else None
            ),
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "找不到指定帳戶" in str(exc) else 422,
            detail=str(exc),
        )
