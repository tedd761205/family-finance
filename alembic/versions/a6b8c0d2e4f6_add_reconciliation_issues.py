"""add reconciliation issue classification and resolution history

Revision ID: a6b8c0d2e4f6
Revises: f4a6c8d0e2b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a6b8c0d2e4f6"
down_revision: Union[str, Sequence[str], None] = "f4a6c8d0e2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_import_row_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("resolution_note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id", "session_id"],
            ["reconciliation_sessions.family_id", "reconciliation_sessions.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_session",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "batch_id", "bank_import_row_id"],
            ["bank_import_rows.family_id", "bank_import_rows.batch_id", "bank_import_rows.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_bank_row",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "account_id", "transaction_id"],
            ["transactions.family_id", "transactions.account_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_reconciliation_issues_transaction",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT",
                                name="fk_reconciliation_issues_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT",
                                name="fk_reconciliation_issues_updated_by"),
        sa.CheckConstraint(
            "category IN ('bank_only','ledger_only','amount_mismatch','date_mismatch','pending','explained')",
            name="ck_reconciliation_issues_category",
        ),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_reconciliation_issues_status"),
        sa.CheckConstraint(
            "bank_import_row_id IS NOT NULL OR transaction_id IS NOT NULL",
            name="ck_reconciliation_issues_source_required",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND length(trim(resolution_note)) > 0)",
            name="ck_reconciliation_issues_resolution",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_reconciliation_issues_reason"),
    )
    op.create_index(
        "ix_reconciliation_issues_session_status", "reconciliation_issues",
        ["family_id", "session_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_issues_session_status", table_name="reconciliation_issues")
    op.drop_table("reconciliation_issues")
