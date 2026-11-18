"""add bill payment and refund ledger

Revision ID: d5e7f9a1b3c5
Revises: c2d4e6f8a0b1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e7f9a1b3c5"
down_revision: Union[str, Sequence[str], None] = "c2d4e6f8a0b1"
branch_labels = None
depends_on = None

PAYMENTS = (
    ("payments.view", "查看付款", "查看帳單付款及繳費紀錄", "payments"),
    ("payments.create", "新增付款", "新增帳單付款及繳費紀錄", "payments"),
    ("payments.update", "修改付款", "修改付款資料", "payments"),
    ("payments.void", "作廢付款", "作廢付款紀錄並保留歷史資料", "payments"),
)
ROLE_CODES = {
    "家庭管理員": ("payments.view", "payments.create", "payments.update", "payments.void"),
    "財務管理員": ("payments.view", "payments.create", "payments.update", "payments.void"),
    "一般成員": ("payments.view", "payments.create", "payments.update", "payments.void"),
    "記帳人員": ("payments.view", "payments.create", "payments.update"),
    "檢視人員": ("payments.view",),
}
ROLE_SCOPES = {
    "家庭管理員": "family", "財務管理員": "family",
    "一般成員": "own", "記帳人員": "family", "檢視人員": "family",
}


def upgrade() -> None:
    op.create_table(
        "bill_payments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("bill_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_type", sa.String(10), nullable=False),
        sa.Column("original_payment_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("payment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("payment_type IN ('payment','refund')", name="ck_bill_payments_type"),
        sa.CheckConstraint("amount > 0", name="ck_bill_payments_amount_positive"),
        sa.CheckConstraint(
            "(payment_type='payment' AND original_payment_id IS NULL) OR "
            "(payment_type='refund' AND original_payment_id IS NOT NULL)",
            name="ck_bill_payments_original_payment_pair",
        ),
        sa.ForeignKeyConstraint(["family_id","bill_id"], ["bills.family_id","bills.id"], ondelete="RESTRICT", name="fk_bill_payments_family_bill"),
        sa.ForeignKeyConstraint(["family_id","account_id"], ["accounts.family_id","accounts.id"], ondelete="RESTRICT", name="fk_bill_payments_family_account"),
        sa.ForeignKeyConstraint(["family_id","original_payment_id"], ["bill_payments.family_id","bill_payments.id"], ondelete="RESTRICT", name="fk_bill_payments_original_payment"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_bill_payments_created_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_bill_payments_voided_by"),
        sa.UniqueConstraint("family_id","id", name="uq_bill_payments_family_id_id"),
    )
    op.create_index("ix_bill_payments_family_bill_date", "bill_payments", ["family_id","bill_id","payment_date"])
    op.create_index("ix_bill_payments_family_account_date", "bill_payments", ["family_id","account_id","payment_date"])
    op.create_index("ix_bill_payments_original_payment", "bill_payments", ["family_id","original_payment_id"])
    op.create_index("ix_bill_payments_created_by", "bill_payments", ["created_by"])

    op.add_column("transactions", sa.Column("bill_payment_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_family_bill_payment", "transactions", "bill_payments",
        ["family_id","bill_payment_id"], ["family_id","id"], ondelete="RESTRICT",
    )
    op.create_index("ix_transactions_bill_payment_id", "transactions", ["bill_payment_id"])
    op.create_index(
        "uq_transactions_active_bill_payment", "transactions",
        ["family_id","bill_payment_id"], unique=True,
        postgresql_where=sa.text("bill_payment_id IS NOT NULL"),
    )

    bind = op.get_bind()
    for code, name, description, category in PAYMENTS:
        bind.execute(sa.text("""
            INSERT INTO permissions (code,name,description,category,is_active)
            VALUES (:code,:name,:description,:category,true)
            ON CONFLICT (code) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                category=EXCLUDED.category, is_active=true
        """), {"code":code,"name":name,"description":description,"category":category})
    for role, codes in ROLE_CODES.items():
        for code in codes:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id,permission_id)
                SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code=:code
                WHERE r.name=:role AND r.is_system=true
                ON CONFLICT DO NOTHING
            """), {"role":role,"code":code})
        bind.execute(sa.text("""
            INSERT INTO role_data_scopes (role_id,family_id,resource,scope)
            SELECT id,family_id,'payments',:scope FROM roles
            WHERE name=:role AND is_system=true
            ON CONFLICT (role_id,resource) DO UPDATE SET scope=EXCLUDED.scope
        """), {"role":role,"scope":ROLE_SCOPES[role]})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM role_permissions rp USING permissions p
        WHERE rp.permission_id=p.id AND p.code LIKE 'payments.%'
    """))
    bind.execute(sa.text("DELETE FROM role_data_scopes WHERE resource='payments'"))
    bind.execute(sa.text("DELETE FROM permissions WHERE code LIKE 'payments.%'"))
    op.drop_index("uq_transactions_active_bill_payment", table_name="transactions")
    op.drop_index("ix_transactions_bill_payment_id", table_name="transactions")
    op.drop_constraint("fk_transactions_family_bill_payment", "transactions", type_="foreignkey")
    op.drop_column("transactions", "bill_payment_id")
    op.drop_index("ix_bill_payments_created_by", table_name="bill_payments")
    op.drop_index("ix_bill_payments_original_payment", table_name="bill_payments")
    op.drop_index("ix_bill_payments_family_account_date", table_name="bill_payments")
    op.drop_index("ix_bill_payments_family_bill_date", table_name="bill_payments")
    op.drop_table("bill_payments")
