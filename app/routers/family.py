
"""
家庭記帳系統：家庭管理 API

功能：
1. 建立家庭
2. 自動將建立者加入家庭
3. 初始化預設角色及權限
4. 自動指派建立者為家庭管理員
5. 查詢目前登入者加入的家庭清單
6. 邀請已註冊使用者加入指定家庭
7. 自動指派新成員為一般成員

安全原則：
- 必須先登入才能操作。
- user_id 一律從 JWT 驗證後的 current_user 取得。
- 邀請成員只接受 Email，不接受前端指定 user_id 或 role_id。
- 邀請操作必須具備 members.invite 權限。
- 新成員預設使用一般成員角色。
- 建立及邀請操作由同一個資料庫交易完成。
- 家庭清單只顯示 active 狀態的家庭成員。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission

from app.models.user import User
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.member_role import MemberRole
from app.models.role import Role

from app.schemas.family import (
    FamilyCreate,
    FamilyCreateResponse,
    FamilyListItem,
    FamilyListResponse,
    FamilyMemberInvite,
    FamilyMemberInviteResponse,
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


@router.get(
    "/mine",
    response_model=FamilyListResponse,
    status_code=status.HTTP_200_OK,
)
def get_my_families(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    查詢目前登入者加入的所有有效家庭。

    只回傳 active 狀態的家庭成員紀錄。
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用，無法查詢家庭",
        )

    rows = (
        db.query(
            Family.id.label("family_id"),
            Family.name.label("family_name"),
            Family.currency.label("currency"),
            FamilyMember.id.label("family_member_id"),
            FamilyMember.status.label("status"),
        )
        .join(
            FamilyMember,
            FamilyMember.family_id == Family.id,
        )
        .filter(
            FamilyMember.user_id == current_user.id,
            FamilyMember.status == "active",
        )
        .order_by(
            Family.created_at.asc(),
            Family.id.asc(),
        )
        .all()
    )

    families = [
        FamilyListItem(
            family_id=row.family_id,
            family_name=row.family_name,
            currency=row.currency,
            family_member_id=row.family_member_id,
            status=row.status,
        )
        for row in rows
    ]

    return FamilyListResponse(
        success=True,
        total=len(families),
        families=families,
    )


@router.post(
    "/{family_id}/members",
    response_model=FamilyMemberInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_family_member(
    family_id: int,
    data: FamilyMemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    邀請已註冊使用者加入指定家庭。

    規則：
    1. 邀請人必須登入且帳號有效。
    2. 邀請人必須具備 members.invite 權限。
    3. 透過 Email 查找已註冊使用者。
    4. 新成員自動指派一般成員角色。
    5. 已加入的成員不可重複加入。
    6. 曾退出的成員可以重新加入。
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用，無法邀請家庭成員",
        )

    try:
        # 1. 檢查邀請人的家庭成員邀請權限
        try:
            require_permission(
                db=db,
                user_id=current_user.id,
                family_id=family_id,
                permission_code="members.invite",
            )

        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="目前帳號沒有邀請家庭成員的權限",
            )

        # 2. 確認家庭存在
        family = (
            db.query(Family)
            .filter(
                Family.id == family_id,
            )
            .first()
        )

        if family is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的家庭",
            )

        # 3. 透過 Email 查找使用者
        normalized_email = str(data.email).strip().lower()

        target_user = (
            db.query(User)
            .filter(
                func.lower(User.email) == normalized_email,
            )
            .first()
        )

        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="此 Email 尚未註冊，請先建立使用者帳號",
            )

        if not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此使用者帳號已停用，無法加入家庭",
            )

        # 4. 不允許邀請自己
        if target_user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能邀請自己加入家庭",
            )

        # 5. 查找家庭的既有成員紀錄
        existing_member = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.family_id == family_id,
                FamilyMember.user_id == target_user.id,
            )
            .first()
        )

        if (
            existing_member is not None
            and existing_member.status == "active"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此使用者已經是家庭成員，不可重複加入",
            )

        # 6. 查找此家庭的系統預設一般成員角色
        member_role = (
            db.query(Role)
            .filter(
                Role.family_id == family_id,
                Role.name == "一般成員",
                Role.is_system.is_(True),
                Role.is_active.is_(True),
            )
            .first()
        )

        if member_role is None:
            logger.error(
                "家庭 %s 找不到有效的系統一般成員角色",
                family_id,
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="家庭一般成員角色尚未初始化，請聯絡系統管理員",
            )

        # 7. 建立新成員或重新啟用既有成員
        if existing_member is None:
            new_member = FamilyMember(
                family_id=family_id,
                user_id=target_user.id,
                status="active",
            )

            db.add(new_member)
            db.flush()

        else:
            # 曾經退出家庭：重新啟用原有成員紀錄
            new_member = existing_member

            new_member.status = "active"
            new_member.left_at = None

            # 清除舊角色，重新套用預設一般成員角色
            (
                db.query(MemberRole)
                .filter(
                    MemberRole.family_member_id == new_member.id,
                    MemberRole.family_id == family_id,
                )
                .delete(synchronize_session=False)
            )

            db.flush()

        # 8. 指派一般成員角色
        new_assignment = MemberRole(
            family_member_id=new_member.id,
            role_id=member_role.id,
            family_id=family_id,
        )

        db.add(new_assignment)

        # 9. 同一個資料庫交易完成
        db.commit()

        return FamilyMemberInviteResponse(
            success=True,
            family_id=family_id,
            family_member_id=new_member.id,
            user_id=target_user.id,
            email=target_user.email,
            display_name=target_user.display_name,
            role_id=member_role.id,
            role_name=member_role.name,
            status=new_member.status,
        )

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        logger.exception(
            "邀請家庭成員時發生資料庫完整性錯誤"
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="加入家庭時發生資料衝突，請重新確認成員是否已加入",
        )

    except Exception:
        db.rollback()

        logger.exception(
            "邀請家庭成員失敗"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="邀請家庭成員失敗，請稍後再試",
        )
