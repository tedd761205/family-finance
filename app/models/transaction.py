
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
        # 家庭、帳戶、交易日期查詢
        Index(
            "ix_transactions_family_account_date",
            "family_id",
            "account_id",
            "transaction_date",
        ),

        # 建立者查詢
        Index(
            "ix_transactions_created_by",
            "created_by",
        ),

        # 轉帳關聯查詢
        Index(
            "ix_transactions_transfer_id",
            "transfer_id",
        ),

        # 相關交易查詢
        Index(
            "ix_transactions_related_transaction_id",
            "related_transaction_id",
        ),

        # 家庭內交易編號唯一
        UniqueConstraint(
            "family_id",
            "id",
            name="uq_transactions_family_id_id",
        ),

        # 金額必須大於零
        CheckConstraint(
            "amount > 0",
            name="ck_transactions_amount_positive",
        ),

        # 作廢狀態
        CheckConstraint(
            "is_voided IN (true, false)",
            name="ck_transactions_is_voided_boolean",
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
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 交易類型
    # income / expense
    # transfer_in / transfer_out
    # credit_card_purchase / credit_card_payment
    # opening_balance / adjustment
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

    # 支出或收入分類 ID
    # 後續 categories 資料表完成後再建立外鍵
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # 轉帳關聯 ID
    # 同一筆轉帳的轉出與轉入紀錄使用相同 ID
    transfer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # 關聯交易 ID
    # 例如退款、沖銷、信用卡繳款關聯
    related_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # 外部參考編號
    # 例如銀行匯入交易編號
    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 備註
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 是否已作廢
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
