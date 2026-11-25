
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
    status_code=status.HTTP_410_GONE,
)
def invite_family_member(
    family_id: int,
    data: FamilyMemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """舊版直接加入 API 已停用；所有成員必須透過邀請連結自行接受。"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="直接加入家庭功能已停用，請建立家庭邀請並由受邀者自行接受",
    )


@router.get(
    "/{family_id}/members",
    status_code=status.HTTP_200_OK,
)
def list_family_members(
    family_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出家庭有效成員及其角色；必須具備 members.view 權限。"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此帳號已停用，無法查詢家庭成員",
        )

    try:
        require_permission(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
            permission_code="members.view",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="目前帳號沒有查看家庭成員的權限",
        )

    rows = (
        db.query(FamilyMember, User)
        .join(User, User.id == FamilyMember.user_id)
        .filter(
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
            User.is_active.is_(True),
        )
        .order_by(FamilyMember.joined_at.asc(), FamilyMember.id.asc())
        .all()
    )

    members = []
    for member, user in rows:
        role_names = [
            row[0]
            for row in (
                db.query(Role.name)
                .join(MemberRole, MemberRole.role_id == Role.id)
                .filter(
                    MemberRole.family_member_id == member.id,
                    MemberRole.family_id == family_id,
                    Role.family_id == family_id,
                    Role.is_active.is_(True),
                )
                .order_by(Role.name.asc())
                .all()
            )
        ]
        members.append({
            "family_member_id": member.id,
            "display_name": user.display_name,
            "email": user.email,
            "status": member.status,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            "roles": role_names,
            "role_ids": [
                row[0] for row in (
                    db.query(MemberRole.role_id)
                    .join(Role, Role.id == MemberRole.role_id)
                    .filter(
                        MemberRole.family_member_id == member.id,
                        MemberRole.family_id == family_id,
                        Role.family_id == family_id,
                        Role.is_active.is_(True),
                    ).all()
                )
            ],
            "is_me": user.id == current_user.id,
        })

    return {"success": True, "total": len(members), "members": members}
