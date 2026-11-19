import pytest

from app.services.reconciliation_completion import evaluate_reconciliation_completion


def test_completion_requires_both_sides_and_no_open_issues():
    result = evaluate_reconciliation_completion(
        unresolved_bank_rows=0,
        unmatched_ledger_transactions=0,
        open_issues=0,
        opening_balance_matches=True,
        closing_balance_matches=True,
    )
    assert result["ready_to_complete"] is True
    assert result["completion_blockers"] == {
        "unresolved_bank_rows": 0,
        "unmatched_ledger_transactions": 0,
        "open_issues": 0,
        "balance_mismatch": False,
    }


@pytest.mark.parametrize(
    "kwargs, blocker",
    [
        ({"unresolved_bank_rows": 1}, "unresolved_bank_rows"),
        ({"unmatched_ledger_transactions": 1}, "unmatched_ledger_transactions"),
        ({"open_issues": 1}, "open_issues"),
        ({"opening_balance_matches": False}, "balance_mismatch"),
        ({"closing_balance_matches": False}, "balance_mismatch"),
    ],
)
def test_any_unresolved_item_blocks_completion(kwargs, blocker):
    values = {
        "unresolved_bank_rows": 0,
        "unmatched_ledger_transactions": 0,
        "open_issues": 0,
        "opening_balance_matches": True,
        "closing_balance_matches": True,
    }
    values.update(kwargs)
    result = evaluate_reconciliation_completion(**values)
    assert result["ready_to_complete"] is False
    assert result["completion_blockers"][blocker]


def test_missing_statement_balance_does_not_create_false_mismatch():
    result = evaluate_reconciliation_completion(
        unresolved_bank_rows=0,
        unmatched_ledger_transactions=0,
        open_issues=0,
        opening_balance_matches=None,
        closing_balance_matches=None,
    )
    assert result["ready_to_complete"] is True


def test_final_report_route_is_registered():
    from main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/reconciliations/sessions/{session_id}/final-report"]
