from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillPayment(Base):
    """帳單付款／退款的不可變事件紀錄。"""

    __tablename__ = "bill_payments"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_bill_payments_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "bill_id"], ["bills.family_id", "bills.id"],
            ondelete="RESTRICT", name="fk_bill_payments_family_bill",
        ),
        ForeignKeyConstraint(
            ["family_id", "account_id"], ["accounts.family_id", "accounts.id"],
            ondelete="RESTRICT", name="fk_bill_payments_family_account",
        ),
        ForeignKeyConstraint(
            ["family_id", "original_payment_id"],
            ["bill_payments.family_id", "bill_payments.id"],
            ondelete="RESTRICT", name="fk_bill_payments_original_payment",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_bill_payments_created_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_bill_payments_voided_by",
        ),
        CheckConstraint("payment_type IN ('payment', 'refund')", name="ck_bill_payments_type"),
        CheckConstraint("amount > 0", name="ck_bill_payments_amount_positive"),
        CheckConstraint(
            "(payment_type = 'payment' AND original_payment_id IS NULL) OR "
            "(payment_type = 'refund' AND original_payment_id IS NOT NULL)",
            name="ck_bill_payments_original_payment_pair",
        ),
        Index("ix_bill_payments_family_bill_date", "family_id", "bill_id", "payment_date"),
        Index("ix_bill_payments_family_account_date", "family_id", "account_id", "payment_date"),
        Index("ix_bill_payments_original_payment", "family_id", "original_payment_id"),
        Index("ix_bill_payments_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_type: Mapped[str] = mapped_column(String(10), nullable=False)
    original_payment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
