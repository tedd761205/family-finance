
"""
家庭記帳系統：功能權限初始化

功能：
1. 將系統權限清單寫入 permissions 資料表。
2. 已存在的權限不重複新增。
3. 更新既有權限的名稱、說明及分類。
4. 不刪除既有權限。
5. 不修改既有權限的啟用狀態。
"""

from app.database import SessionLocal
from app.models.permission import Permission
from app.permission_catalog import PERMISSION_CATALOG


def seed_permissions():
    if SessionLocal is None:
        raise RuntimeError(
            "資料庫尚未設定，請確認 DATABASE_URL"
        )

    db = SessionLocal()

    created_count = 0
    updated_count = 0

    try:
        # 檢查權限代碼是否重複
        codes = [
            item["code"]
            for item in PERMISSION_CATALOG
        ]

        if len(codes) != len(set(codes)):
            raise ValueError(
                "權限清單存在重複的 code"
            )

        # 取得目前資料庫已有的權限
        existing_permissions = {
            permission.code: permission
            for permission in db.query(Permission).all()
        }

        for item in PERMISSION_CATALOG:
            permission = existing_permissions.get(
                item["code"]
            )

            if permission is None:
                # 新增尚未存在的權限
                permission = Permission(
                    code=item["code"],
                    name=item["name"],
                    description=item["description"],
                    category=item["category"],
                )

                db.add(permission)
                created_count += 1

            else:
                # 更新既有權限的基本資料
                permission.name = item["name"]
                permission.description = item["description"]
                permission.category = item["category"]

                updated_count += 1

        # 全部完成後一次提交
        db.commit()

        print("權限初始化成功！")
        print(f"本次新增：{created_count} 項")
        print(f"本次更新：{updated_count} 項")
        print(
            f"權限清單總數：{len(PERMISSION_CATALOG)} 項"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_permissions()
