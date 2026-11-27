"""persist family electronic invoice imports and history

Revision ID: b9c1d3e5f7a9
Revises: a8c4e2f6b1d3
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c1d3e5f7a9"
down_revision: Union[str, Sequence[str], None] = "a8c4e2f6b1d3"
branch_labels = None
depends_on = None


PERMISSIONS = (
    ("invoices.view", "查看發票", "查看家庭已保存的電子發票及商品明細", "invoices"),
    ("invoices.import", "匯入發票", "保存電子發票匯入批次及解析明細", "invoices"),
    ("invoices.void", "作廢發票紀錄", "作廢錯誤或重複的已保存發票紀錄並保留歷史", "invoices"),
)

ROLE_CODES = {
    "家庭管理員": ("invoices.view", "invoices.import", "invoices.void"),
    "財務管理員": ("invoices.view", "invoices.import", "invoices.void"),
    "一般成員": ("invoices.view", "invoices.import"),
    "記帳人員": ("invoices.view", "invoices.import", "invoices.void"),
    "檢視人員": ("invoices.view",),
}
ROLE_SCOPES = {
    "家庭管理員": "family",
    "財務管理員": "family",
    "一般成員": "own",
    "記帳人員": "family",
    "檢視人員": "family",
}


def upgrade() -> None:
    op.create_table(
        "electronic_invoice_import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("received_count", sa.BigInteger(), nullable=False),
        sa.Column("saved_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_einvoice_batches_family"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoice_batches_created_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_batches_family_id_id"),
        sa.CheckConstraint("received_count > 0", name="ck_einvoice_batches_received_positive"),
        sa.CheckConstraint("saved_count >= 0", name="ck_einvoice_batches_saved_nonnegative"),
        sa.CheckConstraint("duplicate_count >= 0", name="ck_einvoice_batches_duplicate_nonnegative"),
        sa.CheckConstraint(
            "saved_count + duplicate_count = received_count",
            name="ck_einvoice_batches_counts_consistent",
        ),
    )
    op.create_index(
        "ix_einvoice_batches_family_created",
        "electronic_invoice_import_batches",
        ["family_id", "created_at"],
    )

    op.create_table(
        "electronic_invoices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.String(length=10), nullable=False),
        sa.Column("merchant_tax_id", sa.String(length=8), nullable=True),
        sa.Column("merchant_name", sa.String(length=200), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("detail_total_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("difference_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency_code", sa.String(length=3), server_default="TWD", nullable=False),
        sa.Column("invoice_status", sa.String(length=60), nullable=True),
        sa.Column("carrier_type", sa.String(length=100), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("duplicate_in_source", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("linked_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id", "import_batch_id"],
            ["electronic_invoice_import_batches.family_id", "electronic_invoice_import_batches.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_batch",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "linked_transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_einvoices_family_transaction",
        ),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_einvoices_family"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_updated_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoices_voided_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoices_family_id_id"),
        sa.UniqueConstraint("family_id", "invoice_date", "invoice_number", name="uq_einvoices_family_date_number"),
        sa.CheckConstraint("invoice_number ~ '^[A-Z]{2}[0-9]{8}$'", name="ck_einvoices_number_format"),
        sa.CheckConstraint("merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'", name="ck_einvoices_tax_id_format"),
        sa.CheckConstraint("total_amount >= 0", name="ck_einvoices_total_nonnegative"),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_einvoices_currency_format"),
        sa.CheckConstraint(
            "validation_status IN ('matched', 'mismatch', 'missing_details', 'duplicate_in_file')",
            name="ck_einvoices_validation_status",
        ),
    )
    op.create_index("ix_einvoices_family_date", "electronic_invoices", ["family_id", "invoice_date", "id"])
    op.create_index("ix_einvoices_family_number", "electronic_invoices", ["family_id", "invoice_number"])
    op.create_index("ix_einvoices_family_merchant_date", "electronic_invoices", ["family_id", "merchant_name", "invoice_date"])
    op.create_index("ix_einvoices_family_batch", "electronic_invoices", ["family_id", "import_batch_id"])
    op.create_index("ix_einvoices_family_transaction", "electronic_invoices", ["family_id", "linked_transaction_id"])

    op.create_table(
        "electronic_invoice_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("sort_order", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id", "invoice_id"],
            ["electronic_invoices.family_id", "electronic_invoices.id"],
            ondelete="RESTRICT", name="fk_einvoice_items_family_invoice",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_einvoice_items_created_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_einvoice_items_family_id_id"),
        sa.CheckConstraint("length(btrim(item_name)) > 0", name="ck_einvoice_items_name_not_blank"),
        sa.CheckConstraint("sort_order >= 0", name="ck_einvoice_items_sort_order_nonnegative"),
    )
    op.create_index(
        "ix_einvoice_items_family_invoice",
        "electronic_invoice_items",
        ["family_id", "invoice_id", "sort_order"],
    )
    op.create_index(
        "ix_einvoice_items_family_name",
        "electronic_invoice_items",
        ["family_id", "item_name"],
    )

    bind = op.get_bind()
    for code, name, description, category in PERMISSIONS:
        bind.execute(
            sa.text("""
                INSERT INTO permissions (code, name, description, category, is_active)
                VALUES (:code, :name, :description, :category, true)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    is_active = true
            """),
            {"code": code, "name": name, "description": description, "category": category},
        )

    for role_name, codes in ROLE_CODES.items():
        for code in codes:
            bind.execute(
                sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                    FROM roles r
                    JOIN permissions p ON p.code = :code
                    WHERE r.name = :role_name AND r.is_system = true
                    ON CONFLICT DO NOTHING
                """),
                {"role_name": role_name, "code": code},
            )

        bind.execute(
            sa.text("""
                INSERT INTO role_data_scopes (role_id, family_id, resource, scope)
                SELECT id, family_id, 'invoices', :scope
                FROM roles
                WHERE name = :role_name AND is_system = true
                ON CONFLICT (role_id, resource) DO NOTHING
            """),
            {"role_name": role_name, "scope": ROLE_SCOPES[role_name]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    has_invoice_records = bind.execute(sa.text("""
        SELECT
            EXISTS (SELECT 1 FROM electronic_invoice_items)
            OR EXISTS (SELECT 1 FROM electronic_invoices)
            OR EXISTS (SELECT 1 FROM electronic_invoice_import_batches)
    """)).scalar_one()
    if has_invoice_records:
        raise RuntimeError(
            "Cannot downgrade while saved electronic invoice records exist; "
            "export or back up these records before removing the invoice tables."
        )

    bind.execute(sa.text("DELETE FROM role_data_scopes WHERE resource = 'invoices'"))
    bind.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions
            WHERE code IN ('invoices.view', 'invoices.import', 'invoices.void')
        )
    """))
    bind.execute(sa.text("""
        DELETE FROM permissions
        WHERE code IN ('invoices.view', 'invoices.import', 'invoices.void')
    """))

    op.drop_index("ix_einvoice_items_family_name", table_name="electronic_invoice_items")
    op.drop_index("ix_einvoice_items_family_invoice", table_name="electronic_invoice_items")
    op.drop_table("electronic_invoice_items")
    op.drop_index("ix_einvoices_family_transaction", table_name="electronic_invoices")
    op.drop_index("ix_einvoices_family_batch", table_name="electronic_invoices")
    op.drop_index("ix_einvoices_family_merchant_date", table_name="electronic_invoices")
    op.drop_index("ix_einvoices_family_number", table_name="electronic_invoices")
    op.drop_index("ix_einvoices_family_date", table_name="electronic_invoices")
    op.drop_table("electronic_invoices")
    op.drop_index("ix_einvoice_batches_family_created", table_name="electronic_invoice_import_batches")
    op.drop_table("electronic_invoice_import_batches")
