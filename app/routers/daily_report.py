
"""
家庭記帳系統：每日收支報表 API
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
from app.schemas.daily_report import DailyReportResponse
from app.services.daily_report import calculate_daily_summary


router = APIRouter(
    prefix="/reports",
    tags=["Daily Reports"],
)


@router.get(
    "/daily-summary",
    response_model=DailyReportResponse,
    summary="查詢家庭每日收支報表",
)
def get_daily_summary(
    family_id: int = Query(..., gt=0),
    report_date: date = Query(
        ...,
        description="報表日期，台灣當地日期 YYYY-MM-DD",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢指定日期的家庭收支報表。

    權限：
    - reports.view

    資料範圍：
    - family：查看整個家庭的交易
    - own：只查看自己建立的交易
    """

    # 檢查報表查看權限
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

    # 檢查交易資料範圍
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

    # 計算每日收支
    try:
        result = calculate_daily_summary(
            db=db,
            family_id=family_id,
            report_date=report_date,
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
