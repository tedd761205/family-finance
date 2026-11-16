
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Category(Base):
    """家庭收入與支出分類"""

    __tablename__ = "categories"

    __table_args__ = (
        Index(
            "ix_categories_family_id",
            "family_id",
        ),
        Index(
            "ix_categories_type",
            "category_type",
        ),
        UniqueConstraint(
            "family_id",
            "category_type",
            "name",
            name="uq_categories_family_type_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 所屬家庭；NULL 代表系統共用分類
    family_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=True,
    )

    # income / expense
    category_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # 分類名稱
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 上層分類 ID，支援多層分類
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 分類圖示
    icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # 分類顯示顏色
    color: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # 是否為系統預設分類
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # 是否啟用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # 排序
    sort_order: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )

    # 備註
    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
