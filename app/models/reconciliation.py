from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Numeric, String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReconciliationSession(Base):
    """單一帳戶、單一對帳期間的銀行／信用卡核對工作階段。"""

    __tablename__ = "reconciliation_sessions"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_reconciliation_sessions_family_id_id"),
        UniqueConstraint("family_id", "id", "source_batch_id", name="uq_reconciliation_sessions_family_id_batch"),
        ForeignKeyConstraint(
            ["family_id", "account_id"], ["accounts.family_id", "accounts.id"],
            ondelete="RESTRICT", name="fk_reconciliation_sessions_family_account",
        ),
        ForeignKeyConstraint(
            ["family_id", "source_batch_id"], ["bank_import_batches.family_id", "bank_import_batches.id"],
            ondelete="RESTRICT", name="fk_reconciliation_sessions_family_batch",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_reconciliation_sessions_created_by",
        ),
        ForeignKeyConstraint(
            ["completed_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_reconciliation_sessions_completed_by",
        ),
        CheckConstraint(
            "period_start <= period_end", name="ck_reconciliation_sessions_period"
        ),
        CheckConstraint(
            "status IN ('draft','in_progress','completed','cancelled')",
            name="ck_reconciliation_sessions_status",
        ),
        CheckConstraint(
            "statement_row_count >= 0 AND matched_row_count >= 0 AND difference_row_count >= 0",
            name="ck_reconciliation_sessions_counts",
        ),
        Index(
            "uq_reconciliation_sessions_active_period",
            "family_id", "account_id", "period_start", "period_end",
            unique=True, postgresql_where=text("status <> 'cancelled'"),
        ),
        Index(
            "uq_reconciliation_sessions_source_batch",
            "family_id", "source_batch_id", unique=True,
            postgresql_where=text("source_batch_id IS NOT NULL"),
        ),
        Index("ix_reconciliation_sessions_family_status_period", "family_id", "status", "period_start"),
        Index("ix_reconciliation_sessions_account_period", "family_id", "account_id", "period_start", "period_end"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    opening_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    closing_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    statement_row_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    matched_row_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    difference_row_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ReconciliationMatch(Base):
    """銀行對帳列與正式交易之間的有效／作廢配對分配。"""

    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_reconciliation_matches_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "session_id", "batch_id"],
            ["reconciliation_sessions.family_id", "reconciliation_sessions.id", "reconciliation_sessions.source_batch_id"],
            ondelete="RESTRICT", name="fk_reconciliation_matches_family_session_batch",
        ),
        ForeignKeyConstraint(
            ["family_id", "batch_id", "bank_import_row_id"],
            ["bank_import_rows.family_id", "bank_import_rows.batch_id", "bank_import_rows.id"],
            ondelete="RESTRICT", name="fk_reconciliation_matches_family_import_row",
        ),
        ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_reconciliation_matches_family_transaction",
        ),
        ForeignKeyConstraint(
            ["matched_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_reconciliation_matches_matched_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"], ondelete="RESTRICT",
            name="fk_reconciliation_matches_voided_by",
        ),
        CheckConstraint("allocated_amount > 0", name="ck_reconciliation_matches_amount_positive"),
        CheckConstraint("status IN ('active','voided')", name="ck_reconciliation_matches_status"),
        CheckConstraint(
            "(status = 'active' AND voided_at IS NULL AND voided_by IS NULL) OR "
            "(status = 'voided' AND voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)",
            name="ck_reconciliation_matches_void_metadata",
        ),
        Index(
            "uq_reconciliation_matches_active_transaction",
            "family_id", "transaction_id", unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_reconciliation_matches_active_row_transaction",
            "family_id", "bank_import_row_id", "transaction_id", unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_reconciliation_matches_session_row", "family_id", "session_id", "bank_import_row_id", "status"),
        Index("ix_reconciliation_matches_transaction", "family_id", "transaction_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_import_row_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    matched_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
