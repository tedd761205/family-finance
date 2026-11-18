from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecurringBill(Base):
    """週期性帳單規則；產生的每期帳單獨立保存於 bills。"""
    __tablename__ = "recurring_bills"
    __table_args__ = (
        ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT", name="fk_recurring_bills_family"),
        ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT", name="fk_recurring_bills_category"),
        ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_recurring_bills_created_by"),
        ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_recurring_bills_updated_by"),
        CheckConstraint("frequency IN ('weekly', 'monthly', 'yearly')", name="ck_recurring_bills_frequency"),
        CheckConstraint("interval_count >= 1", name="ck_recurring_bills_interval_positive"),
        CheckConstraint("original_amount > 0 AND tax_amount >= 0 AND discount_amount >= 0", name="ck_recurring_bills_amounts"),
        CheckConstraint("original_amount + tax_amount - discount_amount >= 0", name="ck_recurring_bills_total_nonnegative"),
        CheckConstraint("due_days_after >= 0 AND due_days_after <= 365", name="ck_recurring_bills_due_days"),
        CheckConstraint("(end_date IS NULL OR end_date >= start_date)", name="ck_recurring_bills_date_range"),
        Index("ix_recurring_bills_family_active", "family_id", "is_active"),
        Index("ix_recurring_bills_next_run", "next_run_date", postgresql_where=__import__("sqlalchemy").text("is_active = true")),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    interval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_days_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    original_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal("0"), server_default="0")
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal("0"), server_default="0")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TWD", server_default="TWD")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
