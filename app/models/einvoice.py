from datetime import datetime
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EInvoiceImportBatch(Base):
    """家庭電子發票匯入批次；保存來源摘要與匯入結果，不保存載具號碼或原始 CSV。"""

    __tablename__ = "einvoice_import_batches"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_import_batches_family_id_id"),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_einvoice_import_batches_family",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_import_batches_created_by",
        ),
        CheckConstraint(
            "status IN ('completed', 'completed_with_issues')",
            name="ck_einvoice_import_batches_status",
        ),
        CheckConstraint(
            "total_invoices >= 0 AND saved_invoices >= 0 AND duplicate_invoices >= 0 AND issue_invoices >= 0",
            name="ck_einvoice_import_batches_counts",
        ),
        CheckConstraint(
            "saved_invoices + duplicate_invoices <= total_invoices",
            name="ck_einvoice_import_batches_saved_duplicate_counts",
        ),
        CheckConstraint(
            "source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_einvoice_import_batches_source_sha256",
        ),
        Index("ix_einvoice_import_batches_family_created", "family_id", "created_at"),
        Index("ix_einvoice_import_batches_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed", server_default="completed")
    total_invoices: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    saved_invoices: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    duplicate_invoices: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    issue_invoices: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EInvoice(Base):
    """家庭電子發票主檔；不與正式收入／支出交易混為一筆。"""

    __tablename__ = "einvoices"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoices_family_id_id"),
        UniqueConstraint("family_id", "invoice_number", name="uq_einvoices_family_invoice_number"),
        ForeignKeyConstraint(
            ["family_id", "import_batch_id"],
            ["einvoice_import_batches.family_id", "einvoice_import_batches.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_import_batch",
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
        CheckConstraint(
            "invoice_number ~ '^[A-Z]{2}[0-9]{8}$'",
            name="ck_einvoices_invoice_number",
        ),
        CheckConstraint(
            "merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'",
            name="ck_einvoices_merchant_tax_id",
        ),
        CheckConstraint("total_amount >= 0", name="ck_einvoices_total_amount_nonnegative"),
        CheckConstraint(
            "verification_status IN ('matched', 'mismatch', 'missing_details', 'duplicate')",
            name="ck_einvoices_verification_status",
        ),
        Index("ix_einvoices_family_date", "family_id", "invoice_date"),
        Index("ix_einvoices_family_merchant", "family_id", "merchant_name"),
        Index("ix_einvoices_family_tax_id", "family_id", "merchant_tax_id"),
        Index("ix_einvoices_family_created_by", "family_id", "created_by"),
        Index("ix_einvoices_import_batch", "family_id", "import_batch_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    import_batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(10), nullable=False)
    invoice_date: Mapped[object] = mapped_column(Date, nullable=False)
    merchant_tax_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    invoice_status: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    carrier_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detail_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0"), server_default="0")
    difference_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=Decimal("0"), server_default="0")
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EInvoiceItem(Base):
    """電子發票商品／折扣明細；允許負數折扣及零元品項。"""

    __tablename__ = "einvoice_items"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_einvoice_items_family_id_id"),
        UniqueConstraint("family_id", "invoice_id", "line_number", name="uq_einvoice_items_invoice_line"),
        ForeignKeyConstraint(
            ["family_id", "invoice_id"],
            ["einvoices.family_id", "einvoices.id"],
            ondelete="RESTRICT", name="fk_einvoice_items_family_invoice",
        ),
        CheckConstraint("length(btrim(item_name)) > 0", name="ck_einvoice_items_item_name_not_blank"),
        CheckConstraint("line_number > 0", name="ck_einvoice_items_line_number_positive"),
        Index("ix_einvoice_items_family_invoice", "family_id", "invoice_id", "line_number"),
        Index("ix_einvoice_items_family_name", "family_id", "item_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invoice_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    source_line_number: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
