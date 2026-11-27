"""add family e-invoice item categories and reusable category rules

Revision ID: d1e3f5a7b9c2
Revises: c9e1a4b6d8f0
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e3f5a7b9c2"
down_revision: Union[str, Sequence[str], None] = "c9e1a4b6d8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("einvoice_items", sa.Column("category_id", sa.BigInteger(), nullable=True))
    op.add_column("einvoice_items", sa.Column("category_source", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        "fk_einvoice_items_category",
        "einvoice_items",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_einvoice_items_category_source",
        "einvoice_items",
        "category_source IS NULL OR category_source = 'manual'",
    )
    op.create_index(
        "ix_einvoice_items_family_category",
        "einvoice_items",
        ["family_id", "category_id"],
    )

    op.create_table(
        "einvoice_category_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("merchant_key", sa.String(length=210), nullable=False),
        sa.Column("merchant_tax_id", sa.String(length=8), nullable=True),
        sa.Column("merchant_name", sa.String(length=200), nullable=False),
        sa.Column("item_name_key", sa.String(length=200), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "family_id", "merchant_key", "item_name_key",
            name="uq_einvoice_category_rules_match",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            name="fk_einvoice_category_rules_family",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"],
            name="fk_einvoice_category_rules_category",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            name="fk_einvoice_category_rules_created_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            name="fk_einvoice_category_rules_updated_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(btrim(merchant_key)) > 0",
            name="ck_einvoice_category_rules_merchant_key",
        ),
        sa.CheckConstraint(
            "length(btrim(item_name_key)) > 0",
            name="ck_einvoice_category_rules_item_key",
        ),
        sa.CheckConstraint(
            "merchant_tax_id IS NULL OR merchant_tax_id ~ '^[0-9]{8}$'",
            name="ck_einvoice_category_rules_tax_id",
        ),
    )
    op.create_index(
        "ix_einvoice_category_rules_family_active",
        "einvoice_category_rules",
        ["family_id", "is_active"],
    )
    op.create_index(
        "ix_einvoice_category_rules_category",
        "einvoice_category_rules",
        ["family_id", "category_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_category_rules = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM einvoice_category_rules)")
    ).scalar_one()
    has_classified_items = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM einvoice_items WHERE category_id IS NOT NULL)")
    ).scalar_one()
    if has_category_rules or has_classified_items:
        raise RuntimeError(
            "Cannot downgrade while invoice category assignments or reusable rules exist; "
            "export or back up those records before removing the feature."
        )

    op.drop_index("ix_einvoice_category_rules_category", table_name="einvoice_category_rules")
    op.drop_index("ix_einvoice_category_rules_family_active", table_name="einvoice_category_rules")
    op.drop_table("einvoice_category_rules")
    op.drop_index("ix_einvoice_items_family_category", table_name="einvoice_items")
    op.drop_constraint("ck_einvoice_items_category_source", "einvoice_items", type_="check")
    op.drop_constraint("fk_einvoice_items_category", "einvoice_items", type_="foreignkey")
    op.drop_column("einvoice_items", "category_source")
    op.drop_column("einvoice_items", "category_id")
