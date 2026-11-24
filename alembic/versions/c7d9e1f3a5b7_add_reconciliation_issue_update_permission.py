"""grant reconciliation issue update permission to existing default roles

Revision ID: c7d9e1f3a5b7
Revises: a6b8c0d2e4f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d9e1f3a5b7"
down_revision: Union[str, Sequence[str], None] = "a6b8c0d2e4f6"
branch_labels = None
depends_on = None


PERMISSION = (
    "reconciliation.update",
    "處理對帳差異",
    "分類、更新及結案對帳差異，並保留處理說明與稽核紀錄",
    "reconciliation",
)

DEFAULT_ROLE_NAMES = ("家庭管理員", "財務管理員", "記帳人員")


def upgrade() -> None:
    bind = op.get_bind()
    code, name, description, category = PERMISSION

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
        {
            "code": code,
            "name": name,
            "description": description,
            "category": category,
        },
    )

    for role_name in DEFAULT_ROLE_NAMES:
        bind.execute(
            sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                JOIN permissions p ON p.code = :code
                WHERE r.name = :role_name
                  AND r.is_system = true
                ON CONFLICT DO NOTHING
            """),
            {"role_name": role_name, "code": code},
        )


def downgrade() -> None:
    bind = op.get_bind()
    code = PERMISSION[0]

    bind.execute(
        sa.text("""
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.is_system = true
              AND r.name IN :role_names
              AND p.code = :code
        """).bindparams(
            sa.bindparam("role_names", expanding=True)
        ),
        {"role_names": list(DEFAULT_ROLE_NAMES), "code": code},
    )

    bind.execute(
        sa.text("""
            DELETE FROM permissions p
            WHERE p.code = :code
              AND NOT EXISTS (
                  SELECT 1
                  FROM role_permissions rp
                  WHERE rp.permission_id = p.id
              )
        """),
        {"code": code},
    )
