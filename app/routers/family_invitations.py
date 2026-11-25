"""安全的家庭邀請流程：可先邀請尚未註冊的家人。"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import require_permission
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.member_role import MemberRole
from app.models.role import Role
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.family_invitation import FamilyInvitation
from app.schemas.family_invitation import (
    FamilyInvitationCreate,
    FamilyInvitationCreateResponse,
    FamilyInvitationAccept,
    FamilyInvitationActionResponse,
)

router = APIRouter(prefix="/families", tags=["Family Invitations"])
INVITATION_TTL_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _build_invite_url(public_app_url: str, raw_token: str) -> str:
    """Build an invite URL that asks LINE to open it in the external browser."""
    base_url = public_app_url.rstrip("/")
    encoded_token = quote(raw_token, safe="")
    # LINE supports openExternalBrowser=1 for ordinary web URLs. Keep the
    # one-time token in the fragment so it is not sent in the initial HTTP request.
    return f"{base_url}/?openExternalBrowser=1#invite={encoded_token}"


def _require_inviter(db: Session, user: User, family_id: int) -> None:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="此帳號已停用")
    try:
        require_permission(
            db=db, user_id=user.id, family_id=family_id,
            permission_code="members.invite",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="目前帳號沒有邀請家庭成員的權限") from exc


def _require_verified_google_email(db: Session, user: User, email: str) -> None:
    """只接受已透過 Google OAuth 驗證並綁定至此 User 的相同 Email。"""
    identity = (
        db.query(UserIdentity)
        .filter(
            UserIdentity.user_id == user.id,
            UserIdentity.provider == "google",
            func.lower(UserIdentity.email) == email,
        )
        .first()
    )
    if identity is None:
        raise HTTPException(
            status_code=403,
            detail="請先使用受邀 Email 的 Google 帳號登入，再接受家庭邀請",
        )


@router.post(
    "/{family_id}/invitations",
    response_model=FamilyInvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_family_invitation(
    family_id: int,
    data: FamilyInvitationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_inviter(db, current_user, family_id)
    family = db.query(Family).filter(Family.id == family_id).first()
    if family is None:
        raise HTTPException(status_code=404, detail="找不到指定家庭")

    email = _normalize_email(str(data.email))
    if email == _normalize_email(current_user.email):
        raise HTTPException(status_code=400, detail="不能邀請自己的 Email")

    target_user = db.query(User).filter(func.lower(User.email) == email).first()
    if target_user is not None:
        if not target_user.is_active:
            raise HTTPException(status_code=400, detail="受邀帳號已停用")
        active_member = db.query(FamilyMember).filter(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == target_user.id,
            FamilyMember.status == "active",
        ).first()
        if active_member is not None:
            raise HTTPException(status_code=409, detail="此使用者已是家庭成員")

    now = _utcnow()
    # 同一家庭、同一 Email 僅保留一筆有效待接受邀請。
    previous = db.query(FamilyInvitation).filter(
        FamilyInvitation.family_id == family_id,
        FamilyInvitation.email == email,
        FamilyInvitation.status == "pending",
    ).with_for_update().all()
    for item in previous:
        item.status = "revoked"
        item.revoked_at = now

    raw_token = secrets.token_urlsafe(32)
    invitation = FamilyInvitation(
        family_id=family_id,
        email=email,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        invited_by_user_id=current_user.id,
        status="pending",
        expires_at=now + timedelta(days=INVITATION_TTL_DAYS),
    )
    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="建立邀請時發生資料衝突，請重新操作") from exc

    public_app_url = os.getenv("PUBLIC_APP_URL", "https://family-finance-web-grst.onrender.com").rstrip("/")
    invite_url = _build_invite_url(public_app_url, raw_token)
    return FamilyInvitationCreateResponse(
        success=True,
        invitation_id=invitation.id,
        family_id=family_id,
        email=email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        invite_url=invite_url,
    )


@router.get("/{family_id}/invitations")
def list_family_invitations(
    family_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_inviter(db, current_user, family_id)
    rows = (
        db.query(FamilyInvitation, User.display_name)
        .join(User, User.id == FamilyInvitation.invited_by_user_id)
        .filter(
            FamilyInvitation.family_id == family_id,
            FamilyInvitation.status == "pending",
            FamilyInvitation.expires_at > _utcnow(),
        )
        .order_by(FamilyInvitation.created_at.desc(), FamilyInvitation.id.desc())
        .all()
    )
    return {
        "success": True,
        "invitations": [
            {
                "invitation_id": item.id,
                "email": item.email,
                "status": item.status,
                "invited_by": display_name,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "expires_at": item.expires_at.isoformat(),
            }
            for item, display_name in rows
        ],
    }


@router.delete("/{family_id}/invitations/{invitation_id}")
def revoke_family_invitation(
    family_id: int,
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_inviter(db, current_user, family_id)
    invitation = db.query(FamilyInvitation).filter(
        FamilyInvitation.id == invitation_id,
        FamilyInvitation.family_id == family_id,
        FamilyInvitation.status == "pending",
    ).with_for_update().first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="找不到有效的待接受邀請")
    invitation.status = "revoked"
    invitation.revoked_at = _utcnow()
    db.commit()
    return {"success": True, "message": "邀請已撤銷"}


@router.get("/invitations/mine")
def list_my_family_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="此帳號已停用")
    email = _normalize_email(current_user.email)
    _require_verified_google_email(db, current_user, email)
    rows = (
        db.query(FamilyInvitation, Family.name, User.display_name)
        .join(Family, Family.id == FamilyInvitation.family_id)
        .join(User, User.id == FamilyInvitation.invited_by_user_id)
        .filter(
            FamilyInvitation.email == email,
            FamilyInvitation.status == "pending",
            FamilyInvitation.expires_at > _utcnow(),
        )
        .order_by(FamilyInvitation.created_at.desc(), FamilyInvitation.id.desc())
        .all()
    )
    return {
        "success": True,
        "invitations": [
            {
                "invitation_id": item.id,
                "family_id": item.family_id,
                "family_name": family_name,
                "invited_by": inviter_name,
                "expires_at": item.expires_at.isoformat(),
            }
            for item, family_name, inviter_name in rows
        ],
    }


def _get_invitation_for_user(db: Session, raw_token: str, user: User) -> FamilyInvitation:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation = db.query(FamilyInvitation).filter(
        FamilyInvitation.token_hash == token_hash,
    ).with_for_update().first()
    if invitation is None or invitation.status != "pending":
        raise HTTPException(status_code=404, detail="邀請連結無效、已使用或已撤銷")
    if invitation.expires_at <= _utcnow():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="邀請連結已過期，請請管理員重新邀請")
    email = _normalize_email(user.email)
    if email != invitation.email:
        raise HTTPException(status_code=403, detail="目前登入的 Google Email 與受邀 Email 不一致")
    _require_verified_google_email(db, user, email)
    return invitation


def _join_family(db: Session, invitation: FamilyInvitation, user: User) -> int:
    family_id = invitation.family_id
    member = db.query(FamilyMember).filter(
        FamilyMember.family_id == family_id,
        FamilyMember.user_id == user.id,
    ).with_for_update().first()
    if member is not None and member.status == "active":
        raise HTTPException(status_code=409, detail="你已經是此家庭的有效成員")

    default_role = db.query(Role).filter(
        Role.family_id == family_id,
        Role.name == "一般成員",
        Role.is_system.is_(True),
        Role.is_active.is_(True),
    ).first()
    if default_role is None:
        raise HTTPException(status_code=500, detail="家庭一般成員角色尚未初始化，請聯絡系統管理員")

    if member is None:
        member = FamilyMember(family_id=family_id, user_id=user.id, status="active")
        db.add(member)
        db.flush()
    else:
        member.status = "active"
        member.left_at = None
        db.query(MemberRole).filter(
            MemberRole.family_member_id == member.id,
            MemberRole.family_id == family_id,
        ).delete(synchronize_session=False)

    db.add(MemberRole(
        family_member_id=member.id,
        role_id=default_role.id,
        family_id=family_id,
    ))
    return member.id


@router.post("/invitations/accept", response_model=FamilyInvitationActionResponse)
def accept_family_invitation(
    data: FamilyInvitationAccept,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="此帳號已停用")
    try:
        invitation = _get_invitation_for_user(db, data.token, current_user)
        family_member_id = _join_family(db, invitation, current_user)
        invitation.status = "accepted"
        invitation.accepted_by_user_id = current_user.id
        invitation.accepted_at = _utcnow()
        db.commit()
        return FamilyInvitationActionResponse(
            success=True,
            message="已成功加入家庭",
            family_id=invitation.family_id,
            family_member_id=family_member_id,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post("/invitations/decline", response_model=FamilyInvitationActionResponse)
def decline_family_invitation(
    data: FamilyInvitationAccept,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="此帳號已停用")
    try:
        invitation = _get_invitation_for_user(db, data.token, current_user)
        invitation.status = "declined"
        invitation.declined_at = _utcnow()
        db.commit()
        return FamilyInvitationActionResponse(success=True, message="已拒絕家庭邀請")
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
