
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    ForeignKey,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MemberRole(Base):
    """家庭成員與角色關聯"""

    __tablename__ = "member_roles"

    __table_args__ = (
        # 確保成員與角色屬於同一個家庭
        ForeignKeyConstraint(
            ["family_member_id", "family_id"],
            ["family_members.id", "family_members.family_id"],
            name="fk_member_roles_family_member"
        ),
        ForeignKeyConstraint(
            ["role_id", "family_id"],
            ["roles.id", "roles.family_id"],
            name="fk_member_roles_role"
        ),
    )

    family_member_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<MemberRole("
            f"family_member_id={self.family_member_id}, "
            f"role_id={self.role_id}, "
            f"family_id={self.family_id})>"
        )
