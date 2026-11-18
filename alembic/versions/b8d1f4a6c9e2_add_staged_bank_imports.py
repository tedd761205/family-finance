"""add staged bank statement imports

Revision ID: b8d1f4a6c9e2
Revises: a7c9e1f3b5d7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d1f4a6c9e2"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f3b5d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_import_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), server_default="previewed", nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ready_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_bank_import_batches_family_id_id"),
        sa.ForeignKeyConstraint(["family_id", "account_id"], ["accounts.family_id", "accounts.id"], ondelete="RESTRICT", name="fk_bank_import_batches_family_account"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_bank_import_batches_created_by"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT", name="fk_bank_import_batches_confirmed_by"),
        sa.CheckConstraint("status IN ('previewed','confirmed','cancelled')", name="ck_bank_import_batches_status"),
        sa.CheckConstraint("total_rows >= 0 AND ready_rows >= 0 AND duplicate_rows >= 0 AND invalid_rows >= 0 AND imported_rows >= 0", name="ck_bank_import_batches_counts"),
    )
    op.create_index("ix_bank_import_batches_family_created", "bank_import_batches", ["family_id", "created_at"])
    op.create_index("ix_bank_import_batches_account_created", "bank_import_batches", ["family_id", "account_id", "created_at"])

    op.create_table(
        "bank_import_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=True),
        sa.Column("amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("external_reference", sa.String(100), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duplicate_of_row_id", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_bank_import_rows_family_id_id"),
        sa.UniqueConstraint("family_id", "batch_id", "row_number", name="uq_bank_import_rows_batch_row"),
        sa.ForeignKeyConstraint(["family_id", "batch_id"], ["bank_import_batches.family_id", "bank_import_batches.id"], ondelete="RESTRICT", name="fk_bank_import_rows_family_batch"),
        sa.ForeignKeyConstraint(["family_id", "duplicate_of_row_id"], ["bank_import_rows.family_id", "bank_import_rows.id"], ondelete="RESTRICT", name="fk_bank_import_rows_duplicate"),
        sa.CheckConstraint("status IN ('ready','duplicate','invalid','imported','skipped')", name="ck_bank_import_rows_status"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_bank_import_rows_amount_positive"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="ck_bank_import_rows_fingerprint"),
    )
    op.create_index("ix_bank_import_rows_family_batch_status", "bank_import_rows", ["family_id", "batch_id", "status"])
    op.create_index("ix_bank_import_rows_family_account_fingerprint", "bank_import_rows", ["family_id", "fingerprint"])

    op.add_column("transactions", sa.Column("import_row_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_family_import_row",
        "transactions", "bank_import_rows",
        ["family_id", "import_row_id"], ["family_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_transactions_import_row_id", "transactions", ["import_row_id"],
        unique=True, postgresql_where=sa.text("import_row_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_transactions_import_row_id", table_name="transactions")
    op.drop_constraint("fk_transactions_family_import_row", "transactions", type_="foreignkey")
    op.drop_column("transactions", "import_row_id")
    op.drop_index("ix_bank_import_rows_family_account_fingerprint", table_name="bank_import_rows")
    op.drop_index("ix_bank_import_rows_family_batch_status", table_name="bank_import_rows")
    op.drop_table("bank_import_rows")
    op.drop_index("ix_bank_import_batches_account_created", table_name="bank_import_batches")
    op.drop_index("ix_bank_import_batches_family_created", table_name="bank_import_batches")
    op.drop_table("bank_import_batches")
