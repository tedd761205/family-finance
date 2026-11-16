
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Account(Base):
    """家庭財務帳戶"""

    __tablename__ = "accounts"

    __table_args__ = (
        Index(
            "ix_accounts_family_id",
            "family_id",
        ),
        Index(
            "ix_accounts_created_by",
            "created_by",
        ),
        # 家庭與帳戶 ID 複合唯一約束
        UniqueConstraint(
            "family_id",
            "id",
            name="uq_accounts_family_id_id",
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

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    account_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )

    institution_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    account_number_last4: Mapped[str | None] = mapped_column(
        String(4),
        nullable=True,
    )

    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    statement_day: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    payment_due_day: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
