"""add durable OCR task workflow

Revision ID: f1a2b3c4d5e6
Revises: e7f9a1b3c5d7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e7f9a1b3c5d7"
branch_labels = None
depends_on = None

OCR_PERMISSIONS = (
    ("ocr.view", "查看 OCR 辨識", "查看帳單圖片文字辨識結果", "ocr"),
    ("ocr.create", "建立 OCR 辨識", "建立並執行帳單圖片文字辨識", "ocr"),
    ("ocr.retry", "重試 OCR 辨識", "重試失敗的文字辨識工作", "ocr"),
    ("ocr.confirm", "確認 OCR 結果", "人工確認 OCR 擷取結果", "ocr"),
)
ROLE_CODES = {
    "家庭管理員": ("ocr.view", "ocr.create", "ocr.retry", "ocr.confirm"),
    "財務管理員": ("ocr.view", "ocr.create", "ocr.retry", "ocr.confirm"),
    "一般成員": ("ocr.view", "ocr.create", "ocr.confirm"),
    "記帳人員": ("ocr.view", "ocr.create", "ocr.retry", "ocr.confirm"),
    "檢視人員": ("ocr.view",),
}
ROLE_SCOPES = {
    "家庭管理員": "family", "財務管理員": "family",
    "一般成員": "own", "記帳人員": "family", "檢視人員": "family",
}


def upgrade() -> None:
    op.create_table(
        "ocr_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("attachment_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("provider", sa.String(40), server_default="google_vision", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("suggested_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_ocr_tasks_family_id_id"),
        sa.UniqueConstraint("family_id", "attachment_id", name="uq_ocr_tasks_family_attachment"),
        sa.ForeignKeyConstraint(["family_id", "attachment_id"], ["attachments.family_id", "attachments.id"], ondelete="RESTRICT", name="fk_ocr_tasks_family_attachment"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_ocr_tasks_family"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_ocr_tasks_created_by"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT", name="fk_ocr_tasks_confirmed_by"),
        sa.CheckConstraint("status IN ('queued','processing','succeeded','failed','confirmed')", name="ck_ocr_tasks_status"),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_ocr_tasks_attempts"),
    )
    op.create_index("ix_ocr_tasks_family_status_created", "ocr_tasks", ["family_id", "status", "created_at"])
    op.create_index("ix_ocr_tasks_attachment_created", "ocr_tasks", ["family_id", "attachment_id", "created_at"])

    bind = op.get_bind()
    for code, name, description, category in OCR_PERMISSIONS:
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
            SELECT id,family_id,'ocr',:scope FROM roles
            WHERE name=:role AND is_system=true
            ON CONFLICT (role_id,resource) DO UPDATE SET scope=EXCLUDED.scope
        """), {"role": role, "scope": ROLE_SCOPES[role]})


def downgrade() -> None:
    op.drop_index("ix_ocr_tasks_attachment_created", table_name="ocr_tasks")
    op.drop_index("ix_ocr_tasks_family_status_created", table_name="ocr_tasks")
    op.drop_table("ocr_tasks")
