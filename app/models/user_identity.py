
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserIdentity(Base):
    """使用者外部登入身分，例如 Google"""

    __tablename__ = "user_identities"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_user_identities_provider_subject",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # 登入來源，例如 google
    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # 外部平台提供的唯一使用者識別碼
    # Google 使用 Google ID Token 中的 sub
    provider_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 外部平台提供的 Email
    # 不作為外部身分的唯一識別依據
    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return (
            f"<UserIdentity("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"provider={self.provider})>"
        )
