"""persist family e-invoices, import batches and itemized details

Revision ID: c9e1a4b6d8f0
Revises: a8c4e2f6b1d3
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1a4b6d8f0"
down_revision: Union[str, Sequence[str], None] = "a8c4e2f6b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "einvoice_import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="completed", nullable=False),
        sa.Column("total_invoices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("saved_invoices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_invoices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("issue_invoices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_import_batches_family_id_id"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_einvoice_import_batches_family"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoice_import_batches_created_by"),
        sa.CheckConstraint("status IN ('completed', 'completed_with_issues')", name="ck_einvoice_import_batches_status"),
        sa.CheckConstraint(
            "total_invoices >= 0 AND saved_invoices >= 0 AND duplicate_invoices >= 0 AND issue_invoices >= 0",
            name="ck_einvoice_import_batches_counts",
        ),
        sa.CheckConstraint(
            "saved_invoices + duplicate_invoices <= total_invoices",
            name="ck_einvoice_import_batches_saved_duplicate_counts",
        ),
        sa.CheckConstraint(
            "source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_einvoice_import_batches_source_sha256",
        ),
    )
    op.create_index("ix_einvoice_import_batches_family_created", "einvoice_import_batches", ["family_id", "created_at"])
    op.create_index("ix_einvoice_import_batches_created_by", "einvoice_import_batches", ["created_by"])

    op.create_table(
        "einvoices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_number", sa.String(length=10), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("merchant_tax_id", sa.String(length=8), nullable=True),
        sa.Column("merchant_name", sa.String(length=200), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("invoice_status", sa.String(length=50), server_default="", nullable=False),
        sa.Column("carrier_type", sa.String(length=80), nullable=True),
        sa.Column("detail_total", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("difference_amount", sa.Numeric(20, 2), server_default="0", nullable=False),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoices_family_id_id"),
        sa.UniqueConstraint("family_id", "invoice_number", name="uq_einvoices_family_invoice_number"),
        sa.ForeignKeyConstraint(
            ["family_id", "import_batch_id"],
            ["einvoice_import_batches.family_id", "einvoice_import_batches.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_import_batch",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_updated_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_voided_by"),
        sa.CheckConstraint("invoice_number ~ '^[A-Z]{2}[0-9]{8}$'", name="ck_einvoices_invoice_number"),
        sa.CheckConstraint("merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'", name="ck_einvoices_merchant_tax_id"),
        sa.CheckConstraint("total_amount >= 0", name="ck_einvoices_total_amount_nonnegative"),
        sa.CheckConstraint(
            "verification_status IN ('matched', 'mismatch', 'missing_details', 'duplicate')",
            name="ck_einvoices_verification_status",
        ),
    )
    op.create_index("ix_einvoices_family_date", "einvoices", ["family_id", "invoice_date"])
    op.create_index("ix_einvoices_family_merchant", "einvoices", ["family_id", "merchant_name"])
    op.create_index("ix_einvoices_family_tax_id", "einvoices", ["family_id", "merchant_tax_id"])
    op.create_index("ix_einvoices_family_created_by", "einvoices", ["family_id", "created_by"])
    op.create_index("ix_einvoices_import_batch", "einvoices", ["family_id", "import_batch_id"])

    op.create_table(
        "einvoice_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("source_line_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_items_family_id_id"),
        sa.UniqueConstraint("family_id", "invoice_id", "line_number", name="uq_einvoice_items_invoice_line"),
        sa.ForeignKeyConstraint(
            ["family_id", "invoice_id"],
            ["einvoices.family_id", "einvoices.id"],
            ondelete="RESTRICT", name="fk_einvoice_items_family_invoice",
        ),
        sa.CheckConstraint("length(btrim(item_name)) > 0", name="ck_einvoice_items_item_name_not_blank"),
        sa.CheckConstraint("line_number > 0", name="ck_einvoice_items_line_number_positive"),
    )
    op.create_index("ix_einvoice_items_family_invoice", "einvoice_items", ["family_id", "invoice_id", "line_number"])
    op.create_index("ix_einvoice_items_family_name", "einvoice_items", ["family_id", "item_name"])


def downgrade() -> None:
    bind = op.get_bind()
    has_records = bind.execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM einvoice_items)
            OR EXISTS (SELECT 1 FROM einvoices)
            OR EXISTS (SELECT 1 FROM einvoice_import_batches)
    """)).scalar_one()
    if has_records:
        raise RuntimeError(
            "Cannot downgrade while saved family e-invoice records exist; "
            "export or back up the records before removing the e-invoice tables."
        )

    op.drop_index("ix_einvoice_items_family_name", table_name="einvoice_items")
    op.drop_index("ix_einvoice_items_family_invoice", table_name="einvoice_items")
    op.drop_table("einvoice_items")

    op.drop_index("ix_einvoices_import_batch", table_name="einvoices")
    op.drop_index("ix_einvoices_family_created_by", table_name="einvoices")
    op.drop_index("ix_einvoices_family_tax_id", table_name="einvoices")
    op.drop_index("ix_einvoices_family_merchant", table_name="einvoices")
    op.drop_index("ix_einvoices_family_date", table_name="einvoices")
    op.drop_table("einvoices")

    op.drop_index("ix_einvoice_import_batches_created_by", table_name="einvoice_import_batches")
    op.drop_index("ix_einvoice_import_batches_family_created", table_name="einvoice_import_batches")
    op.drop_table("einvoice_import_batches")
