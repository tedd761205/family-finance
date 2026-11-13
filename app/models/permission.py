
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    String,
    Text,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Permission(Base):
    """系統功能權限定義"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # 權限代碼，例如 ledger.read.all
    code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    # 權限名稱，例如查看全家庭帳務
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # 權限功能說明
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # 權限所屬功能分類
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    # 是否啟用
    is_active: Mapped[bool] = mapped_column(
        default=True,
        server_default="true",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<Permission("
            f"id={self.id}, "
            f"code={self.code}, "
            f"name={self.name})>"
        )
