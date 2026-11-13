
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RolePermission(Base):
    """角色與功能權限關聯"""

    __tablename__ = "role_permissions"

    # 角色編號
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True
    )

    # 權限編號
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True
    )

    # 授權建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<RolePermission("
            f"role_id={self.role_id}, "
            f"permission_id={self.permission_id})>"
        )
