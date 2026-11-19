"""add reconciliation exclusion history and counters

Revision ID: f4a6c8d0e2b4
Revises: d3e5f7a9b1c3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f4a6c8d0e2b4"
down_revision: Union[str, Sequence[str], None] = "d3e5f7a9b1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_sessions",
        sa.Column("excluded_row_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "reconciliation_exclusions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_import_row_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("family_id", "id", name="uq_reconciliation_exclusions_family_id_id"),
        sa.ForeignKeyConstraint(
            ["family_id", "session_id", "account_id", "batch_id"],
            ["reconciliation_sessions.family_id", "reconciliation_sessions.id", "reconciliation_sessions.account_id", "reconciliation_sessions.source_batch_id"],
            ondelete="RESTRICT", name="fk_reconciliation_exclusions_session",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "batch_id", "bank_import_row_id"],
            ["bank_import_rows.family_id", "bank_import_rows.batch_id", "bank_import_rows.id"],
            ondelete="RESTRICT", name="fk_reconciliation_exclusions_import_row",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT",
                                name="fk_reconciliation_exclusions_created_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT",
                                name="fk_reconciliation_exclusions_voided_by"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_reconciliation_exclusions_status"),
        sa.CheckConstraint(
            "(status = 'active' AND voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR "
            "(status = 'voided' AND voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)",
            name="ck_reconciliation_exclusions_void_metadata",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_reconciliation_exclusions_reason"),
    )
    op.create_index(
        "uq_reconciliation_exclusions_active_row", "reconciliation_exclusions",
        ["family_id", "session_id", "bank_import_row_id"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_reconciliation_exclusions_session_status", "reconciliation_exclusions",
        ["family_id", "session_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_exclusions_session_status", table_name="reconciliation_exclusions")
    op.drop_index("uq_reconciliation_exclusions_active_row", table_name="reconciliation_exclusions")
    op.drop_table("reconciliation_exclusions")
    op.drop_column("reconciliation_sessions", "excluded_row_count")
