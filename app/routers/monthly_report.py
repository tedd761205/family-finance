
"""
家庭記帳系統：月份收支報表 API

功能：
1. 查詢指定家庭、指定年月的收支統計。
2. 支援多幣別分開統計。
3. 使用台灣時間計算月份。
4. 套用登入驗證。
5. 套用 reports.view 權限。
6. 套用 own / family 資料範圍。
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.schemas.monthly_report import MonthlyReportResponse
from app.services.monthly_report import calculate_monthly_summary


router = APIRouter(
    prefix="/reports",
    tags=["Monthly Reports"],
)


@router.get(
    "/monthly-summary",
    response_model=MonthlyReportResponse,
    summary="查詢家庭月份收支報表",
)
def get_monthly_summary(
    family_id: int = Query(..., gt=0),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
            status_code=status.HTTP_403_FORBIDDEN,
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
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )

    # --------------------------------------------------
    # 3. 執行月份統計
    # --------------------------------------------------

    try:
        result = calculate_monthly_summary(
            db=db,
            family_id=family_id,
            year=year,
            month=month,
            created_by=(
                current_user.id
                if scope == "own"
                else None
            ),
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except HTTPException:
        raise

    except Exception:
        raise


