
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


class RoleDataScope(Base):
    __tablename__ = "role_data_scopes"

    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "resource",
            name="uq_role_data_scopes_role_resource",
        ),
        UniqueConstraint(
            "role_id",
            "family_id",
            name="uq_role_data_scopes_role_family",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resource: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="own",
        server_default="own",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
