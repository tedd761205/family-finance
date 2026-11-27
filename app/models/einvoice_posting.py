from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EInvoicePosting(Base):
    """家庭發票的正式支出入帳主檔；一張發票在同一家庭只能有一份入帳主檔。"""

    __tablename__ = "einvoice_postings"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_postings_family_id_id"),
        UniqueConstraint("family_id", "invoice_id", name="uq_einvoice_postings_family_invoice"),
        ForeignKeyConstraint(
            ["family_id", "invoice_id"],
            ["einvoices.family_id", "einvoices.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_postings_family_invoice",
        ),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_postings_family",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_postings_created_by",
        ),
        ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_postings_updated_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_postings_voided_by",
        ),
        CheckConstraint(
            "status IN ('unpaid', 'partially_paid', 'paid', 'voided')",
            name="ck_einvoice_postings_status",
        ),
        CheckConstraint("invoice_amount > 0", name="ck_einvoice_postings_amount_positive"),
        CheckConstraint(
            "invoice_currency_code ~ '^[A-Z]{3}$'",
            name="ck_einvoice_postings_currency_code",
        ),
        Index("ix_einvoice_postings_family_status", "family_id", "status"),
        Index("ix_einvoice_postings_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invoice_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    invoice_currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TWD", server_default="TWD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unpaid", server_default="unpaid")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EInvoicePayment(Base):
    """發票分次／多帳戶付款；每筆付款建立且只連結一筆正式帳戶支出交易。"""

    __tablename__ = "einvoice_payments"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_payments_family_id_id"),
        UniqueConstraint("family_id", "transaction_id", name="uq_einvoice_payments_family_transaction"),
        ForeignKeyConstraint(
            ["family_id", "posting_id"],
            ["einvoice_postings.family_id", "einvoice_postings.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_payments_family_posting",
        ),
        ForeignKeyConstraint(
            ["family_id", "account_id"],
            ["accounts.family_id", "accounts.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_payments_family_account",
        ),
        ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_payments_family_transaction",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_payments_created_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"],
            ondelete="RESTRICT",
            name="fk_einvoice_payments_voided_by",
        ),
        CheckConstraint(
            "(is_voided = false AND voided_at IS NULL AND voided_by IS NULL) OR "
            "(is_voided = true AND voided_at IS NOT NULL AND voided_by IS NOT NULL)",
            name="ck_einvoice_payments_void_metadata",
        ),
        CheckConstraint("amount > 0", name="ck_einvoice_payments_amount_positive"),
        CheckConstraint("account_amount > 0", name="ck_einvoice_payments_account_amount_positive"),
        CheckConstraint("exchange_rate > 0", name="ck_einvoice_payments_exchange_rate_positive"),
        CheckConstraint(
            "account_currency_code ~ '^[A-Z]{3}$'",
            name="ck_einvoice_payments_account_currency_code",
        ),
        CheckConstraint(
            "currency_code <> account_currency_code OR "
            "(exchange_rate = 1 AND account_amount = amount)",
            name="ck_einvoice_payments_same_currency_consistent",
        ),
        Index("ix_einvoice_payments_family_posting_date", "family_id", "posting_id", "payment_date"),
        Index("ix_einvoice_payments_family_account_date", "family_id", "account_id", "payment_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posting_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Amount applied to the Taiwan e-invoice, in invoice_currency_code (TWD).
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TWD", server_default="TWD")
    # Actual account-side debit in the selected account's currency.
    account_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    account_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # Number of account-currency units for one invoice-currency unit.
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=Decimal("1"), server_default="1")
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
