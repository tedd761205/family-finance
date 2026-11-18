"""add family collaboration, notifications and export workflows

Revision ID: a7c9e1f3b5d7
Revises: f1a2b3c4d5e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7c9e1f3b5d7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("notifications.view", "查看通知", "查看本人收到的家庭通知", "notifications"),
    ("notifications.manage", "管理通知", "管理家庭通知及通知狀態", "notifications"),
    ("exports.view", "查看匯出範本與紀錄", "查看家庭匯出範本、排程及匯出紀錄", "exports"),
    ("exports.create", "建立匯出範本", "建立家庭共用匯出範本", "exports"),
    ("exports.update", "修改匯出範本", "修改草稿匯出範本及手動合併版本", "exports"),
    ("exports.publish", "發布匯出範本", "發布及停用家庭共用匯出範本", "exports"),
    ("exports.schedule", "管理定期匯出", "建立、修改及停用定期匯出排程", "exports"),
    ("exports.download", "下載匯出檔案", "下載本人資料範圍內且仍有權限的匯出檔案", "exports"),
    ("exports.dashboard", "查看匯出管理統計", "查看家庭匯出執行統計及管理追蹤", "exports"),
)
ROLE_CODES = {
    "家庭管理員": tuple(item[0] for item in PERMISSIONS),
    "財務管理員": ("notifications.view", "exports.view", "exports.create", "exports.update", "exports.publish", "exports.schedule", "exports.download", "exports.dashboard"),
    "一般成員": ("notifications.view", "exports.view", "exports.create", "exports.download"),
    "記帳人員": ("notifications.view", "exports.view", "exports.create", "exports.download"),
    "檢視人員": ("notifications.view", "exports.view"),
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
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("notification_type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_notifications_family"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="RESTRICT", name="fk_notifications_recipient"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL", name="fk_notifications_actor"),
    )
    op.create_index("ix_notifications_recipient_created", "notifications", ["family_id", "recipient_user_id", "created_at"])
    op.create_index("ix_notifications_recipient_unread", "notifications", ["recipient_user_id", "read_at"])

    op.create_table(
        "export_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_export_templates_family_id_id"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_export_templates_family"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_export_templates_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_export_templates_updated_by"),
        sa.CheckConstraint("status IN ('draft','published','disabled')", name="ck_export_templates_status"),
        sa.CheckConstraint("version >= 1", name="ck_export_templates_version"),
    )
    op.create_index("ix_export_templates_family_status", "export_templates", ["family_id", "status"])

    op.create_table(
        "export_template_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "template_id", "version", name="uq_export_template_versions_version"),
        sa.ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_template_versions_family_template"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_export_template_versions_created_by"),
        sa.CheckConstraint("status IN ('draft','published','disabled')", name="ck_export_template_versions_status"),
    )

    op.create_table(
        "export_schedules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("monthday", sa.Integer(), nullable=True),
        sa.Column("local_hour", sa.Integer(), server_default="8", nullable=False),
        sa.Column("local_minute", sa.Integer(), server_default="0", nullable=False),
        sa.Column("timezone", sa.String(64), server_default="Asia/Taipei", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("family_id", "id", name="uq_export_schedules_family_id_id"),
        sa.ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_schedules_family_template"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_export_schedules_created_by"),
        sa.CheckConstraint("frequency IN ('daily','weekly','monthly')", name="ck_export_schedules_frequency"),
        sa.CheckConstraint("local_hour >= 0 AND local_hour <= 23 AND local_minute >= 0 AND local_minute <= 59", name="ck_export_schedules_local_time"),
        sa.CheckConstraint("(frequency != 'weekly' OR weekday IS NOT NULL) AND (frequency != 'monthly' OR monthday IS NOT NULL)", name="ck_export_schedules_frequency_day"),
    )
    op.create_index("ix_export_schedules_due", "export_schedules", ["enabled", "next_run_at"])

    op.create_table(
        "export_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("schedule_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_by", sa.BigInteger(), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("template_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("object_key", sa.String(500), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("family_id", "id", name="uq_export_runs_family_id_id"),
        sa.ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_runs_family_template"),
        sa.ForeignKeyConstraint(["family_id", "schedule_id"], ["export_schedules.family_id", "export_schedules.id"], ondelete="RESTRICT", name="fk_export_runs_family_schedule"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL", name="fk_export_runs_requested_by"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','revoked')", name="ck_export_runs_status"),
    )
    op.create_index("ix_export_runs_family_created", "export_runs", ["family_id", "created_at"])

    bind = op.get_bind()
    for code, name, description, category in PERMISSIONS:
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
            SELECT id,family_id,'exports',:scope FROM roles
            WHERE name=:role AND is_system=true
            ON CONFLICT (role_id,resource) DO UPDATE SET scope=EXCLUDED.scope
        """), {"role": role, "scope": ROLE_SCOPES[role]})


def downgrade() -> None:
    op.drop_index("ix_export_runs_family_created", table_name="export_runs")
    op.drop_table("export_runs")
    op.drop_index("ix_export_schedules_due", table_name="export_schedules")
    op.drop_table("export_schedules")
    op.drop_table("export_template_versions")
    op.drop_index("ix_export_templates_family_status", table_name="export_templates")
    op.drop_table("export_templates")
    op.drop_index("ix_notifications_recipient_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
