
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    """家庭財務交易紀錄"""

    __tablename__ = "transactions"

    __table_args__ = (
        ForeignKeyConstraint(
            ["family_id", "account_id"],
            ["accounts.family_id", "accounts.id"],
            name="fk_transactions_family_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["family_id", "transfer_id"],
            ["transfers.family_id", "transfers.id"],
            name="fk_transactions_family_transfer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["family_id", "related_transaction_id"],
            ["transactions.family_id", "transactions.id"],
            name="fk_transactions_family_related_transaction",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["family_id", "credit_card_payment_id"],
            ["credit_card_payments.family_id", "credit_card_payments.id"],
            name="fk_transactions_family_credit_card_payment",
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
        Index(
            "ix_transactions_credit_card_payment_id",
            "credit_card_payment_id",
        ),
        Index(
            "uq_transactions_active_opening_balance",
            "family_id",
            "account_id",
            unique=True,
            postgresql_where=text(
                "transaction_type = 'opening_balance' "
                "AND is_voided = false"
            ),
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

    account_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

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

    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )

    transfer_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    related_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    credit_card_payment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_voided: Mapped[bool] = mapped_column(
        Boolean,
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

    # 所屬帳戶
    account = relationship(
        "Account",
        foreign_keys=[family_id, account_id],
        viewonly=True,
    )
