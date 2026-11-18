from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Bill(Base):
    """家庭應繳帳單主檔；付款與退款由後續階段獨立建模。"""

    __tablename__ = "bills"

    __table_args__ = (
        UniqueConstraint("family_id", "id", name="uq_bills_family_id_id"),
        ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            ondelete="RESTRICT",
            name="fk_bills_family",
        ),
        ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="RESTRICT",
            name="fk_bills_category",
        ),
        ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_bills_created_by",
        ),
        ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_bills_updated_by",
        ),
        ForeignKeyConstraint(
            ["voided_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_bills_voided_by",
        ),
        ForeignKeyConstraint(
            ["recurring_bill_id"],
            ["recurring_bills.id"],
            ondelete="RESTRICT",
            name="fk_bills_recurring_bill",
        ),
        CheckConstraint(
            "(recurring_bill_id IS NULL AND recurring_occurrence_date IS NULL) OR "
            "(recurring_bill_id IS NOT NULL AND recurring_occurrence_date IS NOT NULL)",
            name="ck_bills_recurring_occurrence_pair",
        ),
        Index(
            "uq_bills_recurring_occurrence",
            "recurring_bill_id",
            "recurring_occurrence_date",
            unique=True,
            postgresql_where=text("recurring_bill_id IS NOT NULL"),
        ),
        CheckConstraint("original_amount > 0", name="ck_bills_original_amount_positive"),
        CheckConstraint("tax_amount >= 0", name="ck_bills_tax_amount_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_bills_discount_amount_nonnegative"),
        CheckConstraint(
            "original_amount + tax_amount - discount_amount >= 0",
            name="ck_bills_total_amount_nonnegative",
        ),
        CheckConstraint(
            "(billing_period_start IS NULL AND billing_period_end IS NULL) "
            "OR (billing_period_start IS NOT NULL AND billing_period_end IS NOT NULL "
            "AND billing_period_start <= billing_period_end)",
            name="ck_bills_billing_period_valid",
        ),
        Index("ix_bills_family_bill_date", "family_id", "bill_date"),
        Index("ix_bills_family_due_date", "family_id", "due_date"),
        Index("ix_bills_created_by", "created_by"),
        Index(
            "uq_bills_family_bill_number_active",
            "family_id",
            "bill_number",
            unique=True,
            postgresql_where=text("is_voided = false AND bill_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bill_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recurring_bill_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recurring_occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    original_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0"), server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="TWD", server_default="TWD"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
