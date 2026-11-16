
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

        CheckConstraint(
            "category_type IN ('income', 'expense')",
            name="ck_categories_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    family_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=True,
    )

    category_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    color: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    sort_order: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )

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
