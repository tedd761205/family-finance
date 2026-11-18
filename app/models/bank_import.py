from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, JSON, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BankImportBatch(Base):
    """銀行／信用卡對帳單匯入批次；確認前只保存暫存資料。"""

    __tablename__ = "bank_import_batches"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_bank_import_batches_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "account_id"], ["accounts.family_id", "accounts.id"],
            ondelete="RESTRICT", name="fk_bank_import_batches_family_account",
        ),
        ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_bank_import_batches_family"),
        ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_bank_import_batches_created_by"),
        ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT", name="fk_bank_import_batches_confirmed_by"),
        CheckConstraint("status IN ('previewed','confirmed','cancelled')", name="ck_bank_import_batches_status"),
        CheckConstraint("total_rows >= 0 AND ready_rows >= 0 AND duplicate_rows >= 0 AND invalid_rows >= 0 AND imported_rows >= 0", name="ck_bank_import_batches_counts"),
        Index("ix_bank_import_batches_family_created", "family_id", "created_at"),
        Index("ix_bank_import_batches_account_created", "family_id", "account_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="previewed", server_default="previewed")
    column_mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    ready_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    duplicate_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    invalid_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    imported_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BankImportRow(Base):
    """單筆匯入暫存列；保留原始 CSV 欄位及解析結果。"""

    __tablename__ = "bank_import_rows"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_bank_import_rows_family_id_id"),
        UniqueConstraint("family_id", "batch_id", "row_number", name="uq_bank_import_rows_batch_row"),
        ForeignKeyConstraint(
            ["family_id", "batch_id"], ["bank_import_batches.family_id", "bank_import_batches.id"],
            ondelete="RESTRICT", name="fk_bank_import_rows_family_batch",
        ),
        ForeignKeyConstraint(
            ["family_id", "duplicate_of_row_id"], ["bank_import_rows.family_id", "bank_import_rows.id"],
            ondelete="RESTRICT", name="fk_bank_import_rows_duplicate",
        ),
        CheckConstraint("status IN ('ready','duplicate','invalid','imported','skipped')", name="ck_bank_import_rows_status"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_bank_import_rows_amount_positive"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_bank_import_rows_fingerprint"),
        Index("ix_bank_import_rows_family_batch_status", "family_id", "batch_id", "status"),
        Index("ix_bank_import_rows_family_account_fingerprint", "family_id", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duplicate_of_row_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
