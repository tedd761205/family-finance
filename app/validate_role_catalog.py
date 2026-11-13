
"""
家庭記帳系統：預設角色設定驗證

此程式只檢查設定，不連線資料庫，也不修改資料。
"""

from app.permission_catalog import PERMISSION_CATALOG
from app.role_catalog import DEFAULT_ROLES


def validate_role_catalog():

    errors = []

    # 1. 檢查系統權限清單
    permission_codes = [
        item["code"]
        for item in PERMISSION_CATALOG
    ]

    if len(permission_codes) != len(set(permission_codes)):
        errors.append("系統權限清單存在重複代碼")

    permission_code_set = set(permission_codes)

    # 2. 檢查預設角色數量
    if len(DEFAULT_ROLES) != 5:
        errors.append(
            f"預設角色應為 5 種，目前為 {len(DEFAULT_ROLES)} 種"
        )

    # 3. 檢查角色名稱
    role_names = [
        role["name"]
        for role in DEFAULT_ROLES
    ]

    if len(role_names) != len(set(role_names)):
        errors.append("預設角色名稱重複")

    # 4. 檢查各角色
    for role in DEFAULT_ROLES:

        role_name = role["name"]
        permissions = role["permissions"]
        data_scopes = role["data_scopes"]

        # 檢查角色權限重複
        if len(permissions) != len(set(permissions)):
            errors.append(
                f"{role_name}：存在重複的功能權限"
            )

        # 檢查不存在的權限
        missing = set(permissions) - permission_code_set

        if missing:
            errors.append(
                f"{role_name}：不存在的權限代碼 {sorted(missing)}"
            )

        # 取得角色擁有的功能分類
        role_categories = {
            code.split(".", 1)[0]
            for code in permissions
            if "." in code
        }

        # 檢查資料範圍
        for resource, scope in data_scopes.items():

            if scope not in ("own", "family"):
                errors.append(
                    f"{role_name}："
                    f"{resource} 的資料範圍不合法：{scope}"
                )

            if resource not in role_categories:
                errors.append(
                    f"{role_name}："
                    f"{resource} 設定了資料範圍，"
                    "但沒有對應的功能權限"
                )

        # 檢查系統角色標記
        if role.get("is_system") is not True:
            errors.append(
                f"{role_name}：預設角色必須是系統角色"
            )

    # 5. 顯示檢查結果
    if errors:
        print("角色設定驗證失敗！")

        for error in errors:
            print(f"- {error}")

        raise SystemExit(1)

    print("角色設定驗證成功！")
    print(f"系統權限數量：{len(permission_codes)}")
    print(f"預設角色數量：{len(DEFAULT_ROLES)}")

    for role in DEFAULT_ROLES:
        print(
            f"- {role['name']}："
            f"{len(role['permissions'])} 項功能權限，"
            f"{len(role['data_scopes'])} 項資料範圍"
        )


if __name__ == "__main__":
    validate_role_catalog()
