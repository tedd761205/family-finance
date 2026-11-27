"""add e-invoice posting and multiple account payments

Revision ID: e2f4a6b8c0d1
Revises: d1e3f5a7b9c2
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f4a6b8c0d1"
down_revision: Union[str, Sequence[str], None] = "d1e3f5a7b9c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "einvoice_postings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("invoice_currency_code", sa.String(3), server_default="TWD", nullable=False),
        sa.Column("status", sa.String(20), server_default="unpaid", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_postings_family_id_id"),
        sa.UniqueConstraint("family_id", "invoice_id", name="uq_einvoice_postings_family_invoice"),
        sa.ForeignKeyConstraint(
            ["family_id", "invoice_id"], ["einvoices.family_id", "einvoices.id"],
            ondelete="RESTRICT", name="fk_einvoice_postings_family_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_einvoice_postings_family",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_postings_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_postings_updated_by",
        ),
        sa.ForeignKeyConstraint(
            ["voided_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_postings_voided_by",
        ),
        sa.CheckConstraint(
            "status IN ('unpaid', 'partially_paid', 'paid', 'voided')",
            name="ck_einvoice_postings_status",
        ),
        sa.CheckConstraint("invoice_amount > 0", name="ck_einvoice_postings_amount_positive"),
        sa.CheckConstraint(
            "invoice_currency_code ~ '^[A-Z]{3}$'",
            name="ck_einvoice_postings_currency_code",
        ),
    )
    op.create_index("ix_einvoice_postings_family_status", "einvoice_postings", ["family_id", "status"])
    op.create_index("ix_einvoice_postings_created_by", "einvoice_postings", ["created_by"])

    op.create_table(
        "einvoice_payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("posting_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="TWD", nullable=False),
        sa.Column("account_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("account_currency_code", sa.String(3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(20, 10), server_default="1", nullable=False),
        sa.Column("payment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_payments_family_id_id"),
        sa.UniqueConstraint("family_id", "transaction_id", name="uq_einvoice_payments_family_transaction"),
        sa.ForeignKeyConstraint(
            ["family_id", "posting_id"],
            ["einvoice_postings.family_id", "einvoice_postings.id"],
            ondelete="RESTRICT", name="fk_einvoice_payments_family_posting",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "account_id"],
            ["accounts.family_id", "accounts.id"],
            ondelete="RESTRICT", name="fk_einvoice_payments_family_account",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_einvoice_payments_family_transaction",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_einvoice_payments_created_by",
        ),
        sa.CheckConstraint("amount > 0", name="ck_einvoice_payments_amount_positive"),
        sa.CheckConstraint("account_amount > 0", name="ck_einvoice_payments_account_amount_positive"),
        sa.CheckConstraint("exchange_rate > 0", name="ck_einvoice_payments_exchange_rate_positive"),
        sa.CheckConstraint(
            "account_currency_code ~ '^[A-Z]{3}$'",
            name="ck_einvoice_payments_account_currency_code",
        ),
        sa.CheckConstraint(
            "currency_code <> account_currency_code OR "
            "(exchange_rate = 1 AND account_amount = amount)",
            name="ck_einvoice_payments_same_currency_consistent",
        ),
    )
    op.create_index(
        "ix_einvoice_payments_family_posting_date",
        "einvoice_payments",
        ["family_id", "posting_id", "payment_date"],
    )
    op.create_index(
        "ix_einvoice_payments_family_account_date",
        "einvoice_payments",
        ["family_id", "account_id", "payment_date"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_payments = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM einvoice_payments)")
    ).scalar_one()
    has_postings = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM einvoice_postings)")
    ).scalar_one()
    if has_payments or has_postings:
        raise RuntimeError(
            "Cannot downgrade while invoice postings or account payment transactions exist; "
            "void/export and back up the posting records before removing these tables."
        )

    op.drop_index("ix_einvoice_payments_family_account_date", table_name="einvoice_payments")
    op.drop_index("ix_einvoice_payments_family_posting_date", table_name="einvoice_payments")
    op.drop_table("einvoice_payments")
    op.drop_index("ix_einvoice_postings_created_by", table_name="einvoice_postings")
    op.drop_index("ix_einvoice_postings_family_status", table_name="einvoice_postings")
    op.drop_table("einvoice_postings")
