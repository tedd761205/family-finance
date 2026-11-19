"""Pure completion gate for reconciliation finalization."""

def evaluate_reconciliation_completion(
    unresolved_bank_rows: int,
    unmatched_ledger_transactions: int,
    open_issues: int,
    opening_balance_matches: bool | None,
    closing_balance_matches: bool | None,
) -> dict:
    balance_mismatch = (
        opening_balance_matches is False or closing_balance_matches is False
    )
    blockers = {
        "unresolved_bank_rows": max(0, unresolved_bank_rows),
        "unmatched_ledger_transactions": max(0, unmatched_ledger_transactions),
        "open_issues": max(0, open_issues),
        "balance_mismatch": balance_mismatch,
    }
    return {
        "ready_to_complete": (
            blockers["unresolved_bank_rows"] == 0
            and blockers["unmatched_ledger_transactions"] == 0
            and blockers["open_issues"] == 0
            and not balance_mismatch
        ),
        "completion_blockers": blockers,
    }
