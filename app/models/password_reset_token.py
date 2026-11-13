
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PasswordResetToken(Base):
    """使用者密碼重設 Token"""

    __tablename__ = "password_reset_tokens"

    # 資料編號
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # 密碼重設 Token 的 SHA-256 雜湊值
    # 不儲存原始 Token
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False
    )

    # Token 所屬使用者
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    # Token 到期時間
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Token 使用時間，尚未使用時為 None
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # 建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<PasswordResetToken("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"expires_at={self.expires_at})>"
        )
