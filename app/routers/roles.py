"""家庭角色、細項權限與成員角色指派 API。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    get_active_family_member,
    get_active_family_roles,
    require_permission,
)
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.member_role import MemberRole
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_data_scope import RoleDataScope
from app.models.role_permission import RolePermission
from app.models.user import User
from app.permission_catalog import PERMISSION_CATALOG
from app.services.audit_log import add_audit_log
from app.schemas.roles import MemberRoleAssignment, RoleWrite

router = APIRouter(prefix="/families", tags=["Family Roles"])
ADMIN_ROLE_NAME = "家庭管理員"


def _authorize(db: Session, user_id: int, family_id: int, code: str):
    try:
        _, roles = require_permission(
            db=db, user_id=user_id, family_id=family_id,
            permission_code=code,
        )
        return roles
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _actor_permission_codes(db: Session, roles: list[Role]) -> set[str]:
    role_ids = [role.id for role in roles]
    if not role_ids:
        return set()
    rows = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(
            RolePermission.role_id.in_(role_ids),
            Permission.is_active.is_(True),
        )
        .all()
    )
    return {row[0] for row in rows}


def _validate_role_payload(db: Session, actor_codes: set[str], data: RoleWrite):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="角色名稱不可空白")
    if len(set(data.permission_codes)) != len(data.permission_codes):
        raise HTTPException(status_code=422, detail="權限清單不可重複")
    requested = set(data.permission_codes)
    known = {
        row.code for row in db.query(Permission).filter(Permission.is_active.is_(True)).all()
    }
    unknown = requested - known
    if unknown:
        raise HTTPException(status_code=422, detail="包含不存在或已停用的權限代碼")
    if not requested.issubset(actor_codes):
        raise HTTPException(
            status_code=403,
            detail="不可授予自己目前不具備的權限，避免權限升級",
        )
    categories = {item["category"] for item in PERMISSION_CATALOG}
    invalid_scopes = {
        resource: scope for resource, scope in data.data_scopes.items()
        if resource not in categories or scope not in {"own", "family"}
    }
    if invalid_scopes:
        raise HTTPException(status_code=422, detail="資料範圍只能設定在有效功能分類，且值必須是 own 或 family")
    if set(data.data_scopes) - {code.split(".", 1)[0] for code in requested}:
        raise HTTPException(status_code=422, detail="資料範圍只能設定於此角色已取得權限的功能分類")
    return name, requested


@router.get("/{family_id}/my-permissions")
def list_my_permissions(
    family_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """回傳目前登入者在指定家庭的有效權限，供前端顯示可用功能。"""
    try:
        family_member = get_active_family_member(
            db=db,
            user_id=current_user.id,
            family_id=family_id,
        )
        roles = get_active_family_roles(
            db=db,
            family_member_id=family_member.id,
            family_id=family_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "permission_codes": sorted(_actor_permission_codes(db, roles)),
    }


@router.get("/{family_id}/permissions")
def list_assignable_permissions(
    family_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = _authorize(db, current_user.id, family_id, "roles.view")
    grantable = _actor_permission_codes(db, roles)
    permissions = (
        db.query(Permission)
        .filter(Permission.is_active.is_(True))
        .order_by(Permission.category.asc(), Permission.code.asc())
        .all()
    )
    return {
        "success": True,
        "permissions": [
            {
                "code": item.code,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "grantable": item.code in grantable,
            }
            for item in permissions
        ],
    }


@router.get("/{family_id}/roles")
def list_family_roles(
    family_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "roles.view")
    roles = (
        db.query(Role)
        .filter(Role.family_id == family_id, Role.is_active.is_(True))
        .order_by(Role.is_system.desc(), Role.name.asc())
        .all()
    )
    result = []
    for role in roles:
        codes = [
            row[0] for row in (
                db.query(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role_id == role.id, Permission.is_active.is_(True))
                .order_by(Permission.code.asc()).all()
            )
        ]
        scopes = {
            row.resource: row.scope for row in
            db.query(RoleDataScope).filter(
                RoleDataScope.role_id == role.id,
                RoleDataScope.family_id == family_id,
            ).all()
        }
        assigned_count = (
            db.query(MemberRole)
            .join(FamilyMember, FamilyMember.id == MemberRole.family_member_id)
            .filter(
                MemberRole.role_id == role.id,
                MemberRole.family_id == family_id,
                FamilyMember.status == "active",
            ).count()
        )
        result.append({
            "id": role.id, "name": role.name, "description": role.description,
            "is_system": role.is_system, "permission_codes": codes,
            "data_scopes": scopes, "assigned_member_count": assigned_count,
        })
    return {"success": True, "roles": result}


@router.post("/{family_id}/roles", status_code=status.HTTP_201_CREATED)
def create_family_role(
    family_id: int,
    data: RoleWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = _authorize(db, current_user.id, family_id, "roles.create")
    actor_codes = _actor_permission_codes(db, roles)
    name, requested = _validate_role_payload(db, actor_codes, data)
    if db.query(Role).filter(Role.family_id == family_id, Role.name == name).first():
        raise HTTPException(status_code=409, detail="此家庭已有相同名稱的角色")
    role = Role(
        family_id=family_id, name=name,
        description=(data.description or "").strip() or None,
        is_system=False, is_active=True,
    )
    try:
        db.add(role)
        db.flush()
        permission_map = {
            item.code: item for item in db.query(Permission).filter(Permission.code.in_(requested)).all()
        }
        for code in requested:
            db.add(RolePermission(role_id=role.id, permission_id=permission_map[code].id))
        for resource, scope in data.data_scopes.items():
            db.add(RoleDataScope(role_id=role.id, family_id=family_id, resource=resource, scope=scope))
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="role.create", entity_type="role", entity_id=role.id,
            new_values={"name": name, "permission_codes": sorted(requested), "data_scopes": data.data_scopes},
            description="建立自訂角色",
        )
        db.commit()
        return {"success": True, "role_id": role.id, "name": role.name}
    except Exception:
        db.rollback()
        raise


@router.patch("/{family_id}/roles/{role_id}")
def update_family_role(
    family_id: int,
    role_id: int,
    data: RoleWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = _authorize(db, current_user.id, family_id, "roles.update")
    actor_codes = _actor_permission_codes(db, roles)
    name, requested = _validate_role_payload(db, actor_codes, data)
    role = db.query(Role).filter(
        Role.id == role_id, Role.family_id == family_id, Role.is_active.is_(True),
    ).with_for_update().first()
    if role is None:
        raise HTTPException(status_code=404, detail="找不到有效角色")
    if role.is_system:
        raise HTTPException(status_code=403, detail="系統預設角色受到保護，不可修改")
    duplicate = db.query(Role).filter(
        Role.family_id == family_id, Role.name == name, Role.id != role_id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="此家庭已有相同名稱的角色")
    old_codes = _actor_permission_codes(db, [role])
    old_scopes = {
        row.resource: row.scope for row in db.query(RoleDataScope).filter(
            RoleDataScope.role_id == role_id, RoleDataScope.family_id == family_id,
        ).all()
    }
    old_values = {
        "name": role.name, "description": role.description,
        "permission_codes": sorted(old_codes), "data_scopes": old_scopes,
    }
    try:
        role.name = name
        role.description = (data.description or "").strip() or None
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete(synchronize_session=False)
        permission_map = {
            item.code: item for item in db.query(Permission).filter(Permission.code.in_(requested)).all()
        }
        for code in requested:
            db.add(RolePermission(role_id=role_id, permission_id=permission_map[code].id))
        db.query(RoleDataScope).filter(
            RoleDataScope.role_id == role_id, RoleDataScope.family_id == family_id,
        ).delete(synchronize_session=False)
        for resource, scope in data.data_scopes.items():
            db.add(RoleDataScope(role_id=role_id, family_id=family_id, resource=resource, scope=scope))
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="role.update", entity_type="role", entity_id=role_id,
            old_values=old_values,
            new_values={"name": name, "description": role.description,
                        "permission_codes": sorted(requested), "data_scopes": data.data_scopes},
            description="修改自訂角色及權限",
        )
        db.commit()
        return {"success": True, "role_id": role_id, "name": role.name}
    except Exception:
        db.rollback()
        raise


@router.delete("/{family_id}/roles/{role_id}")
def void_family_role(
    family_id: int,
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize(db, current_user.id, family_id, "roles.void")
    role = db.query(Role).filter(
        Role.id == role_id, Role.family_id == family_id, Role.is_active.is_(True),
    ).with_for_update().first()
    if role is None:
        raise HTTPException(status_code=404, detail="找不到有效角色")
    if role.is_system:
        raise HTTPException(status_code=403, detail="系統預設角色受到保護，不可作廢")
    if db.query(MemberRole).filter(
        MemberRole.role_id == role_id, MemberRole.family_id == family_id,
    ).first():
        raise HTTPException(status_code=409, detail="此角色仍指派給家庭成員，請先調整成員角色")
    role.is_active = False
    add_audit_log(
        db, family_id=family_id, actor_user_id=current_user.id,
        action="role.void", entity_type="role", entity_id=role_id,
        old_values={"name": role.name, "is_active": True},
        new_values={"is_active": False},
        description="作廢未指派的自訂角色",
    )
    db.commit()
    return {"success": True, "message": "角色已作廢，歷史關聯保留"}


@router.put("/{family_id}/members/{family_member_id}/roles")
def assign_member_roles(
    family_id: int,
    family_member_id: int,
    data: MemberRoleAssignment,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    actor_roles = _authorize(db, current_user.id, family_id, "roles.assign")
    actor_codes = _actor_permission_codes(db, actor_roles)
    member = db.query(FamilyMember).filter(
        FamilyMember.id == family_member_id,
        FamilyMember.family_id == family_id,
        FamilyMember.status == "active",
    ).with_for_update().first()
    if member is None:
        raise HTTPException(status_code=404, detail="找不到有效家庭成員")
    if len(set(data.role_ids)) != len(data.role_ids):
        raise HTTPException(status_code=422, detail="角色清單不可重複")
    selected_roles = db.query(Role).filter(
        Role.id.in_(data.role_ids),
        Role.family_id == family_id,
        Role.is_active.is_(True),
    ).all()
    if len(selected_roles) != len(data.role_ids):
        raise HTTPException(status_code=422, detail="包含不存在、停用或不屬於此家庭的角色")
    for role in selected_roles:
        granted_codes = _actor_permission_codes(db, [role])
        if not granted_codes.issubset(actor_codes):
            raise HTTPException(status_code=403, detail=f"不可指派超出自己權限範圍的角色：{role.name}")
    admin_role = db.query(Role).filter(
        Role.family_id == family_id, Role.name == ADMIN_ROLE_NAME,
        Role.is_system.is_(True), Role.is_active.is_(True),
    ).first()
    includes_admin = bool(admin_role and any(role.id == admin_role.id for role in selected_roles))
    if not includes_admin:
        other_admins = (
            db.query(MemberRole)
            .join(FamilyMember, FamilyMember.id == MemberRole.family_member_id)
            .filter(
                MemberRole.family_id == family_id,
                MemberRole.role_id == admin_role.id if admin_role else -1,
                FamilyMember.status == "active",
                FamilyMember.id != family_member_id,
            ).count()
        )
        if other_admins == 0:
            raise HTTPException(status_code=409, detail="每個家庭至少必須保留一位家庭管理員")
    old_role_ids = [
        row[0] for row in db.query(MemberRole.role_id).filter(
            MemberRole.family_member_id == family_member_id,
            MemberRole.family_id == family_id,
        ).all()
    ]
    try:
        db.query(MemberRole).filter(
            MemberRole.family_member_id == family_member_id,
            MemberRole.family_id == family_id,
        ).delete(synchronize_session=False)
        for role in selected_roles:
            db.add(MemberRole(
                family_member_id=family_member_id, role_id=role.id, family_id=family_id,
            ))
        add_audit_log(
            db, family_id=family_id, actor_user_id=current_user.id,
            action="member.roles.update", entity_type="family_member",
            entity_id=family_member_id,
            old_values={"role_ids": sorted(old_role_ids)},
            new_values={"role_ids": sorted(data.role_ids)},
            description="調整家庭成員角色指派",
        )
        db.commit()
        return {"success": True, "family_member_id": family_member_id, "role_ids": data.role_ids}
    except Exception:
        db.rollback()
        raise
