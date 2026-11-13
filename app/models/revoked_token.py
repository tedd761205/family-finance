
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RevokedToken(Base):
    """已撤銷的登入 Token"""

    __tablename__ = "revoked_tokens"

    # 資料編號
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # JWT 的唯一識別碼，不儲存完整 Token
    jti: Mapped[str] = mapped_column(
        String(128),
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

    # Token 原本的到期時間
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # 撤銷時間
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # 建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<RevokedToken(id={self.id}, "
            f"user_id={self.user_id}, jti={self.jti})>"
        )
