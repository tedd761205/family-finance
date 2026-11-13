
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MemberRole(Base):
    """家庭成員與角色關聯"""

    __tablename__ = "member_roles"

    # 家庭成員編號
    family_member_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("family_members.id", ondelete="CASCADE"),
        primary_key=True
    )

    # 角色編號
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True
    )

    # 指派角色的時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<MemberRole("
            f"family_member_id={self.family_member_id}, "
            f"role_id={self.role_id})>"
        )
