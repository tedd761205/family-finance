from pydantic import ValidationError
import pytest

from app.schemas.reconciliation import ReconciliationIssueCreate, ReconciliationIssueResolve


def test_bank_only_issue_requires_bank_row():
    issue = ReconciliationIssueCreate(
        bank_import_row_id=12, category="bank_only", reason="銀行已入帳，帳務尚未登錄"
    )
    assert issue.bank_import_row_id == 12
    assert issue.transaction_id is None


def test_ledger_only_issue_requires_transaction():
    issue = ReconciliationIssueCreate(
        transaction_id=20, category="ledger_only", reason="交易尚未出現在銀行對帳單"
    )
    assert issue.transaction_id == 20


@pytest.mark.parametrize("category", ["amount_mismatch", "date_mismatch"])
def test_mismatch_categories_require_both_sources(category):
    with pytest.raises(ValidationError):
        ReconciliationIssueCreate(
            bank_import_row_id=12, category=category, reason="待查"
        )


def test_issue_requires_at_least_one_source():
    with pytest.raises(ValidationError):
        ReconciliationIssueCreate(category="pending", reason="待確認")


def test_issue_reasons_and_resolution_notes_are_trimmed_and_required():
    issue = ReconciliationIssueCreate(
        transaction_id=20, category="pending", reason="  尚待銀行入帳  "
    )
    assert issue.reason == "尚待銀行入帳"
    resolved = ReconciliationIssueResolve(resolution_note="  已確認為跨日入帳  ")
    assert resolved.resolution_note == "已確認為跨日入帳"


def test_issue_routes_are_registered():
    from main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/reconciliations/sessions/{session_id}/issues"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/issues"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/issues/{issue_id}/resolve"]
