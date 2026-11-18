
"""
家庭記帳系統：帳戶交易明細 API

功能：
1. 查詢指定帳戶的交易明細。
2. 支援日期區間查詢。
3. 支援分頁。
4. 支援 own / family 資料範圍。
5. 排除作廢交易。
6. 保留期初餘額明細。
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.schemas.account_report import AccountTransactionListResponse
from app.services.account_report import calculate_account_transactions


router = APIRouter(
    prefix="/reports",
    tags=["Account Reports"],
)


@router.get(
    "/account-transactions",
    response_model=AccountTransactionListResponse,
    summary="查詢帳戶交易明細",
)
def get_account_transactions(
    family_id: int = Query(..., gt=0),
    account_id: int = Query(..., gt=0),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查詢指定帳戶的交易明細。

    own：只查詢自己建立的交易。
    family：查詢整個家庭的交易。
    """

    try:
        # 1. 檢查家庭報表查看權限
        _, roles = require_permission(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
            permission_code="reports.view",
        )

        # 2. 分別檢查帳戶及交易資料範圍
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

        # 3. own 範圍分別限制帳戶與交易建立者
        account_created_by = (
            current_user.id
            if account_scope == "own"
            else None
        )
        created_by = (
            current_user.id
            if transaction_scope == "own"
            else None
        )

        # 4. 查詢交易明細
        return calculate_account_transactions(
            db=db,
            family_id=family_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            created_by=created_by,
            account_created_by=account_created_by,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        )

    except ValueError as exc:
        message = str(exc)

        if "找不到指定帳戶" in message:
            raise HTTPException(
                status_code=404,
                detail=message,
            )

        raise HTTPException(
            status_code=422,
            detail=message,
        )
