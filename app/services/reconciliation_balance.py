"""Read-only opening/closing balance comparison for reconciliation sessions."""

from decimal import Decimal

ZERO = Decimal("0.0000")


def calculate_reconciliation_balance_check(
    account_type: str,
    opening_balance: Decimal,
    prior_income: Decimal,
    prior_expense: Decimal,
    period_income: Decimal,
    period_expense: Decimal,
    statement_opening_balance: Decimal | None,
    statement_closing_balance: Decimal | None,
) -> dict:
    """Calculate balances using the same sign convention as account_balance.

    Asset accounts are positive assets; credit-card accounts are positive debt.
    Opening-balance transactions form the account baseline and are not period activity.
    """
    if account_type == "credit_card":
        opening_ledger = opening_balance + prior_expense - prior_income
        period_net = period_expense - period_income
    elif account_type in {"bank", "cash", "e_payment"}:
        opening_ledger = opening_balance + prior_income - prior_expense
        period_net = period_income - period_expense
    else:
        raise ValueError(f"Unsupported account type for balance reconciliation: {account_type}")

    closing_ledger = opening_ledger + period_net
    opening_difference = (
        opening_ledger - statement_opening_balance
        if statement_opening_balance is not None else None
    )
    closing_difference = (
        closing_ledger - statement_closing_balance
        if statement_closing_balance is not None else None
    )
    return {
        "opening_balance": opening_ledger,
        "period_income": period_income,
        "period_expense": period_expense,
        "period_net_change": period_net,
        "closing_balance": closing_ledger,
        "statement_opening_balance": statement_opening_balance,
        "statement_closing_balance": statement_closing_balance,
        "opening_difference": opening_difference,
        "closing_difference": closing_difference,
        "opening_matches": opening_difference == ZERO if opening_difference is not None else None,
        "closing_matches": closing_difference == ZERO if closing_difference is not None else None,
    }
