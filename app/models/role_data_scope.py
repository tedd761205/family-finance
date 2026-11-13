
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
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
        ForeignKeyConstraint(
            ["role_id", "family_id"],
            ["roles.id", "roles.family_id"],
            ondelete="CASCADE",
            name="fk_role_data_scopes_role_family",
        ),
        CheckConstraint(
            "scope IN ('own', 'family')",
            name="ck_role_data_scopes_scope",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
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
