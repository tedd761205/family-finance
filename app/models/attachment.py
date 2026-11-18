from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Attachment(Base):
    """家庭帳務附件；檔案本體存放於私有物件儲存。"""

    __tablename__ = "attachments"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_attachments_family_id_id"),
        UniqueConstraint("object_key", name="uq_attachments_object_key"),
        ForeignKeyConstraint(
            ["family_id", "bill_id"],
            ["bills.family_id", "bills.id"],
            ondelete="RESTRICT",
            name="fk_attachments_family_bill",
        ),
        ForeignKeyConstraint(
            ["family_id", "transaction_id"],
            ["transactions.family_id", "transactions.id"],
            ondelete="RESTRICT",
            name="fk_attachments_family_transaction",
        ),
        CheckConstraint(
            "(bill_id IS NOT NULL AND transaction_id IS NULL) OR "
            "(bill_id IS NULL AND transaction_id IS NOT NULL)",
            name="ck_attachments_exactly_one_parent",
        ),
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_attachments_allowed_content_type",
        ),
        CheckConstraint(
            "file_size > 0 AND file_size <= 10485760",
            name="ck_attachments_file_size",
        ),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_attachments_sha256",
        ),
        ForeignKeyConstraint(
            ["family_id"], ["families.id"],
            ondelete="RESTRICT", name="fk_attachments_family",
        ),
        ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_attachments_created_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"], ["users.id"],
            ondelete="RESTRICT", name="fk_attachments_voided_by",
        ),
        Index("ix_attachments_family_bill_created", "family_id", "bill_id", "created_at"),
        Index("ix_attachments_family_transaction_created", "family_id", "transaction_id", "created_at"),
        Index("ix_attachments_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bill_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    is_voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
