from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models.audit_log import AuditLog
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.reconciliation import ReconciliationSession
from app.models.transaction import Transaction
from test_g03_02_03_reconciliation_matches import (
    _create_family_account,
    _create_transaction,
    reconciliation_match_client,
)


@pytest.fixture(scope="session", autouse=True)
def ensure_g03_03_06_schema():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def _create_confirmed_batch_and_session(
    client,
    headers,
    family_id,
    account_id,
    user_id,
    *,
    opening_balance=None,
    closing_balance=None,
    include_duplicate=False,
):
    suffix = uuid4().hex
    with Session(engine) as db:
        batch = BankImportBatch(
            family_id=family_id,
            account_id=account_id,
            source_filename=f"g03-03-06-{suffix}.csv",
            status="previewed",
            column_mapping={"date": "日期", "amount": "金額", "description": "摘要"},
            total_rows=2 if include_duplicate else 1,
            ready_rows=1,
            duplicate_rows=1 if include_duplicate else 0,
            invalid_rows=0,
            imported_rows=0,
            created_by=user_id,
        )
        db.add(batch)
        db.flush()
        row = BankImportRow(
            family_id=family_id,
            batch_id=batch.id,
            row_number=2,
            fingerprint="a" * 64,
            transaction_date=datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc),
            transaction_type="expense",
            amount=Decimal("3000.0000"),
            currency_code="TWD",
            description="百貨公司消費",
            external_reference=f"BANK-G030306-{suffix[:12]}",
            raw_data={"日期": "2026-11-05", "金額": "-3000", "摘要": "百貨公司消費"},
            status="ready",
        )
        db.add(row)
        db.flush()
        row_id = row.id
        duplicate_id = None
        if include_duplicate:
            duplicate = BankImportRow(
                family_id=family_id,
                batch_id=batch.id,
                row_number=3,
                fingerprint="b" * 64,
                transaction_date=datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc),
                transaction_type="expense",
                amount=Decimal("3000.0000"),
                currency_code="TWD",
                description="百貨公司消費（疑似重複列）",
                external_reference=f"BANK-G030306-DUP-{suffix[:8]}",
                raw_data={"日期": "2026-11-05", "金額": "-3000", "摘要": "疑似重複列"},
                status="duplicate",
                duplicate_of_row_id=row_id,
            )
            db.add(duplicate)
            db.flush()
            duplicate_id = duplicate.id
        batch_id = batch.id
        db.commit()

    confirmed = client.post(
        f"/imports/batches/{batch_id}/confirm?family_id={family_id}",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["statement_only"] is True
    assert confirmed.json()["created_transaction_count"] == 0

    session_payload = {
        "account_id": account_id,
        "source_batch_id": batch_id,
        "period_start": "2026-11-01",
        "period_end": "2026-11-30",
    }
    if opening_balance is not None:
        session_payload["opening_balance"] = str(opening_balance)
    if closing_balance is not None:
        session_payload["closing_balance"] = str(closing_balance)
    created = client.post(
        f"/reconciliations/sessions?family_id={family_id}",
        headers=headers,
        json=session_payload,
    )
    assert created.status_code == 201, created.text
    return batch_id, row_id, duplicate_id, created.json()["session"]["id"]


def _seed_opening_and_expense(db, family_id, account_id, user_id, *, expense_date):
    opening_id = _create_transaction(
        db, family_id, account_id, user_id, "10000.0000",
        "銀行帳戶期初餘額", transaction_type="opening_balance",
    )
    expense_id = _create_transaction(
        db, family_id, account_id, user_id, "3000.0000",
        "百貨公司消費", transaction_type="expense",
    )
    expense = db.query(Transaction).filter(Transaction.id == expense_id).one()
    expense.transaction_date = expense_date
    db.flush()
    return opening_id, expense_id


def test_full_reconciliation_workflow_matches_excludes_resolves_and_completes(
    reconciliation_match_client,
):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    batch_id, bank_row_id, duplicate_row_id, session_id = _create_confirmed_batch_and_session(
        client,
        headers,
        family_id,
        account_id,
        user_id,
        opening_balance="10000.0000",
        closing_balance="7000.0000",
        include_duplicate=True,
    )
    assert duplicate_row_id is not None

    with Session(engine) as db:
        opening_id, expense_id = _seed_opening_and_expense(
            db,
            family_id,
            account_id,
            user_id,
            expense_date=datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc),
        )
        original_bank_row = db.query(BankImportRow).filter(
            BankImportRow.id == bank_row_id
        ).one()
        original_bank_raw_data = dict(original_bank_row.raw_data)
        original_bank_fingerprint = original_bank_row.fingerprint
        db.commit()

    suggestions = client.post(
        f"/reconciliations/sessions/{session_id}/suggestions?family_id={family_id}",
        headers=headers,
    )
    assert suggestions.status_code == 200, suggestions.text
    suggestion_payload = suggestions.json()
    assert suggestion_payload["automatic_matches_created"] == 0
    suggested_row = next(
        item for item in suggestion_payload["suggestions"]
        if item["bank_import_row"]["id"] == bank_row_id
    )
    assert any(item["transaction_id"] == expense_id for item in suggested_row["candidates"])

    with Session(engine) as db:
        assert db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.account_id == account_id,
        ).count() == 2

    matched = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": bank_row_id,
            "transaction_id": expense_id,
            "allocated_amount": "3000.0000",
        },
    )
    assert matched.status_code == 201, matched.text
    assert matched.json()["bank_row"]["reconciliation_status"] == "matched"
    assert matched.json()["date_difference_days"] == 1

    issue_response = client.post(
        f"/reconciliations/sessions/{session_id}/issues?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": bank_row_id,
            "transaction_id": expense_id,
            "category": "date_mismatch",
            "reason": "銀行入帳日與帳務登錄日相差一天",
        },
    )
    assert issue_response.status_code == 201, issue_response.text
    issue_id = issue_response.json()["issue"]["id"]

    blank_resolution = client.post(
        f"/reconciliations/sessions/{session_id}/issues/{issue_id}/resolve?family_id={family_id}",
        headers=headers,
        json={"resolution_note": "   "},
    )
    assert blank_resolution.status_code == 422

    excluded = client.post(
        f"/reconciliations/sessions/{session_id}/exclude?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": duplicate_row_id,
            "reason": "同一筆銀行明細的疑似重複匯入列，不重複計入",
        },
    )
    assert excluded.status_code == 201, excluded.text
    exclusion_id = excluded.json()["exclusion"]["id"]
    assert excluded.json()["session"]["excluded_row_count"] == 1

    before_resolution = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert before_resolution.status_code == 200, before_resolution.text
    before_payload = before_resolution.json()
    assert before_payload["bank_side"] == {
        "statement_rows": 2,
        "matched_rows": 1,
        "excluded_rows": 1,
        "unresolved_rows": 0,
    }
    assert before_payload["issues"]["open_count"] == 1
    assert before_payload["balance_check"]["opening_matches"] is True
    assert before_payload["balance_check"]["closing_matches"] is True
    assert before_payload["ready_to_complete"] is False
    assert before_payload["completion_blockers"]["open_issues"] == 1

    blocked = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "差異尚未結案，不應允許完成"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["open_issues"] == 1

    resolved = client.post(
        f"/reconciliations/sessions/{session_id}/issues/{issue_id}/resolve?family_id={family_id}",
        headers=headers,
        json={"resolution_note": "已核對銀行交易日與內部登錄日，屬跨日時間差"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["issue"]["status"] == "resolved"

    issue_history = client.get(
        f"/reconciliations/sessions/{session_id}/issues?family_id={family_id}",
        headers=headers,
    )
    assert issue_history.status_code == 200, issue_history.text
    assert issue_history.json()["total"] == 1
    assert issue_history.json()["issues"][0]["resolution_note"] == (
        "已核對銀行交易日與內部登錄日，屬跨日時間差"
    )

    final_report = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert final_report.status_code == 200, final_report.text
    report = final_report.json()
    assert report["bank_side"]["matched_rows"] == 1
    assert report["bank_side"]["excluded_rows"] == 1
    assert report["ledger_side"]["unmatched_transactions"] == 0
    assert report["issues"]["open_count"] == 0
    assert report["issues"]["resolved_count"] == 1
    assert report["balance_check"]["opening_balance"] == "10000.0000"
    assert report["balance_check"]["closing_balance"] == "7000.0000"
    assert report["ready_to_complete"] is True
    assert report["read_only"] is True

    completed = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "銀行明細、帳務交易、差異處理及餘額均已核對"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["session"]["status"] == "completed"
    assert completed.json()["session"]["completed_by"] == user_id

    with Session(engine) as db:
        session = db.query(ReconciliationSession).filter(
            ReconciliationSession.id == session_id
        ).one()
        assert session.statement_row_count == 2
        assert session.matched_row_count == 1
        assert session.excluded_row_count == 1
        assert session.difference_row_count == 0

        transactions = db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.account_id == account_id,
        ).order_by(Transaction.id.asc()).all()
        assert len(transactions) == 2
        assert {item.id for item in transactions} == {opening_id, expense_id}
        assert all(item.is_voided is False for item in transactions)
        assert db.query(AuditLog).filter(
            AuditLog.family_id == family_id,
            AuditLog.entity_type == "reconciliation_issue",
            AuditLog.action == "resolve",
        ).count() == 1
        audited_actions = {
            (item.entity_type, item.action)
            for item in db.query(AuditLog).filter(
                AuditLog.family_id == family_id
            ).all()
        }
        assert ("reconciliation_match", "create") in audited_actions
        assert ("reconciliation_exclusion", "exclude") in audited_actions
        assert ("reconciliation_issue", "create") in audited_actions
        assert ("reconciliation_issue", "resolve") in audited_actions
        assert ("reconciliation_session", "complete") in audited_actions

        unchanged_bank_row = db.query(BankImportRow).filter(
            BankImportRow.id == bank_row_id
        ).one()
        assert unchanged_bank_row.status == "imported"
        assert unchanged_bank_row.raw_data == original_bank_raw_data
        assert unchanged_bank_row.fingerprint == original_bank_fingerprint
        assert unchanged_bank_row.batch_id == batch_id


def test_ledger_only_transaction_must_be_explained_before_completion(
    reconciliation_match_client,
):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, bank_row_id, _, session_id = _create_confirmed_batch_and_session(
        client, headers, family_id, account_id, user_id
    )

    with Session(engine) as db:
        matched_id = _create_transaction(
            db, family_id, account_id, user_id, "3000.0000", "百貨公司消費"
        )
        ledger_only_id = _create_transaction(
            db, family_id, account_id, user_id, "500.0000", "尚待對帳的轉帳紀錄"
        )
        db.commit()

    match = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": bank_row_id,
            "transaction_id": matched_id,
            "allocated_amount": "3000.0000",
        },
    )
    assert match.status_code == 201, match.text

    ledger_only = client.get(
        f"/reconciliations/sessions/{session_id}/ledger-only?family_id={family_id}",
        headers=headers,
    )
    assert ledger_only.status_code == 200, ledger_only.text
    assert ledger_only.json()["total"] == 1
    assert ledger_only.json()["transactions"][0]["id"] == ledger_only_id

    report_before = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert report_before.status_code == 200, report_before.text
    assert report_before.json()["ready_to_complete"] is False
    assert report_before.json()["completion_blockers"]["unmatched_ledger_transactions"] == 1
    assert report_before.json()["balance_check"]["opening_matches"] is None
    assert report_before.json()["balance_check"]["closing_matches"] is None

    issue = client.post(
        f"/reconciliations/sessions/{session_id}/issues?family_id={family_id}",
        headers=headers,
        json={
            "transaction_id": ledger_only_id,
            "category": "ledger_only",
            "reason": "此筆交易尚未出現在本期銀行明細，需保留說明",
        },
    )
    assert issue.status_code == 201, issue.text
    issue_id = issue.json()["issue"]["id"]

    report_open_issue = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert report_open_issue.status_code == 200
    assert report_open_issue.json()["ready_to_complete"] is False
    assert report_open_issue.json()["completion_blockers"]["open_issues"] == 1

    resolved = client.post(
        f"/reconciliations/sessions/{session_id}/issues/{issue_id}/resolve?family_id={family_id}",
        headers=headers,
        json={"resolution_note": "已確認為跨日待入帳，保留紀錄，不另行補建交易"},
    )
    assert resolved.status_code == 200, resolved.text

    report_after = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert report_after.status_code == 200, report_after.text
    assert report_after.json()["ledger_side"]["unmatched_transactions"] == 0
    assert report_after.json()["issues"]["open_count"] == 0
    assert report_after.json()["issues"]["resolved_count"] == 1
    assert report_after.json()["ready_to_complete"] is True

    completed = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "帳務獨有交易已完成差異說明及結案"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["session"]["status"] == "completed"

    with Session(engine) as db:
        assert db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.account_id == account_id,
        ).count() == 2


def test_balance_mismatch_blocks_backend_completion_even_after_bank_row_is_matched(
    reconciliation_match_client,
):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, bank_row_id, _, session_id = _create_confirmed_batch_and_session(
        client,
        headers,
        family_id,
        account_id,
        user_id,
        opening_balance="10000.0000",
        closing_balance="6999.0000",
    )

    with Session(engine) as db:
        _, expense_id = _seed_opening_and_expense(
            db,
            family_id,
            account_id,
            user_id,
            expense_date=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        )
        db.commit()

    match = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": bank_row_id,
            "transaction_id": expense_id,
            "allocated_amount": "3000.0000",
        },
    )
    assert match.status_code == 201, match.text

    report = client.get(
        f"/reconciliations/sessions/{session_id}/final-report?family_id={family_id}",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["balance_check"]["closing_matches"] is False
    assert report.json()["balance_check"]["closing_difference"] == "1.0000"
    assert report.json()["ready_to_complete"] is False
    assert report.json()["completion_blockers"]["balance_mismatch"] is True

    blocked = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "期末餘額不符，不應完成"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["balance_mismatch"] is True

    detail = client.get(
        f"/reconciliations/sessions/{session_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["session"]["status"] == "in_progress"
