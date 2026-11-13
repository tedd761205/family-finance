
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FamilyMember(Base):
    """家庭與使用者之間的成員關係"""

    __tablename__ = "family_members"

    # 同一家庭與使用者只能建立一筆成員關係
    __table_args__ = (
        UniqueConstraint(
            "family_id",
            "user_id",
            name="uq_family_members_family_user"
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

    # 對應使用者帳號
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # 成員狀態：active / invited / suspended / left
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False
    )

    # 加入家庭時間
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # 離開家庭時間
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    def __repr__(self):
        return (
            f"<FamilyMember("
            f"id={self.id}, "
            f"family_id={self.family_id}, "
            f"user_id={self.user_id})>"
        )
