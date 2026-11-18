from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.bill import calculate_bill_total, get_bill_status, bill_to_dict


def make_bill(**overrides):
    values = {
        "id": 1,
        "family_id": 10,
        "bill_number": "000123",
        "title": "測試電費",
        "category_id": None,
        "bill_date": date(2026, 11, 1),
        "billing_period_start": date(2026, 10, 1),
        "billing_period_end": date(2026, 10, 31),
        "due_date": date(2026, 11, 20),
        "original_amount": Decimal("1000.0000"),
        "tax_amount": Decimal("50.0000"),
        "discount_amount": Decimal("20.0000"),
        "currency_code": "TWD",
        "note": None,
        "is_voided": False,
        "voided_at": None,
        "voided_by": None,
        "void_reason": None,
        "created_by": 1,
        "updated_by": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_bill_total_preserves_decimal_precision():
    assert calculate_bill_total(make_bill()) == Decimal("1030.0000")


def test_bill_status_is_unpaid_before_due_date():
    assert get_bill_status(make_bill(), as_of=date(2026, 11, 18)) == "unpaid"


def test_bill_status_becomes_overdue_after_due_date():
    assert get_bill_status(make_bill(due_date=date(2026, 11, 17)), as_of=date(2026, 11, 18)) == "overdue"


def test_bill_status_supports_partial_and_full_payment_for_future_phase():
    bill = make_bill()
    assert get_bill_status(bill, Decimal("500.0000"), date(2026, 11, 18)) == "partially_paid"
    assert get_bill_status(bill, Decimal("1030.0000"), date(2026, 11, 18)) == "paid"


def test_voided_bill_status_has_highest_priority():
    bill = make_bill(is_voided=True, due_date=date(2026, 11, 1))
    assert get_bill_status(bill, Decimal("100.0000"), date(2026, 11, 18)) == "voided"


def test_bill_response_calculates_remaining_amount():
    result = bill_to_dict(make_bill(), Decimal("250.0000"), date(2026, 11, 18))
    assert result["total_amount"] == Decimal("1030.0000")
    assert result["paid_amount"] == Decimal("250.0000")
    assert result["remaining_amount"] == Decimal("780.0000")


def test_bill_status_paid_amount_is_capped_at_total():
    result = bill_to_dict(make_bill(), Decimal("1200.0000"), date(2026, 11, 18))
    assert result["paid_amount"] == Decimal("1030.0000")
    assert result["remaining_amount"] == Decimal("0")


def test_bill_status_negative_paid_amount_is_treated_as_zero():
    result = bill_to_dict(make_bill(), Decimal("-1.0000"), date(2026, 11, 18))
    assert result["paid_amount"] == Decimal("0")
    assert result["remaining_amount"] == Decimal("1030.0000")
