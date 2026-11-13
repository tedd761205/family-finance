
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """系統使用者帳號"""

    __tablename__ = "users"

    # 使用者編號
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # 登入電子郵件
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False
    )

    # 密碼雜湊值，不儲存原始密碼
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # 顯示名稱
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    # 帳號是否啟用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # 建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # 最後修改時間
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
