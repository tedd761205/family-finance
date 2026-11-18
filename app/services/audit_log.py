"""
家庭記帳系統：共用 AuditLog 寫入服務

此服務只將紀錄加入目前 SQLAlchemy Session，不自行 commit，
確保操作資料與 AuditLog 能在同一個資料庫交易中成功或一起 rollback。
"""

from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def add_audit_log(
    db: Session,
    *,
    family_id: int,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    description: str | None = None,
) -> AuditLog:
    """
    將一筆操作紀錄加入目前 Session。

    注意：
    - 不在此處 commit 或 flush。
    - Decimal 以字串保留完整精度；日期時間等值由 jsonable_encoder 處理。
    - 呼叫端必須在原業務交易 commit 前呼叫本函式。
    - 不應傳入密碼、Token、連線字串或其他認證秘密。
    """

    log = AuditLog(
        family_id=family_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=(
            jsonable_encoder(old_values, custom_encoder={Decimal: str})
            if old_values is not None
            else None
        ),
        new_values=(
            jsonable_encoder(new_values, custom_encoder={Decimal: str})
            if new_values is not None
            else None
        ),
        description=description,
    )

    db.add(log)
    return log
