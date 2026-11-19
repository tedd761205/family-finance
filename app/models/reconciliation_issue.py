from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index,
    String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReconciliationIssue(Base):
    """人工分類及追蹤對帳差異；不修改銀行原始列或正式交易。"""

    __tablename__ = "reconciliation_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_id", "session_id"],
            ["reconciliation_sessions.family_id", "reconciliation_sessions.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_session",
        ),
        ForeignKeyConstraint(
            ["family_id", "batch_id", "bank_import_row_id"],
            ["bank_import_rows.family_id", "bank_import_rows.batch_id", "bank_import_rows.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_bank_row",
        ),
        ForeignKeyConstraint(
            ["family_id", "account_id", "transaction_id"],
            ["transactions.family_id", "transactions.account_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_transaction",
        ),
        ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT",
                             name="fk_reconciliation_issues_created_by"),
        ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT",
                             name="fk_reconciliation_issues_updated_by"),
        CheckConstraint(
            "category IN ('bank_only','ledger_only','amount_mismatch','date_mismatch','pending','explained')",
            name="ck_reconciliation_issues_category",
        ),
        CheckConstraint("status IN ('open','resolved')", name="ck_reconciliation_issues_status"),
        CheckConstraint(
            "bank_import_row_id IS NOT NULL OR transaction_id IS NOT NULL",
            name="ck_reconciliation_issues_source_required",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND length(trim(resolution_note)) > 0)",
            name="ck_reconciliation_issues_resolution",
        ),
        CheckConstraint("length(trim(reason)) > 0", name="ck_reconciliation_issues_reason"),
        Index("ix_reconciliation_issues_session_status",
              "family_id", "session_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_import_row_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
