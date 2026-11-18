"""add secure family attachments

Revision ID: e7f9a1b3c5d7
Revises: d5e7f9a1b3c5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7f9a1b3c5d7"
down_revision: Union[str, Sequence[str], None] = "d5e7f9a1b3c5"
branch_labels = None
depends_on = None

ATTACHMENT_PERMISSIONS = (
    ("attachments.view", "查看附件", "查看帳單照片及相關附件", "attachments"),
    ("attachments.upload", "上傳附件", "上傳帳單照片及其他財務附件", "attachments"),
    ("attachments.void", "停用附件", "停用附件並保留必要的操作紀錄", "attachments"),
)
ROLE_CODES = {
    "家庭管理員": ("attachments.view", "attachments.upload", "attachments.void"),
    "財務管理員": ("attachments.view", "attachments.upload", "attachments.void"),
    "一般成員": ("attachments.view", "attachments.upload"),
    "記帳人員": ("attachments.view", "attachments.upload"),
    "檢視人員": ("attachments.view",),
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
        "attachments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("bill_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("is_voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.BigInteger(), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_attachments_family_id_id"),
        sa.UniqueConstraint("object_key", name="uq_attachments_object_key"),
        sa.CheckConstraint(
            "(bill_id IS NOT NULL AND transaction_id IS NULL) OR "
            "(bill_id IS NULL AND transaction_id IS NOT NULL)",
            name="ck_attachments_exactly_one_parent",
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_attachments_allowed_content_type",
        ),
        sa.CheckConstraint(
            "file_size > 0 AND file_size <= 10485760",
            name="ck_attachments_file_size",
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_attachments_sha256"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_attachments_family"),
        sa.ForeignKeyConstraint(
            ["family_id", "bill_id"], ["bills.family_id", "bills.id"],
            ondelete="RESTRICT", name="fk_attachments_family_bill",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "transaction_id"], ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT", name="fk_attachments_family_transaction",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_attachments_created_by"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT", name="fk_attachments_voided_by"),
    )
    op.create_index(
        "ix_attachments_family_bill_created", "attachments",
        ["family_id", "bill_id", "created_at"],
    )
    op.create_index(
        "ix_attachments_family_transaction_created", "attachments",
        ["family_id", "transaction_id", "created_at"],
    )
    op.create_index("ix_attachments_created_by", "attachments", ["created_by"])

    bind = op.get_bind()
    for code, name, description, category in ATTACHMENT_PERMISSIONS:
        bind.execute(sa.text("""
            INSERT INTO permissions (code,name,description,category,is_active)
            VALUES (:code,:name,:description,:category,true)
            ON CONFLICT (code) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                category=EXCLUDED.category, is_active=true
        """), {"code": code, "name": name, "description": description, "category": category})

    for role, codes in ROLE_CODES.items():
        for code in codes:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id,permission_id)
                SELECT r.id,p.id FROM roles r JOIN permissions p ON p.code=:code
                WHERE r.name=:role AND r.is_system=true
                ON CONFLICT DO NOTHING
            """), {"role": role, "code": code})
        bind.execute(sa.text("""
            INSERT INTO role_data_scopes (role_id,family_id,resource,scope)
            SELECT id,family_id,'attachments',:scope FROM roles
            WHERE name=:role AND is_system=true
            ON CONFLICT (role_id,resource) DO UPDATE SET scope=EXCLUDED.scope
        """), {"role": role, "scope": ROLE_SCOPES[role]})


def downgrade() -> None:
    # attachments.* 權限與資料範圍原本已存在於系統權限目錄；
    # 降版只移除本次新增的附件資料結構，不刪除既有角色授權。
    op.drop_index("ix_attachments_created_by", table_name="attachments")
    op.drop_index("ix_attachments_family_transaction_created", table_name="attachments")
    op.drop_index("ix_attachments_family_bill_created", table_name="attachments")
    op.drop_table("attachments")
