from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.monthly_report import calculate_monthly_summary


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def options(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args, **kwargs):
        return FakeQuery(self.rows)


def transaction(
    transaction_type, amount, currency, occurred_at, *,
    account_type="bank", credit_card_payment_id=None,
    transfer_id=None, related_transaction_id=None,
):
    return SimpleNamespace(
        transaction_type=transaction_type,
        amount=Decimal(amount),
        currency_code=currency,
        transaction_date=occurred_at,
        account=SimpleNamespace(account_type=account_type),
        credit_card_payment_id=credit_card_payment_id,
        transfer_id=transfer_id,
        related_transaction_id=related_transaction_id,
    )


def test_monthly_report_groups_daily_rows_by_taiwan_date_and_currency():
    rows = [
        transaction("income", "100.00", "TWD", datetime(2026, 11, 1, 16, 30, tzinfo=timezone.utc)),
        transaction("expense", "30.00", "TWD", datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)),
        transaction("income", "10.00", "USD", datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)),
        transaction("expense", "5.00", "TWD", datetime(2026, 11, 1, 18, 30, tzinfo=timezone.utc), transfer_id=9),
        transaction("expense", "200.00", "TWD", datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc), transfer_id=9, related_transaction_id=19),
        transaction("opening_balance", "500.00", "TWD", datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)),
        transaction("income", "20.00", "TWD", datetime(2026, 11, 1, 21, 0, tzinfo=timezone.utc), account_type="credit_card"),
        transaction("expense", "90.00", "TWD", datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc), credit_card_payment_id=33),
    ]

    result = calculate_monthly_summary(FakeDB(rows), family_id=7, year=2026, month=11)

    assert result["daily_reports"] == [
        {
            "report_date": "2026-11-02",
            "currency_code": "TWD",
            "total_income": Decimal("100.00"),
            "total_expense": Decimal("35.00"),
            "net_amount": Decimal("65.00"),
            "transaction_count": 3,
        },
        {
            "report_date": "2026-11-02",
            "currency_code": "USD",
            "total_income": Decimal("10.00"),
            "total_expense": Decimal("0.0000"),
            "net_amount": Decimal("10.0000"),
            "transaction_count": 1,
        },
    ]
    assert result["transaction_count"] == 4

    assert result["total_income"] == [
        {"currency_code": "TWD", "amount": Decimal("100.00")},
        {"currency_code": "USD", "amount": Decimal("10.00")},
    ]
    assert result["total_expense"] == [
        {"currency_code": "TWD", "amount": Decimal("35.00")},
        {"currency_code": "USD", "amount": Decimal("0.0000")},
    ]
