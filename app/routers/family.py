
"""
家庭記帳系統：家庭管理 API

功能：
1. 建立家庭
2. 自動將建立者加入家庭
3. 初始化預設角色及權限
4. 自動指派建立者為家庭管理員

安全原則：
- 必須先登入才能建立家庭。
- user_id 一律從 JWT 驗證後的 current_user 取得。
- 不接受前端指定建立者。
- 所有建立操作由同一個資料庫交易完成。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.family import (
    FamilyCreate,
    FamilyCreateResponse,
)
from app.services.family_initializer import (
    create_family_with_admin,
)


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/families",
    tags=["Families"],
)


@router.post(
    "",
    response_model=FamilyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_family(
    data: FamilyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    建立家庭。

    使用目前登入者作為家庭建立者，
    不接受前端傳入 user_id。
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用，無法建立家庭",
        )

    try:
        result = create_family_with_admin(
            db=db,
            user_id=current_user.id,
            family_name=data.name,
            currency=data.currency,
        )

        # 初始化服務不自行 commit，
        # 由 API 呼叫端統一提交交易。
        db.commit()

        return FamilyCreateResponse(
            **result
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    except IntegrityError:
        db.rollback()

        logger.exception(
            "建立家庭時發生資料庫完整性錯誤"
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="建立家庭時發生資料衝突，請稍後再試",
        )

    except Exception:
        db.rollback()

        logger.exception(
            "建立家庭失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="建立家庭失敗，請稍後再試",
        )
