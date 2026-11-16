
"""create categories, transfers and transactions tables

Revision ID: 66b1e3d6c67a
Revises: b7c3fe056257
Create Date: 2026-11-16 03:48:35.381862
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "66b1e3d6c67a"
down_revision: Union[str, Sequence[str], None] = "b7c3fe056257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 先建立 accounts 複合唯一約束
    # 後續 transfers / transactions 的複合外鍵會參照這組欄位
    op.create_unique_constraint(
        "uq_accounts_family_id_id",
        "accounts",
        ["family_id", "id"],
    )

    # 2. 建立 categories
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=True),
        sa.Column("category_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category_type IN ('income', 'expense')",
            name="ck_categories_type",
        ),
        sa.CheckConstraint(
            """
            (family_id IS NULL AND is_system = true)
            OR
            (family_id IS NOT NULL AND is_system = false)
            """,
            name="ck_categories_system_scope",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_categories_family_id",
        "categories",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        "ix_categories_parent_id",
        "categories",
        ["parent_id"],
        unique=False,
    )
    op.create_index(
        "ix_categories_type",
        "categories",
        ["category_type"],
        unique=False,
    )
    op.create_index(
        "uq_categories_family_type_name",
        "categories",
        ["family_id", "category_type", "name"],
        unique=True,
        postgresql_where=sa.text("family_id IS NOT NULL"),
    )
    op.create_index(
        "uq_categories_system_type_name",
        "categories",
        ["category_type", "name"],
        unique=True,
        postgresql_where=sa.text("family_id IS NULL"),
    )

    # 3. 建立 transfers
    op.create_table(
        "transfers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("from_account_id", sa.BigInteger(), nullable=False),
        sa.Column("to_account_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), server_default="TWD", nullable=False),
        sa.Column("transfer_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("fee_amount", sa.Numeric(precision=20, scale=4), server_default="0", nullable=False),
        sa.Column("fee_account_id", sa.BigInteger(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_transfers_amount_positive",
        ),
        sa.CheckConstraint(
            "fee_amount = 0 OR fee_account_id IS NOT NULL",
            name="ck_transfers_fee_account_required",
        ),
        sa.CheckConstraint(
            "fee_amount >= 0",
            name="ck_transfers_fee_nonnegative",
        ),
        sa.CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_different_accounts",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["family_id", "fee_account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transfers_family_fee_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "from_account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transfers_family_from_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "to_account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transfers_family_to_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "family_id",
            "id",
            name="uq_transfers_family_id_id",
        ),
    )

    op.create_index(
        "ix_transfers_family_id",
        "transfers",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        "ix_transfers_from_account_id",
        "transfers",
        ["from_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_transfers_to_account_id",
        "transfers",
        ["to_account_id"],
        unique=False,
    )

    # 4. 建立 transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), server_default="TWD", nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("transfer_id", sa.BigInteger(), nullable=True),
        sa.Column("related_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("external_reference", sa.String(length=100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_voided", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_transactions_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["family_id", "account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transactions_family_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "related_transaction_id"],
            ["transactions.family_id", "transactions.id"],
            name="fk_transactions_family_related_transaction",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "transfer_id"],
            ["transfers.family_id", "transfers.id"],
            name="fk_transactions_family_transfer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "family_id",
            "id",
            name="uq_transactions_family_id_id",
        ),
    )

    op.create_index(
        "ix_transactions_created_by",
        "transactions",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_family_account_date",
        "transactions",
        ["family_id", "account_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_related_transaction_id",
        "transactions",
        ["related_transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_transfer_id",
        "transactions",
        ["transfer_id"],
        unique=False,
    )

    # 5. 分類父子關係的家庭範圍檢查
    # 系統分類可以作為家庭自訂分類的父分類；
    # 家庭分類不能成為其他家庭或系統分類的父分類。
    # 同時檢查分類類型及防止父子循環。

    op.execute("""
    CREATE OR REPLACE FUNCTION check_category_parent_scope()
    RETURNS TRIGGER AS $$
    DECLARE
        parent_family_id BIGINT;
        parent_category_type VARCHAR(20);
    BEGIN
        IF NEW.parent_id IS NULL THEN
            RETURN NEW;
        END IF;

        IF NEW.id IS NOT NULL AND NEW.parent_id = NEW.id THEN
            RAISE EXCEPTION 'Category cannot be its own parent'
                USING ERRCODE = '23514';
        END IF;

        SELECT family_id, category_type
        INTO parent_family_id, parent_category_type
        FROM categories
        WHERE id = NEW.parent_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Parent category does not exist'
                USING ERRCODE = '23503';
        END IF;

        IF parent_family_id IS NOT NULL
           AND parent_family_id IS DISTINCT FROM NEW.family_id THEN
            RAISE EXCEPTION 'Parent category belongs to another family'
                USING ERRCODE = '23514';
        END IF;

        IF parent_category_type IS DISTINCT FROM NEW.category_type THEN
            RAISE EXCEPTION 'Parent and child category types must match'
                USING ERRCODE = '23514';
        END IF;

        IF NEW.id IS NOT NULL THEN
            IF EXISTS (
                WITH RECURSIVE ancestors(id) AS (
                    SELECT NEW.parent_id
                    UNION
                    SELECT c.parent_id
                    FROM categories c
                    JOIN ancestors a ON c.id = a.id
                    WHERE c.parent_id IS NOT NULL
                )
                SELECT 1
                FROM ancestors
                WHERE id = NEW.id
            ) THEN
                RAISE EXCEPTION 'Category parent relationship cannot contain a cycle'
                    USING ERRCODE = '23514';
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trg_check_category_parent_scope
    BEFORE INSERT OR UPDATE OF family_id, parent_id, category_type
    ON categories
    FOR EACH ROW
    EXECUTE FUNCTION check_category_parent_scope();
    """)

    # 6. 交易分類的家庭範圍檢查
    # 允許使用系統分類（family_id IS NULL）
    # 或目前家庭自己的分類。

    op.execute("""
    CREATE OR REPLACE FUNCTION check_transaction_category_scope()
    RETURNS TRIGGER AS $$
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

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Transaction category does not exist'
                USING ERRCODE = '23503';
        END IF;

        IF category_family_id IS NOT NULL
           AND category_family_id <> NEW.family_id THEN
            RAISE EXCEPTION 'Transaction category belongs to another family'
                USING ERRCODE = '23514';
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trg_check_transaction_category_scope
    BEFORE INSERT OR UPDATE OF family_id, category_id
    ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION check_transaction_category_scope();
    """)


def downgrade() -> None:
    # 1. 先移除 Trigger 及其函式
    op.execute("""
    DROP TRIGGER IF EXISTS trg_check_transaction_category_scope
    ON transactions;
    """)
    op.execute("""
    DROP FUNCTION IF EXISTS check_transaction_category_scope();
    """)

    op.execute("""
    DROP TRIGGER IF EXISTS trg_check_category_parent_scope
    ON categories;
    """)
    op.execute("""
    DROP FUNCTION IF EXISTS check_category_parent_scope();
    """)

    # 2. 移除 transactions
    op.drop_index(
        "ix_transactions_transfer_id",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_related_transaction_id",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_family_account_date",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_created_by",
        table_name="transactions",
    )
    op.drop_table("transactions")

    # 3. 移除 transfers
    op.drop_index(
        "ix_transfers_to_account_id",
        table_name="transfers",
    )
    op.drop_index(
        "ix_transfers_from_account_id",
        table_name="transfers",
    )
    op.drop_index(
        "ix_transfers_family_id",
        table_name="transfers",
    )
    op.drop_table("transfers")

    # 4. 移除 categories
    op.drop_index(
        "uq_categories_system_type_name",
        table_name="categories",
        postgresql_where=sa.text("family_id IS NULL"),
    )
    op.drop_index(
        "uq_categories_family_type_name",
        table_name="categories",
        postgresql_where=sa.text("family_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_categories_type",
        table_name="categories",
    )
    op.drop_index(
        "ix_categories_parent_id",
        table_name="categories",
    )
    op.drop_index(
        "ix_categories_family_id",
        table_name="categories",
    )
    op.drop_table("categories")

    # 5. 最後才移除 accounts 複合唯一約束
    op.drop_constraint(
        "uq_accounts_family_id_id",
        "accounts",
        type_="unique",
    )
