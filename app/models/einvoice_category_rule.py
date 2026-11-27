from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EInvoiceCategoryRule(Base):
    """家庭發票品項分類規則；只保存店家／商品文字鍵，不保存載具資訊。"""

    __tablename__ = "einvoice_category_rules"
    __table_args__ = (
        UniqueConstraint(
            "family_id", "merchant_key", "item_name_key",
            name="uq_einvoice_category_rules_match",
        ),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_einvoice_category_rules_family",
        ),
        ForeignKeyConstraint(
            ["category_id"], ["categories.id"],
            name="fk_einvoice_category_rules_category",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_category_rules_created_by",
        ),
        ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_category_rules_updated_by",
        ),
        CheckConstraint("length(btrim(merchant_key)) > 0", name="ck_einvoice_category_rules_merchant_key"),
        CheckConstraint("length(btrim(item_name_key)) > 0", name="ck_einvoice_category_rules_item_key"),
        CheckConstraint(
            "merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'",
            name="ck_einvoice_category_rules_tax_id",
        ),
        Index("ix_einvoice_category_rules_family_active", "family_id", "is_active"),
        Index("ix_einvoice_category_rules_category", "family_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merchant_key: Mapped[str] = mapped_column(String(210), nullable=False)
    merchant_tax_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_name_key: Mapped[str] = mapped_column(String(200), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
