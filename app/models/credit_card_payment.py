
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


class CreditCardPayment(Base):
    """
    信用卡繳款主檔

    一筆信用卡繳款會對應兩筆交易：
    1. 來源帳戶：expense（資產減少）
    2. 信用卡帳戶：income（信用卡負債減少）

    兩筆交易透過 credit_card_payment_id 關聯。
    """

    __tablename__ = "credit_card_payments"

    __table_args__ = (
        # 確保來源帳戶屬於同一家庭
        ForeignKeyConstraint(
            ["family_id", "from_account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_credit_card_payments_from_account",
        ),

        # 確保目標信用卡帳戶屬於同一家庭
        ForeignKeyConstraint(
            ["family_id", "credit_card_account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_credit_card_payments_credit_card_account",
        ),

        UniqueConstraint(
            "family_id",
            "id",
            name="uq_credit_card_payments_family_id_id",
        ),

        CheckConstraint(
            "from_account_id <> credit_card_account_id",
            name="ck_credit_card_payments_different_accounts",
        ),

        CheckConstraint(
            "amount > 0",
            name="ck_credit_card_payments_amount_positive",
        ),

        Index(
            "ix_credit_card_payments_family_date",
            "family_id",
            "payment_date",
        ),

        Index(
            "ix_credit_card_payments_from_account",
            "from_account_id",
        ),

        Index(
            "ix_credit_card_payments_credit_card_account",
            "credit_card_account_id",
        ),

        Index(
            "ix_credit_card_payments_created_by",
            "created_by",
        ),
    )

    # =====================================================
    # 主鍵與家庭
    # =====================================================

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id"),
        nullable=False,
    )

    # =====================================================
    # 帳戶關聯
    # =====================================================

    from_account_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    credit_card_account_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # =====================================================
    # 繳款資料
    # =====================================================

    amount: Mapped[float] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )

    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    payment_date: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # =====================================================
    # 作廢管理
    # =====================================================

    is_voided: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    voided_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =====================================================
    # 建立者與時間
    # =====================================================

    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
