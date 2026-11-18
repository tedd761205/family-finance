from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routers.reconciliation import _period_bounds, _row_state
from app.schemas.reconciliation import ReconciliationSessionCreate


def make_row(amount):
    return SimpleNamespace(
        id=10,
        row_number=2,
        transaction_date=datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc),
        transaction_type="expense",
        amount=Decimal(amount),
        currency_code="TWD",
        description="測試銀行扣款",
        external_reference="BANK-001",
    )


def test_reconciliation_period_bounds_use_taipei_calendar_days():
    start, end_exclusive = _period_bounds(date(2026, 11, 1), date(2026, 11, 30))

    assert start == datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
    assert end_exclusive == datetime(2026, 11, 30, 16, 0, tzinfo=timezone.utc)


def test_reconciliation_row_state_is_unmatched_when_no_allocation_exists():
    result = _row_state(make_row("100.0000"), Decimal("0"))

    assert result["reconciliation_status"] == "unmatched"
    assert result["matched_amount"] == "0"
    assert result["remaining_amount"] == "100.0000"


def test_reconciliation_row_state_supports_split_partial_allocation():
    result = _row_state(make_row("3000.0000"), Decimal("2200.0000"))

    assert result["reconciliation_status"] == "partially_matched"
    assert result["matched_amount"] == "2200.0000"
    assert result["remaining_amount"] == "800.0000"


def test_reconciliation_row_state_is_matched_only_when_amounts_are_equal():
    result = _row_state(make_row("3000.0000"), Decimal("3000.0000"))

    assert result["reconciliation_status"] == "matched"
    assert result["remaining_amount"] == "0.0000"


def test_reconciliation_session_schema_accepts_valid_period_and_balances():
    result = ReconciliationSessionCreate(
        account_id=10,
        source_batch_id=20,
        period_start="2026-11-01",
        period_end="2026-11-30",
        opening_balance="-100.0000",
        closing_balance="2900.0000",
    )

    assert result.period_start == date(2026, 11, 1)
    assert result.period_end == date(2026, 11, 30)
    assert result.opening_balance == Decimal("-100.0000")


def test_reconciliation_session_schema_rejects_reversed_period():
    with pytest.raises(ValidationError):
        ReconciliationSessionCreate(
            account_id=10,
            source_batch_id=20,
            period_start="2026-12-01",
            period_end="2026-11-30",
        )


def test_reconciliation_session_schema_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ReconciliationSessionCreate(
            account_id=10,
            source_batch_id=20,
            period_start="2026-11-01",
            period_end="2026-11-30",
            unexpected=True,
        )


def test_reconciliation_session_routes_are_registered():
    from main import app

    routes = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/reconciliations/sessions", "POST") in routes
    assert ("/reconciliations/sessions", "GET") in routes
    assert ("/reconciliations/sessions/{session_id}", "GET") in routes
