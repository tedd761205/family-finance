
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
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
        Index(
            "ix_categories_parent_id",
            "parent_id",
        ),

        # 系統分類：全系統相同類型不可有重複名稱
        Index(
            "uq_categories_system_type_name",
            "category_type",
            "name",
            unique=True,
            postgresql_where=text("family_id IS NULL"),
        ),

        # 家庭分類：同一家庭、相同類型不可有重複名稱
        Index(
            "uq_categories_family_type_name",
            "family_id",
            "category_type",
            "name",
            unique=True,
            postgresql_where=text("family_id IS NOT NULL"),
        ),

        # 分類類型只能是收入或支出
        CheckConstraint(
            "category_type IN ('income', 'expense')",
            name="ck_categories_type",
        ),

        # 系統分類與家庭分類必須有正確的範圍標記
        CheckConstraint(
            """
            (family_id IS NULL AND is_system = true)
            OR
            (family_id IS NOT NULL AND is_system = false)
            """,
            name="ck_categories_system_scope",
        ),
    )

    # 分類 ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 所屬家庭
    # NULL 代表全系統共用分類
    family_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=True,
    )

    # 分類類型：income / expense
    category_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # 分類名稱
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 上層分類
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 圖示
    icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # 顏色
    color: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # 是否為系統分類
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

    # 建立者
    # 系統分類可以沒有建立者
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    # 建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 最後修改時間
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
