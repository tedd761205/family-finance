
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """系統操作歷程紀錄"""

    __tablename__ = "audit_logs"

    __table_args__ = (
        Index(
            "ix_audit_logs_family_created",
            "family_id",
            "created_at"
        ),
        Index(
            "ix_audit_logs_entity",
            "entity_type",
            "entity_id"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # 所屬家庭
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # 執行操作的使用者
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # 操作類型：create / update / void / login 等
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # 被操作的資料表或資料類型
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # 被操作資料的編號
    entity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True
    )

    # 修改前的資料
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )

    # 修改後的資料
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )

    # 操作說明
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    # 操作時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<AuditLog("
            f"id={self.id}, "
            f"action={self.action}, "
            f"entity_type={self.entity_type}, "
            f"entity_id={self.entity_id})>"
        )
