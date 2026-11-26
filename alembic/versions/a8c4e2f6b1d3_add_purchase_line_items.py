"""add structured purchase line items to expense transactions

Revision ID: a8c4e2f6b1d3
Revises: f5b7d9e1a3c5
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c4e2f6b1d3"
down_revision: Union[str, Sequence[str], None] = "f5b7d9e1a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_line_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("item_name", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=True),
        sa.Column("unit_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 4), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            name="fk_purchase_line_items_family_transaction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_purchase_line_items_created_by_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "family_id",
            "id",
            name="uq_purchase_line_items_family_id_id",
        ),
        sa.CheckConstraint(
            "length(btrim(item_name)) > 0",
            name="ck_purchase_line_items_item_name_not_blank",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_purchase_line_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_purchase_line_items_unit_price_nonnegative",
        ),
        sa.CheckConstraint(
            "line_total >= 0",
            name="ck_purchase_line_items_line_total_nonnegative",
        ),
    )
    op.create_index(
        "ix_purchase_line_items_family_transaction",
        "purchase_line_items",
        ["family_id", "transaction_id", "sort_order"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_purchase_items = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM purchase_line_items)")
    ).scalar_one()
    if has_purchase_items:
        raise RuntimeError(
            "Cannot downgrade while purchase line items exist; "
            "export or back up the records before removing this table."
        )

    op.drop_index(
        "ix_purchase_line_items_family_transaction",
        table_name="purchase_line_items",
    )
    op.drop_table("purchase_line_items")
