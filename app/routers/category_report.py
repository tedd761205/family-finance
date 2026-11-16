
"""
家庭記帳系統：分類收支統計 API
"""

from datetime import date
from typing import Literal

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
from app.schemas.category_report import CategoryReportResponse
from app.services.category_report import calculate_category_summary


router = APIRouter(
    prefix="/reports",
    tags=["Category Reports"],
)


@router.get(
    "/category-summary",
    response_model=CategoryReportResponse,
    summary="查詢家庭分類收支統計",
)
def get_category_summary(
    family_id: int = Query(..., gt=0),
    start_date: date | None = Query(
        None,
        description="統計開始日期，台灣當地日期",
    ),
    end_date: date | None = Query(
        None,
        description="統計結束日期，台灣當地日期",
    ),
    transaction_type: Literal["income", "expense"] | None = Query(
        None,
        description="收入或支出；不指定表示同時統計",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢指定家庭的分類收支統計。

    支援：
    - 不限日期
    - 單日統計
    - 月份統計
    - 年度統計
    - 自訂日期區間
    - 收入分類
    - 支出分類
    - 多幣別分開統計

    權限：
    - reports.view

    資料範圍：
    - family：查看整個家庭的交易
    - own：只查看自己建立的交易
    """

    # --------------------------------------------------
    # 1. 檢查報表查看權限
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 2. 檢查交易資料範圍
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 3. 檢查日期區間
    # --------------------------------------------------

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=422,
            detail="start_date 不可晚於 end_date",
        )

    # --------------------------------------------------
    # 4. 計算分類收支統計
    # --------------------------------------------------

    try:
        result = calculate_category_summary(
            db=db,
            family_id=family_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            created_by=(
                current_user.id
                if scope == "own"
                else None
            ),
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
