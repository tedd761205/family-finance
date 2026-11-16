
"""
家庭記帳系統：年度收支報表 API
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
from app.schemas.yearly_report import YearlyReportResponse
from app.services.yearly_report import calculate_yearly_summary


router = APIRouter(
    prefix="/reports",
    tags=["Yearly Reports"],
)


@router.get(
    "/yearly-summary",
    response_model=YearlyReportResponse,
    summary="查詢家庭年度收支報表",
)
def get_yearly_summary(
    family_id: int = Query(..., gt=0),
    year: int = Query(..., ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢指定年度的家庭收支報表。

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

    # 計算年度收支
    try:
        result = calculate_yearly_summary(
            db=db,
            family_id=family_id,
            year=year,
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
