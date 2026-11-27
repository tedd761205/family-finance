from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ElectronicInvoiceImportBatch(Base):
    """已保存的電子發票匯入批次；不保存載具號碼或原始 CSV。"""

    __tablename__ = "electronic_invoice_import_batches"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_batches_family_id_id"),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_einvoice_batches_family",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_batches_created_by",
        ),
        CheckConstraint("received_count > 0", name="ck_einvoice_batches_received_positive"),
        CheckConstraint("saved_count >= 0", name="ck_einvoice_batches_saved_nonnegative"),
        CheckConstraint("duplicate_count >= 0", name="ck_einvoice_batches_duplicate_nonnegative"),
        CheckConstraint(
            "saved_count + duplicate_count = received_count",
            name="ck_einvoice_batches_counts_consistent",
        ),
        Index("ix_einvoice_batches_family_created", "family_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    received_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    saved_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ElectronicInvoice(Base):
    """家庭已保存的電子發票表頭。"""

    __tablename__ = "electronic_invoices"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoices_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "import_batch_id"],
            ["electronic_invoice_import_batches.family_id", "electronic_invoice_import_batches.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_batch",
        ),
        ForeignKeyConstraint(
            ["family_id", "linked_transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_transaction",
        ),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_einvoices_family",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoices_created_by",
        ),
        ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoices_updated_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoices_voided_by",
        ),
        CheckConstraint("invoice_number ~ '^[A-Z]{2}[0-9]{8}$'", name="ck_einvoices_number_format"),
        CheckConstraint(
            "invoice_period ~ '^[0-9]{4}(02|04|06|08|10|12)$'",
            name="ck_einvoices_period_format",
        ),
        CheckConstraint(
            "merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'",
            name="ck_einvoices_tax_id_format",
        ),
        CheckConstraint("total_amount >= 0", name="ck_einvoices_total_nonnegative"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_einvoices_currency_format"),
        CheckConstraint(
            "validation_status IN ('matched', 'mismatch', 'missing_details', 'duplicate_in_file')",
            name="ck_einvoices_validation_status",
        ),
        Index("ix_einvoices_family_date", "family_id", "invoice_date", "id"),
        Index("ix_einvoices_family_number", "family_id", "invoice_number"),
        Index("ix_einvoices_family_period_number", "family_id", "invoice_period", "invoice_number"),
        Index(
            "uq_einvoices_family_period_number_active",
            "family_id",
            "invoice_period",
            "invoice_number",
            unique=True,
            postgresql_where=text("is_voided IS FALSE"),
        ),
        Index("ix_einvoices_family_merchant_date", "family_id", "merchant_name", "invoice_date"),
        Index("ix_einvoices_family_batch", "family_id", "import_batch_id"),
        Index("ix_einvoices_family_transaction", "family_id", "linked_transaction_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    import_batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_period: Mapped[str] = mapped_column(String(6), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(10), nullable=False)
    merchant_tax_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    detail_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    difference_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="TWD", server_default="TWD"
    )
    invoice_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    carrier_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    duplicate_in_source: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    linked_transaction_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ElectronicInvoiceItem(Base):
    """電子發票商品／折扣明細；負數折扣與零元品項均保留。"""

    __tablename__ = "electronic_invoice_items"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_items_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "invoice_id"],
            ["electronic_invoices.family_id", "electronic_invoices.id"],
            ondelete="RESTRICT", name="fk_einvoice_items_family_invoice",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_items_created_by",
        ),
        CheckConstraint("length(btrim(item_name)) > 0", name="ck_einvoice_items_name_not_blank"),
        CheckConstraint("sort_order >= 0", name="ck_einvoice_items_sort_order_nonnegative"),
        Index("ix_einvoice_items_family_invoice", "family_id", "invoice_id", "sort_order"),
        Index("ix_einvoice_items_family_name", "family_id", "item_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invoice_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
