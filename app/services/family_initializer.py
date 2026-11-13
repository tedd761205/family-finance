
"""
家庭記帳系統：家庭初始化服務

負責：
1. 確認建立者帳號存在且已啟用。
2. 建立家庭。
3. 將建立者加入家庭。
4. 初始化五種預設角色。
5. 自動指派家庭管理員角色。
6. 確保所有操作都在同一個資料庫交易中。

注意：
本服務不自行 commit，由呼叫端負責 commit。
發生錯誤時，本服務會 rollback。
"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.role import Role
from app.models.member_role import MemberRole

from app.services.role_initializer import initialize_family_roles


ADMIN_ROLE_NAME = "家庭管理員"


def create_family_with_admin(
    db: Session,
    user_id: int,
    family_name: str,
    currency: str = "TWD",
) -> dict:
    """
    建立家庭，並將建立者設定為家庭管理員。

    Args:
        db: SQLAlchemy Session
        user_id: 已登入使用者的資料庫 ID
        family_name: 家庭名稱
        currency: 家庭預設幣別，預設 TWD

    Returns:
        新家庭及管理員資訊

    注意：
        呼叫端必須在成功後 commit。
        發生錯誤時會 rollback。
    """

    try:
        # 1. 檢查家庭名稱
        family_name = (family_name or "").strip()

        if not family_name:
            raise ValueError("家庭名稱不可空白")

        if len(family_name) > 100:
            raise ValueError("家庭名稱不可超過 100 個字")

        # 2. 檢查幣別
        currency = (currency or "").strip().upper()

        if len(currency) != 3:
            raise ValueError("幣別必須是三碼代碼，例如 TWD")

        # 3. 確認使用者存在且啟用
        user = db.get(User, user_id)

        if user is None:
            raise ValueError("找不到使用者帳號")

        if not user.is_active:
            raise ValueError("此使用者帳號目前未啟用")

        # 4. 建立家庭
        family = Family(
            name=family_name,
            currency=currency,
        )

        db.add(family)
        db.flush()

        # 5. 將建立者加入家庭
        family_member = FamilyMember(
            family_id=family.id,
            user_id=user.id,
            status="active",
        )

        db.add(family_member)
        db.flush()

        # 6. 初始化五種預設角色
        initialize_result = initialize_family_roles(
            db=db,
            family_id=family.id,
        )

        # 7. 找出目前家庭的管理員角色
        admin_role = (
            db.query(Role)
            .filter(
                Role.family_id == family.id,
                Role.name == ADMIN_ROLE_NAME,
                Role.is_system.is_(True),
                Role.is_active.is_(True),
            )
            .first()
        )

        if admin_role is None:
            raise ValueError(
                "家庭初始化失敗：找不到有效的家庭管理員角色"
            )

        # 8. 指派家庭管理員角色
        member_role = MemberRole(
            family_member_id=family_member.id,
            role_id=admin_role.id,
            family_id=family.id,
        )

        db.add(member_role)
        db.flush()

        # 9. 回傳結果，不自行 commit
        return {
            "success": True,
            "family_id": family.id,
            "family_name": family.name,
            "currency": family.currency,
            "family_member_id": family_member.id,
            "user_id": user.id,
            "admin_role_id": admin_role.id,
            "admin_role_name": admin_role.name,
            "role_initialization": initialize_result,
        }

    except Exception:
        # 任何步驟失敗，整個交易回滾
        db.rollback()
        raise
