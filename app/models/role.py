
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(Base):
    """家庭角色設定"""

    __tablename__ = "roles"

    # 同一家庭內角色名稱不可重複
__table_args__ = (
    UniqueConstraint(
        "family_id",
        "name",
        name="uq_roles_family_name"
    ),
    UniqueConstraint(
        "id",
        "family_id",
        name="uq_roles_id_family"
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

    # 角色名稱
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # 角色說明
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # 是否為系統預設角色
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False
    )

    # 是否啟用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<Role("
            f"id={self.id}, "
            f"family_id={self.family_id}, "
            f"name={self.name})>"
        )
