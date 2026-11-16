
from datetime import datetime

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
        Index("ix_accounts_family_id", "family_id"),
        Index("ix_accounts_created_by", "created_by"),
    )

    # 帳戶 ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # 所屬家庭
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 帳戶名稱
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 帳戶類型：
    # bank / time_deposit / cash / credit_card / e_wallet / other
    account_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # 幣別，例如 TWD、USD、JPY
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )

    # 銀行或金融機構名稱
    institution_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 帳號末四碼（不儲存完整銀行帳號）
    account_number_last4: Mapped[str | None] = mapped_column(
        String(4),
        nullable=True,
    )

    # 信用卡額度
    credit_limit: Mapped[float | None] = mapped_column(
        Numeric(20, 4),
        nullable=True,
    )

    # 信用卡結帳日（1～31）
    statement_day: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # 信用卡繳款截止日（1～31）
    payment_due_day: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # 帳戶備註
    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # 是否啟用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # 建立者
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )

    # 建立時間
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 最後修改時間
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
