
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
    __tablename__ = "family_members"

    __table_args__ = (
        UniqueConstraint(
            "family_id",
            "user_id",
            name="uq_family_members_family_user"
        ),
        UniqueConstraint(
            "id",
            "family_id",
            name="uq_family_members_id_family"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
