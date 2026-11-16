
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transfer(Base):
    """家庭帳戶間轉帳主檔"""

    __tablename__ = "transfers"

    __table_args__ = (
        Index(
            "ix_transfers_family_id",
            "family_id",
        ),
        Index(
            "ix_transfers_from_account_id",
            "from_account_id",
        ),
        Index(
            "ix_transfers_to_account_id",
            "to_account_id",
        ),
        CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_different_accounts",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_transfers_amount_positive",
        ),
        CheckConstraint(
            "fee_amount >= 0",
            name="ck_transfers_fee_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )

    from_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    to_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 轉帳本金
    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )

    transfer_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 轉帳手續費，獨立於本金
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    # 手續費扣款帳戶
    fee_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    is_voided: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
