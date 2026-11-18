from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OcrTask(Base):
    """OCR 工作佇列；辨識結果僅供人工核對，不會自動建立帳單。"""

    __tablename__ = "ocr_tasks"
    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_ocr_tasks_family_id_id"),
        ForeignKeyConstraint(
            ["family_id", "attachment_id"],
            ["attachments.family_id", "attachments.id"],
            ondelete="RESTRICT",
            name="fk_ocr_tasks_family_attachment",
        ),
        ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_ocr_tasks_family"),
        ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_ocr_tasks_created_by"),
        ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="RESTRICT", name="fk_ocr_tasks_confirmed_by"),
        CheckConstraint("status IN ('queued','processing','succeeded','failed','confirmed')", name="ck_ocr_tasks_status"),
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_ocr_tasks_attempts"),
        Index("ix_ocr_tasks_family_status_created", "family_id", "status", "created_at"),
        Index("ix_ocr_tasks_attachment_created", "family_id", "attachment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attachment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="google_vision", server_default="google_vision")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
