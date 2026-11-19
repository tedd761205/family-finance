from decimal import Decimal

import pytest

from app.services.reconciliation_balance import calculate_reconciliation_balance_check


def test_asset_account_balance_check_uses_income_minus_expense():
    result = calculate_reconciliation_balance_check(
        account_type="bank",
        opening_balance=Decimal("1000"),
        prior_income=Decimal("500"),
        prior_expense=Decimal("200"),
        period_income=Decimal("300"),
        period_expense=Decimal("100"),
        statement_opening_balance=Decimal("1300"),
        statement_closing_balance=Decimal("1500"),
    )

    assert result["opening_balance"] == Decimal("1300")
    assert result["period_net_change"] == Decimal("200")
    assert result["closing_balance"] == Decimal("1500")
    assert result["opening_matches"] is True
    assert result["closing_matches"] is True


def test_credit_card_balance_check_uses_expense_minus_income_as_debt():
    result = calculate_reconciliation_balance_check(
        account_type="credit_card",
        opening_balance=Decimal("2000"),
        prior_income=Decimal("300"),
        prior_expense=Decimal("800"),
        period_income=Decimal("100"),
        period_expense=Decimal("600"),
        statement_opening_balance=Decimal("2500"),
        statement_closing_balance=Decimal("3000"),
    )

    assert result["opening_balance"] == Decimal("2500")
    assert result["period_net_change"] == Decimal("500")
    assert result["closing_balance"] == Decimal("3000")
    assert result["opening_matches"] is True
    assert result["closing_matches"] is True


def test_missing_statement_balances_return_null_differences():
    result = calculate_reconciliation_balance_check(
        account_type="cash",
        opening_balance=Decimal("100"),
        prior_income=Decimal("0"),
        prior_expense=Decimal("0"),
        period_income=Decimal("20"),
        period_expense=Decimal("5"),
        statement_opening_balance=None,
        statement_closing_balance=None,
    )

    assert result["opening_difference"] is None
    assert result["closing_difference"] is None
    assert result["opening_matches"] is None
    assert result["closing_matches"] is None


def test_balance_check_rejects_unknown_account_type():
    with pytest.raises(ValueError):
        calculate_reconciliation_balance_check(
            account_type="investment",
            opening_balance=Decimal("0"),
            prior_income=Decimal("0"),
            prior_expense=Decimal("0"),
            period_income=Decimal("0"),
            period_expense=Decimal("0"),
            statement_opening_balance=None,
            statement_closing_balance=None,
        )


def test_balance_check_route_is_registered():
    from main import app

    route = app.openapi()["paths"]["/reconciliations/sessions/{session_id}/balance-check"]
    assert "get" in route
