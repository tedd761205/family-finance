"""create family invitations

Revision ID: f2a4c6e8b0d2
Revises: c7d9e1f3a5b7
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a4c6e8b0d2"
down_revision: Union[str, Sequence[str], None] = "c7d9e1f3a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "family_invitations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_family_invitations_token_hash"),
    )
    op.create_index("ix_family_invitations_family_id", "family_invitations", ["family_id"])
    op.create_index("ix_family_invitations_email", "family_invitations", ["email"])
    op.create_index(
        "ix_family_invitations_pending_family_email",
        "family_invitations",
        ["family_id", "email"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_family_invitations_pending_family_email", table_name="family_invitations")
    op.drop_index("ix_family_invitations_email", table_name="family_invitations")
    op.drop_index("ix_family_invitations_family_id", table_name="family_invitations")
    op.drop_table("family_invitations")
