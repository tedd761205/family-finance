"""preserve bill and account currencies for cross-currency payments

Revision ID: f5b7d9e1a3c5
Revises: f2a4c6e8b0d2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5b7d9e1a3c5"
down_revision: Union[str, Sequence[str], None] = "f2a4c6e8b0d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bill_payments", sa.Column("account_amount", sa.Numeric(20, 4), nullable=True))
    op.add_column("bill_payments", sa.Column("account_currency_code", sa.String(3), nullable=True))
    op.add_column(
        "bill_payments",
        sa.Column("exchange_rate", sa.Numeric(20, 10), server_default="1", nullable=False),
    )
    op.add_column(
        "bill_payments",
        sa.Column("exchange_difference", sa.Numeric(20, 4), server_default="0", nullable=False),
    )

    # Existing records were restricted to same-currency payments. Preserve them exactly.
    op.execute(sa.text("""
        UPDATE bill_payments AS payment
        SET account_amount = COALESCE(
                (SELECT transaction.amount
                 FROM transactions AS transaction
                 WHERE transaction.family_id = payment.family_id
                   AND transaction.bill_payment_id = payment.id),
                payment.amount
            ),
            account_currency_code = COALESCE(
                (SELECT transaction.currency_code
                 FROM transactions AS transaction
                 WHERE transaction.family_id = payment.family_id
                   AND transaction.bill_payment_id = payment.id),
                account.currency_code
            ),
            exchange_rate = 1,
            exchange_difference = 0
        FROM accounts AS account
        WHERE account.family_id = payment.family_id
          AND account.id = payment.account_id
    """))

    op.alter_column("bill_payments", "account_amount", nullable=False)
    op.alter_column("bill_payments", "account_currency_code", nullable=False)

    op.create_check_constraint(
        "ck_bill_payments_account_amount_positive",
        "bill_payments",
        "account_amount > 0",
    )
    op.create_check_constraint(
        "ck_bill_payments_exchange_rate_positive",
        "bill_payments",
        "exchange_rate > 0",
    )
    op.create_check_constraint(
        "ck_bill_payments_account_currency_code",
        "bill_payments",
        "account_currency_code ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        "ck_bill_payments_payment_exchange_difference_zero",
        "bill_payments",
        "payment_type = 'refund' OR exchange_difference = 0",
    )
    op.create_check_constraint(
        "ck_bill_payments_same_currency_consistent",
        "bill_payments",
        "currency_code <> account_currency_code OR "
        "(exchange_rate = 1 AND account_amount = amount AND exchange_difference = 0)",
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_cross_currency_records = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM bill_payments
            WHERE currency_code <> account_currency_code
               OR exchange_rate <> 1
               OR exchange_difference <> 0
        )
    """)).scalar_one()
    if has_cross_currency_records:
        raise RuntimeError(
            "Cannot downgrade cross-currency bill payments while converted payment records exist; "
            "restore from a verified backup or write a separately reviewed data-preserving migration."
        )

    op.drop_constraint("ck_bill_payments_same_currency_consistent", "bill_payments", type_="check")
    op.drop_constraint("ck_bill_payments_payment_exchange_difference_zero", "bill_payments", type_="check")
    op.drop_constraint("ck_bill_payments_account_currency_code", "bill_payments", type_="check")
    op.drop_constraint("ck_bill_payments_exchange_rate_positive", "bill_payments", type_="check")
    op.drop_constraint("ck_bill_payments_account_amount_positive", "bill_payments", type_="check")
    op.drop_column("bill_payments", "exchange_difference")
    op.drop_column("bill_payments", "exchange_rate")
    op.drop_column("bill_payments", "account_currency_code")
    op.drop_column("bill_payments", "account_amount")
