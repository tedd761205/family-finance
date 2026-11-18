"""create bills core table and bill permissions

Revision ID: b1a7c903e642
Revises: 49ed3855c31c
Create Date: 2026-11-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1a7c903e642"
down_revision: Union[str, Sequence[str], None] = "49ed3855c31c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BILL_PERMISSIONS = (
    ("bills.view", "查看帳單", "查看家庭帳單及應繳義務", "bills"),
    ("bills.create", "新增帳單", "建立家庭帳單", "bills"),
    ("bills.update", "修改帳單", "修改尚未作廢的帳單", "bills"),
    ("bills.void", "作廢帳單", "作廢帳單並保留歷史紀錄", "bills"),
)

ROLE_PERMISSION_CODES = {
    "家庭管理員": ("bills.view", "bills.create", "bills.update", "bills.void"),
    "財務管理員": ("bills.view", "bills.create", "bills.update", "bills.void"),
    "一般成員": ("bills.view", "bills.create", "bills.update", "bills.void"),
    "記帳人員": ("bills.view", "bills.create", "bills.update"),
    "檢視人員": ("bills.view",),
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
        "bills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("bill_number", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("billing_period_start", sa.Date(), nullable=True),
        sa.Column("billing_period_end", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("original_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("discount_amount", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("currency_code", sa.String(length=3), server_default="TWD", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_amount > 0", name="ck_bills_original_amount_positive"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_bills_tax_amount_nonnegative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_bills_discount_amount_nonnegative"),
        sa.CheckConstraint("original_amount + tax_amount - discount_amount >= 0", name="ck_bills_total_amount_nonnegative"),
        sa.CheckConstraint(
            "(billing_period_start IS NULL AND billing_period_end IS NULL) OR "
            "(billing_period_start IS NOT NULL AND billing_period_end IS NOT NULL AND "
            "billing_period_start <= billing_period_end)",
            name="ck_bills_billing_period_valid",
        ),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_bills_family"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT", name="fk_bills_category"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_bills_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_bills_updated_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_bills_voided_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "id", name="uq_bills_family_id_id"),
    )
    op.create_index("ix_bills_family_bill_date", "bills", ["family_id", "bill_date"])
    op.create_index("ix_bills_family_due_date", "bills", ["family_id", "due_date"])
    op.create_index("ix_bills_created_by", "bills", ["created_by"])
    op.create_index(
        "uq_bills_family_bill_number_active",
        "bills",
        ["family_id", "bill_number"],
        unique=True,
        postgresql_where=sa.text("is_voided = false AND bill_number IS NOT NULL"),
    )

    bind = op.get_bind()
    bind.exec_driver_sql("""
        CREATE OR REPLACE FUNCTION check_bill_category_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $bill_category_scope$
        DECLARE
            category_family_id BIGINT;
        BEGIN
            IF NEW.category_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT family_id
            INTO category_family_id
            FROM categories
            WHERE id = NEW.category_id;

            IF FOUND
               AND category_family_id IS NOT NULL
               AND category_family_id <> NEW.family_id THEN
                RAISE EXCEPTION '帳單分類必須屬於同一家庭或為系統分類'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_bills_category_family_scope';
            END IF;

            RETURN NEW;
        END;
        $bill_category_scope$;
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER trg_check_bill_category_scope
        BEFORE INSERT OR UPDATE OF family_id, category_id
        ON bills
        FOR EACH ROW
        EXECUTE FUNCTION check_bill_category_scope();
    """)

    bind = op.get_bind()
    for code, name, description, category in BILL_PERMISSIONS:
        bind.execute(
            sa.text("""
                INSERT INTO permissions (code, name, description, category, is_active)
                VALUES (:code, :name, :description, :category, true)
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category
            """),
            {"code": code, "name": name, "description": description, "category": category},
        )

    for role_name, codes in ROLE_PERMISSION_CODES.items():
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
                {"code": code, "role_name": role_name},
            )
        bind.execute(
            sa.text("""
                INSERT INTO role_data_scopes (role_id, family_id, resource, scope)
                SELECT r.id, r.family_id, 'bills', :scope
                FROM roles r
                WHERE r.name = :role_name AND r.is_system = true
                ON CONFLICT (role_id, resource) DO NOTHING
            """),
            {"role_name": role_name, "scope": ROLE_SCOPES[role_name]},
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_bill_category_scope ON bills")
    op.execute("DROP FUNCTION IF EXISTS check_bill_category_scope()")
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id AND p.code LIKE 'bills.%'
    """))
    bind.execute(sa.text("DELETE FROM role_data_scopes WHERE resource = 'bills'"))
    bind.execute(sa.text("DELETE FROM permissions WHERE code LIKE 'bills.%'"))
    op.drop_index("uq_bills_family_bill_number_active", table_name="bills")
    op.drop_index("ix_bills_created_by", table_name="bills")
    op.drop_index("ix_bills_family_due_date", table_name="bills")
    op.drop_index("ix_bills_family_bill_date", table_name="bills")
    op.drop_table("bills")
