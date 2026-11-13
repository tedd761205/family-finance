
"""
家庭記帳系統：家庭預設角色初始化服務

負責：
1. 為指定家庭建立五種預設角色。
2. 建立角色與功能權限的關聯。
3. 建立角色的資料範圍設定。
4. 支援重複執行及同步更新。

注意：
本服務不自行 commit，由呼叫端負責交易提交。
"""

from sqlalchemy.orm import Session

from app.models.family import Family
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.role_data_scope import RoleDataScope

from app.role_catalog import DEFAULT_ROLES


def initialize_family_roles(
    db: Session,
    family_id: int,
) -> dict:
    """
    初始化指定家庭的五種預設角色。

    Args:
        db: SQLAlchemy 資料庫 Session
        family_id: 家庭 ID

    Returns:
        初始化結果統計

    注意：
        呼叫端必須在成功後 commit；
        發生錯誤時應 rollback。
    """

    # 1. 確認家庭存在
    family = db.get(Family, family_id)

    if family is None:
        raise ValueError(
            f"找不到家庭，family_id={family_id}"
        )

    # 2. 取得所有系統權限
    permissions = db.query(Permission).all()

    permission_map = {
        permission.code: permission
        for permission in permissions
    }

    # 3. 檢查角色所需權限是否完整
    required_codes = {
        code
        for role_config in DEFAULT_ROLES
        for code in role_config["permissions"]
    }

    missing_codes = sorted(
        required_codes - set(permission_map.keys())
    )

    if missing_codes:
        raise ValueError(
            "資料庫缺少以下系統權限："
            + ", ".join(missing_codes)
        )

    # 4. 初始化統計資料
    result = {
        "roles_created": 0,
        "roles_existing": 0,
        "permissions_created": 0,
        "scopes_created": 0,
    }

    # 5. 逐一建立或更新五種預設角色
    for role_config in DEFAULT_ROLES:

        role_name = role_config["name"]

        # 檢查同一家庭是否已有相同角色
        role = (
            db.query(Role)
            .filter(
                Role.family_id == family_id,
                Role.name == role_name,
            )
            .first()
        )

        if role is None:
            role = Role(
                family_id=family_id,
                name=role_name,
                description=role_config["description"],
                is_system=True,
                is_active=True,
            )

            db.add(role)
            db.flush()

            result["roles_created"] += 1

        else:
            # 更新系統角色基本資料
            role.description = role_config["description"]
            role.is_system = True
            role.is_active = True

            result["roles_existing"] += 1

        # 6. 同步角色功能權限
        desired_permission_ids = {
            permission_map[code].id
            for code in role_config["permissions"]
        }

        existing_role_permissions = (
            db.query(RolePermission)
            .filter(
                RolePermission.role_id == role.id
            )
            .all()
        )

        existing_permission_ids = {
            item.permission_id
            for item in existing_role_permissions
        }

        # 移除已不在預設清單中的權限
        for item in existing_role_permissions:
            if item.permission_id not in desired_permission_ids:
                db.delete(item)

        # 新增缺少的權限關聯
        for permission_id in desired_permission_ids:
            if permission_id not in existing_permission_ids:
                db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission_id,
                    )
                )

                result["permissions_created"] += 1

        # 7. 同步角色資料範圍
        desired_scopes = role_config["data_scopes"]

        existing_scopes = (
            db.query(RoleDataScope)
            .filter(
                RoleDataScope.role_id == role.id,
                RoleDataScope.family_id == family_id,
            )
            .all()
        )

        existing_scope_map = {
            item.resource: item
            for item in existing_scopes
        }

        # 移除已不在設定清單中的資料範圍
        for item in existing_scopes:
            if item.resource not in desired_scopes:
                db.delete(item)

        # 新增或更新資料範圍
        for resource, scope in desired_scopes.items():

            if scope not in ("own", "family"):
                raise ValueError(
                    f"不合法的資料範圍：{resource}={scope}"
                )

            existing_scope = existing_scope_map.get(
                resource
            )

            if existing_scope is None:
                db.add(
                    RoleDataScope(
                        role_id=role.id,
                        family_id=family_id,
                        resource=resource,
                        scope=scope,
                    )
                )

                result["scopes_created"] += 1

            else:
                existing_scope.scope = scope

    # 8. 將變更送入目前交易，但不自行 commit
    db.flush()

    return result
