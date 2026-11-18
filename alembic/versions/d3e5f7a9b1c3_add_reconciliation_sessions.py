"""add reconciliation sessions and match allocations

Revision ID: d3e5f7a9b1c3
Revises: b8d1f4a6c9e2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e5f7a9b1c3"
down_revision: Union[str, Sequence[str], None] = "b8d1f4a6c9e2"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("reconciliation.exclude", "排除對帳明細", "將銀行明細標記為排除並保留原因", "reconciliation"),
    ("reconciliation.reopen", "重新開啟對帳", "重新開啟已完成的對帳工作階段", "reconciliation"),
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_bank_import_batches_family_account_id", "bank_import_batches",
        ["family_id", "account_id", "id"],
    )
    op.create_unique_constraint(
        "uq_transactions_family_account_id", "transactions",
        ["family_id", "account_id", "id"],
    )
    op.create_table(
        "reconciliation_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("source_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("opening_balance", sa.Numeric(20, 4), nullable=True),
        sa.Column("closing_balance", sa.Numeric(20, 4), nullable=True),
        sa.Column("statement_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matched_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("difference_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("completed_by", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_reconciliation_sessions_family_id_id"),
        sa.UniqueConstraint("family_id", "id", "account_id", "source_batch_id", name="uq_reconciliation_sessions_family_id_account_batch"),
        sa.ForeignKeyConstraint(["family_id", "account_id"], ["accounts.family_id", "accounts.id"], ondelete="RESTRICT", name="fk_reconciliation_sessions_family_account"),
        sa.ForeignKeyConstraint(["family_id", "account_id", "source_batch_id"], ["bank_import_batches.family_id", "bank_import_batches.account_id", "bank_import_batches.id"], ondelete="RESTRICT", name="fk_reconciliation_sessions_family_account_batch"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_reconciliation_sessions_created_by"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"], ondelete="RESTRICT", name="fk_reconciliation_sessions_completed_by"),
        sa.CheckConstraint("period_start <= period_end", name="ck_reconciliation_sessions_period"),
        sa.CheckConstraint("status IN ('draft','in_progress','completed','cancelled')", name="ck_reconciliation_sessions_status"),
        sa.CheckConstraint("statement_row_count >= 0 AND matched_row_count >= 0 AND difference_row_count >= 0", name="ck_reconciliation_sessions_counts"),
    )
    op.create_index(
        "uq_reconciliation_sessions_active_period", "reconciliation_sessions",
        ["family_id", "account_id", "period_start", "period_end"],
        unique=True, postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_index(
        "uq_reconciliation_sessions_source_batch", "reconciliation_sessions",
        ["family_id", "source_batch_id"], unique=True,
        postgresql_where=sa.text("source_batch_id IS NOT NULL"),
    )
    op.create_index("ix_reconciliation_sessions_family_status_period", "reconciliation_sessions", ["family_id", "status", "period_start"])
    op.create_index("ix_reconciliation_sessions_account_period", "reconciliation_sessions", ["family_id", "account_id", "period_start", "period_end"])

    op.create_unique_constraint(
        "uq_bank_import_rows_family_batch_id", "bank_import_rows",
        ["family_id", "batch_id", "id"],
    )

    op.create_table(
        "reconciliation_matches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("bank_import_row_id", sa.BigInteger(), nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("matched_by", sa.BigInteger(), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("family_id", "id", name="uq_reconciliation_matches_family_id_id"),
        sa.ForeignKeyConstraint(["family_id", "session_id", "account_id", "batch_id"], ["reconciliation_sessions.family_id", "reconciliation_sessions.id", "reconciliation_sessions.account_id", "reconciliation_sessions.source_batch_id"], ondelete="RESTRICT", name="fk_reconciliation_matches_family_session_account_batch"),
        sa.ForeignKeyConstraint(["family_id", "batch_id", "bank_import_row_id"], ["bank_import_rows.family_id", "bank_import_rows.batch_id", "bank_import_rows.id"], ondelete="RESTRICT", name="fk_reconciliation_matches_family_import_row"),
        sa.ForeignKeyConstraint(["family_id", "account_id", "transaction_id"], ["transactions.family_id", "transactions.account_id", "transactions.id"], ondelete="RESTRICT", name="fk_reconciliation_matches_family_account_transaction"),
        sa.ForeignKeyConstraint(["matched_by"], ["users.id"], ondelete="RESTRICT", name="fk_reconciliation_matches_matched_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_reconciliation_matches_voided_by"),
        sa.CheckConstraint("allocated_amount > 0", name="ck_reconciliation_matches_amount_positive"),
        sa.CheckConstraint("status IN ('active','voided')", name="ck_reconciliation_matches_status"),
        sa.CheckConstraint(
            "(status = 'active' AND voided_at IS NULL AND voided_by IS NULL) OR "
            "(status = 'voided' AND voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)",
            name="ck_reconciliation_matches_void_metadata",
        ),
    )
    op.create_index(
        "uq_reconciliation_matches_active_transaction", "reconciliation_matches",
        ["family_id", "transaction_id"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_reconciliation_matches_active_row_transaction", "reconciliation_matches",
        ["family_id", "bank_import_row_id", "transaction_id"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_reconciliation_matches_session_row", "reconciliation_matches", ["family_id", "session_id", "bank_import_row_id", "status"])
    op.create_index("ix_reconciliation_matches_transaction", "reconciliation_matches", ["family_id", "transaction_id", "status"])

    bind = op.get_bind()
    for code, name, description, category in PERMISSIONS:
        bind.execute(sa.text("""
            INSERT INTO permissions (code, name, description, category, is_active)
            VALUES (:code, :name, :description, :category, true)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name, description = EXCLUDED.description,
                category = EXCLUDED.category, is_active = true
        """), {"code": code, "name": name, "description": description, "category": category})

    role_permissions = {
        "家庭管理員": ("reconciliation.exclude", "reconciliation.reopen"),
        "財務管理員": ("reconciliation.exclude",),
        "記帳人員": ("reconciliation.exclude",),
    }
    for role_name, codes in role_permissions.items():
        for code in codes:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r JOIN permissions p ON p.code = :code
                WHERE r.name = :role_name AND r.is_system = true
                ON CONFLICT DO NOTHING
            """), {"role_name": role_name, "code": code})


def downgrade() -> None:
    op.drop_index("ix_reconciliation_matches_transaction", table_name="reconciliation_matches")
    op.drop_index("ix_reconciliation_matches_session_row", table_name="reconciliation_matches")
    op.drop_index("uq_reconciliation_matches_active_row_transaction", table_name="reconciliation_matches")
    op.drop_index("uq_reconciliation_matches_active_transaction", table_name="reconciliation_matches")
    op.drop_table("reconciliation_matches")
    op.drop_constraint("uq_bank_import_rows_family_batch_id", "bank_import_rows", type_="unique")

    op.drop_index("ix_reconciliation_sessions_account_period", table_name="reconciliation_sessions")
    op.drop_index("ix_reconciliation_sessions_family_status_period", table_name="reconciliation_sessions")
    op.drop_index("uq_reconciliation_sessions_source_batch", table_name="reconciliation_sessions")
    op.drop_index("uq_reconciliation_sessions_active_period", table_name="reconciliation_sessions")
    op.drop_table("reconciliation_sessions")
    op.drop_constraint("uq_transactions_family_account_id", "transactions", type_="unique")
    op.drop_constraint("uq_bank_import_batches_family_account_id", "bank_import_batches", type_="unique")

    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.is_system = true
          AND r.name IN ('家庭管理員', '財務管理員', '記帳人員')
          AND p.code IN ('reconciliation.exclude', 'reconciliation.reopen')
    """))
    bind.execute(sa.text("""
        DELETE FROM permissions p
        WHERE code IN ('reconciliation.exclude', 'reconciliation.reopen')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id
          )
    """))
