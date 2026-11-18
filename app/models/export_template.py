from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ExportTemplate(Base):
    __tablename__ = "export_templates"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_export_templates_family_id_id"),
        CheckConstraint("status IN ('draft','published','disabled')", name="ck_export_templates_status"),
        CheckConstraint("version >= 1", name="ck_export_templates_version"),
        Index("ix_export_templates_family_status", "family_id", "status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("families.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ExportTemplateVersion(Base):
    __tablename__ = "export_template_versions"
    __table_args__ = (
        UniqueConstraint("family_id", "template_id", "version", name="uq_export_template_versions_version"),
        ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_template_versions_family_template"),
        CheckConstraint("status IN ('draft','published','disabled')", name="ck_export_template_versions_status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExportSchedule(Base):
    __tablename__ = "export_schedules"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_export_schedules_family_id_id"),
        ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_schedules_family_template"),
        CheckConstraint("frequency IN ('daily','weekly','monthly')", name="ck_export_schedules_frequency"),
        CheckConstraint("local_hour >= 0 AND local_hour <= 23 AND local_minute >= 0 AND local_minute <= 59", name="ck_export_schedules_local_time"),
        CheckConstraint("(frequency != 'weekly' OR weekday IS NOT NULL) AND (frequency != 'monthly' OR monthday IS NOT NULL)", name="ck_export_schedules_frequency_day"),
        Index("ix_export_schedules_due", "enabled", "next_run_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default="8")
    local_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Taipei", server_default="Asia/Taipei")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ExportRun(Base):
    __tablename__ = "export_runs"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_export_runs_family_id_id"),
        ForeignKeyConstraint(["family_id", "template_id"], ["export_templates.family_id", "export_templates.id"], ondelete="RESTRICT", name="fk_export_runs_family_template"),
        ForeignKeyConstraint(["family_id", "schedule_id"], ["export_schedules.family_id", "export_schedules.id"], ondelete="RESTRICT", name="fk_export_runs_family_schedule"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','revoked')", name="ck_export_runs_status"),
        Index("ix_export_runs_family_created", "family_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
