"""create recurring bill rules and idempotent bill occurrences

Revision ID: c2d4e6f8a0b1
Revises: b1a7c903e642
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c2d4e6f8a0b1"
down_revision: Union[str, Sequence[str], None] = "b1a7c903e642"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("recurring_bills.view", "查看定期帳單", "查看固定週期的帳單及提醒", "recurring_bills"),
    ("recurring_bills.create", "新增定期帳單", "建立定期帳單及繳費週期", "recurring_bills"),
    ("recurring_bills.update", "修改定期帳單", "修改定期帳單內容及週期", "recurring_bills"),
    ("recurring_bills.void", "停用定期帳單", "停止定期帳單並保留歷史紀錄", "recurring_bills"),
)
ROLE_CODES = {
    "家庭管理員": ("recurring_bills.view", "recurring_bills.create", "recurring_bills.update", "recurring_bills.void"),
    "財務管理員": ("recurring_bills.view", "recurring_bills.create", "recurring_bills.update", "recurring_bills.void"),
    "一般成員": ("recurring_bills.view", "recurring_bills.create", "recurring_bills.update", "recurring_bills.void"),
    "記帳人員": ("recurring_bills.view", "recurring_bills.create", "recurring_bills.update", "recurring_bills.void"),
    "檢視人員": ("recurring_bills.view",),
}
ROLE_SCOPES = {"家庭管理員":"family", "財務管理員":"family", "一般成員":"own", "記帳人員":"family", "檢視人員":"family"}

def upgrade() -> None:
    op.create_table(
        "recurring_bills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("interval_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("next_run_date", sa.Date(), nullable=False),
        sa.Column("due_days_after", sa.Integer(), server_default="0", nullable=False),
        sa.Column("original_amount", sa.Numeric(20,4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20,4), server_default="0", nullable=False),
        sa.Column("discount_amount", sa.Numeric(20,4), server_default="0", nullable=False),
        sa.Column("currency_code", sa.String(3), server_default="TWD", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("frequency IN ('weekly','monthly','yearly')", name="ck_recurring_bills_frequency"),
        sa.CheckConstraint("interval_count >= 1", name="ck_recurring_bills_interval_positive"),
        sa.CheckConstraint("original_amount > 0 AND tax_amount >= 0 AND discount_amount >= 0", name="ck_recurring_bills_amounts"),
        sa.CheckConstraint("original_amount + tax_amount - discount_amount >= 0", name="ck_recurring_bills_total_nonnegative"),
        sa.CheckConstraint("due_days_after >= 0 AND due_days_after <= 365", name="ck_recurring_bills_due_days"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_recurring_bills_date_range"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_recurring_bills_family"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT", name="fk_recurring_bills_category"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_recurring_bills_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_recurring_bills_updated_by"),
    )
    op.create_index("ix_recurring_bills_family_active", "recurring_bills", ["family_id", "is_active"])
    op.create_index("ix_recurring_bills_next_run", "recurring_bills", ["next_run_date"], postgresql_where=sa.text("is_active = true"))

    op.add_column("bills", sa.Column("recurring_bill_id", sa.BigInteger(), nullable=True))
    op.add_column("bills", sa.Column("recurring_occurrence_date", sa.Date(), nullable=True))
    op.create_foreign_key("fk_bills_recurring_bill", "bills", "recurring_bills", ["recurring_bill_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint(
        "ck_bills_recurring_occurrence_pair", "bills",
        "(recurring_bill_id IS NULL AND recurring_occurrence_date IS NULL) OR (recurring_bill_id IS NOT NULL AND recurring_occurrence_date IS NOT NULL)"
    )
    op.create_index(
        "uq_bills_recurring_occurrence", "bills",
        ["recurring_bill_id", "recurring_occurrence_date"], unique=True,
        postgresql_where=sa.text("recurring_bill_id IS NOT NULL")
    )

    bind = op.get_bind()
    bind.exec_driver_sql("""
        CREATE OR REPLACE FUNCTION check_recurring_bill_category_scope()
        RETURNS trigger LANGUAGE plpgsql AS $recurring_category_scope$
        DECLARE category_family_id BIGINT;
        BEGIN
            IF NEW.category_id IS NULL THEN RETURN NEW; END IF;
            SELECT family_id INTO category_family_id FROM categories WHERE id = NEW.category_id;
            IF FOUND AND category_family_id IS NOT NULL AND category_family_id <> NEW.family_id THEN
                RAISE EXCEPTION '定期帳單分類必須屬於同一家庭或為系統分類'
                    USING ERRCODE = '23514', CONSTRAINT = 'ck_recurring_bills_category_family_scope';
            END IF;
            RETURN NEW;
        END;
        $recurring_category_scope$;
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER trg_check_recurring_bill_category_scope
        BEFORE INSERT OR UPDATE OF family_id, category_id ON recurring_bills
        FOR EACH ROW EXECUTE FUNCTION check_recurring_bill_category_scope();
    """)

    for code, name, description, category in PERMISSIONS:
        bind.execute(sa.text("""
            INSERT INTO permissions (code,name,description,category,is_active)
            VALUES (:code,:name,:description,:category,true)
            ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, category=EXCLUDED.category
        """), {"code":code,"name":name,"description":description,"category":category})
    for role, codes in ROLE_CODES.items():
        for code in codes:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id,permission_id)
                SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code=:code
                WHERE r.name=:role AND r.is_system=true ON CONFLICT DO NOTHING
            """), {"role":role,"code":code})
        bind.execute(sa.text("""
            INSERT INTO role_data_scopes (role_id,family_id,resource,scope)
            SELECT id,family_id,'recurring_bills',:scope FROM roles
            WHERE name=:role AND is_system=true
            ON CONFLICT (role_id,resource) DO UPDATE SET scope=EXCLUDED.scope
        """), {"role":role,"scope":ROLE_SCOPES[role]})

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_recurring_bill_category_scope ON recurring_bills")
    op.execute("DROP FUNCTION IF EXISTS check_recurring_bill_category_scope()")
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM role_permissions rp USING permissions p
        WHERE rp.permission_id=p.id AND p.code LIKE 'recurring_bills.%'
    """))
    bind.execute(sa.text("DELETE FROM role_data_scopes WHERE resource='recurring_bills'"))
    bind.execute(sa.text("DELETE FROM permissions WHERE code LIKE 'recurring_bills.%'"))
    op.drop_index("uq_bills_recurring_occurrence", table_name="bills")
    op.drop_constraint("ck_bills_recurring_occurrence_pair", "bills", type_="check")
    op.drop_constraint("fk_bills_recurring_bill", "bills", type_="foreignkey")
    op.drop_column("bills", "recurring_occurrence_date")
    op.drop_column("bills", "recurring_bill_id")
    op.drop_index("ix_recurring_bills_next_run", table_name="recurring_bills")
    op.drop_index("ix_recurring_bills_family_active", table_name="recurring_bills")
    op.drop_table("recurring_bills")
