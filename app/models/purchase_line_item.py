from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PurchaseLineItem(Base):
    """單筆支出交易底下的採買商品明細。"""

    __tablename__ = "purchase_line_items"

    __table_args__ = (
        ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            name="fk_purchase_line_items_family_transaction",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(btrim(item_name)) > 0",
            name="ck_purchase_line_items_item_name_not_blank",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_purchase_line_items_quantity_positive",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="ck_purchase_line_items_unit_price_nonnegative",
        ),
        CheckConstraint(
            "line_total >= 0",
            name="ck_purchase_line_items_line_total_nonnegative",
        ),
        UniqueConstraint(
            "family_id",
            "id",
            name="uq_purchase_line_items_family_id_id",
        ),
        Index(
            "ix_purchase_line_items_family_transaction",
            "family_id",
            "transaction_id",
            "sort_order",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    transaction_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    item_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    unit: Mapped[str | None] = mapped_column(
        String(24),
        nullable=True,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
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

    transaction = relationship(
        "Transaction",
        back_populates="purchase_items",
    )
