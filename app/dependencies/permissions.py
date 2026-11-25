
"""
家庭記帳系統：共用權限檢查服務

負責：
1. 確認使用者帳號有效。
2. 確認使用者是有效的家庭成員。
3. 取得家庭成員擁有的有效角色。
4. 檢查角色是否具備指定功能權限。
5. 取得角色對指定資源的資料範圍（own / family）。

權限規則：
- 多角色採聯集：任一有效角色具有權限即可。
- 資料範圍採較廣範圍優先：family 優先於 own。
- 不允許跨家庭存取。
"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.family_member import FamilyMember
from app.models.member_role import MemberRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.permission import Permission
from app.models.role_data_scope import RoleDataScope


def get_active_family_member(
    db: Session,
    user_id: int,
    family_id: int,
) -> FamilyMember:
    """取得使用者在指定家庭的有效成員資料。"""

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise PermissionError("使用者帳號不存在或未啟用")

    family_member = (
        db.query(FamilyMember)
        .filter(
            FamilyMember.user_id == user_id,
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
        )
        .first()
    )

    if family_member is None:
        raise PermissionError("你不是此家庭的有效成員")

    return family_member


def get_active_family_roles(
    db: Session,
    family_member_id: int,
    family_id: int,
) -> list[Role]:
    """取得家庭成員被指派的所有有效角色。"""

    roles = (
        db.query(Role)
        .join(
            MemberRole,
            MemberRole.role_id == Role.id,
        )
        .filter(
            MemberRole.family_member_id == family_member_id,
            MemberRole.family_id == family_id,
            Role.family_id == family_id,
            Role.is_active.is_(True),
        )
        .all()
    )

    return roles


def has_permission(
    db: Session,
    roles: list[Role],
    permission_code: str,
) -> bool:
    """檢查任一有效角色是否具有指定權限。"""

    role_ids = [role.id for role in roles]

    if not role_ids:
        return False

    permission = (
        db.query(Permission)
        .filter(
            Permission.code == permission_code,
            Permission.is_active.is_(True),
        )
        .first()
    )

    if permission is None:
        return False

    assignment = (
        db.query(RolePermission)
        .filter(
            RolePermission.role_id.in_(role_ids),
            RolePermission.permission_id == permission.id,
        )
        .first()
    )

    return assignment is not None


def require_permission(
    db: Session,
    user_id: int,
    family_id: int,
    permission_code: str,
) -> tuple[FamilyMember, list[Role]]:
    """
    確認家庭成員有效，並檢查指定功能權限。

    成功：
        回傳家庭成員及有效角色。

    失敗：
        拋出 PermissionError。
    """

    family_member = get_active_family_member(
        db=db,
        user_id=user_id,
        family_id=family_id,
    )

    roles = get_active_family_roles(
        db=db,
        family_member_id=family_member.id,
        family_id=family_id,
    )

    if not has_permission(
        db=db,
        roles=roles,
        permission_code=permission_code,
    ):
        raise PermissionError(
            "目前帳號沒有執行此操作的權限"
        )

    return family_member, roles


def get_data_scope(
    db: Session,
    roles: list[Role],
    family_id: int,
    resource: str,
) -> str | None:
    """
    取得多個角色對指定資源的資料範圍。

    回傳：
        family：可查看整個家庭資料。
        own：只能查看自己建立的資料。
        None：沒有設定資料範圍。
    """

    role_ids = [role.id for role in roles]

    if not role_ids:
        return None

    scopes = (
        db.query(RoleDataScope.scope)
        .filter(
            RoleDataScope.role_id.in_(role_ids),
            RoleDataScope.family_id == family_id,
            RoleDataScope.resource == resource,
        )
        .all()
    )

    scope_values = {item[0] for item in scopes}

    if "family" in scope_values:
        return "family"

    if "own" in scope_values:
        return "own"

    return None


def require_data_scope(
    db: Session,
    roles: list[Role],
    family_id: int,
    resource: str,
) -> str:
    """取得資料範圍；沒有設定時拒絕存取。"""

    scope = get_data_scope(
        db=db,
        roles=roles,
        family_id=family_id,
        resource=resource,
    )

    if scope is None:
        raise PermissionError(
            "目前角色尚未設定此類資料的查看範圍"
        )

    return scope
