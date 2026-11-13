
"""
家庭記帳系統：家庭預設角色初始化服務

負責：
1. 為指定家庭建立五種預設角色。
2. 建立角色與功能權限的關聯。
3. 建立角色的資料範圍設定。
4. 避免重複初始化覆蓋既有自訂設定。

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
    為指定家庭建立五種預設角色。

    已存在的系統角色不會被重新覆蓋，
    以保留家庭管理員自行調整的權限設定。

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

    # 5. 建立五種預設角色
    for role_config in DEFAULT_ROLES:

        role_name = role_config["name"]

        role = (
            db.query(Role)
            .filter(
                Role.family_id == family_id,
                Role.name == role_name,
            )
            .first()
        )

        # 已有角色時，不覆蓋既有設定
        if role is not None:

            if not role.is_system:
                raise ValueError(
                    f"角色名稱衝突：{role_name} "
                    "已被自訂角色使用，請先處理名稱衝突。"
                )

            result["roles_existing"] += 1
            continue

        # 6. 建立新角色
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

        # 7. 建立角色功能權限
        for code in role_config["permissions"]:

            permission = permission_map[code]

            db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                )
            )

            result["permissions_created"] += 1

        # 8. 建立角色資料範圍
        for resource, scope in role_config["data_scopes"].items():

            if scope not in ("own", "family"):
                raise ValueError(
                    f"不合法的資料範圍：{resource}={scope}"
                )

            db.add(
                RoleDataScope(
                    role_id=role.id,
                    family_id=family_id,
                    resource=resource,
                    scope=scope,
                )
            )

            result["scopes_created"] += 1

    # 9. 將變更送入目前交易，但不自行 commit
    db.flush()

    return result
