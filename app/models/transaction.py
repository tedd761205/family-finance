
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transaction(Base):
    """家庭財務交易紀錄"""

    __tablename__ = "transactions"

    __table_args__ = (
        # 家庭 ID + 帳戶 ID 必須屬於同一家庭
        ForeignKeyConstraint(
            ["family_id", "account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transactions_family_account",
            ondelete="RESTRICT",
        ),

        Index(
            "ix_transactions_family_account_date",
            "family_id",
            "account_id",
            "transaction_date",
        ),
        Index(
            "ix_transactions_created_by",
            "created_by",
        ),
        Index(
            "ix_transactions_transfer_id",
            "transfer_id",
        ),
        Index(
            "ix_transactions_related_transaction_id",
            "related_transaction_id",
        ),
        UniqueConstraint(
            "family_id",
            "id",
            name="uq_transactions_family_id_id",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_transactions_amount_positive",
        ),
    )

    # 交易 ID
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

    # 所屬帳戶
    # 透過複合外鍵與 family_id 一起驗證
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 交易類型
    transaction_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    # 交易金額
    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    # 交易幣別
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )

    # 交易日期
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # 交易說明
    description: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # 收支分類
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 轉帳關聯
    transfer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("transfers.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 相關交易
    related_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 外部參考編號
    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 備註
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 是否作廢
    is_voided: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # 作廢時間
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
