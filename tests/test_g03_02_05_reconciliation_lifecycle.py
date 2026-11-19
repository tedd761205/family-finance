from sqlalchemy.orm import Session

from app.database import engine
from app.models.audit_log import AuditLog
from app.models.reconciliation import ReconciliationExclusion, ReconciliationSession
from app.models.transaction import Transaction
from test_g03_02_03_reconciliation_matches import (
    _create_confirmed_statement,
    _create_family_account,
    _create_transaction,
    reconciliation_match_client,
)


def test_exclude_complete_reopen_and_unexclude_preserve_history(reconciliation_match_client):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, row_id, session_id = _create_confirmed_statement(
        client, headers, family_id, account_id, user_id
    )

    excluded = client.post(
        f"/reconciliations/sessions/{session_id}/exclude?family_id={family_id}",
        headers=headers,
        json={"bank_import_row_id": row_id, "reason": "銀行列為測試用手續費調整，不納入一般交易核對"},
    )
    assert excluded.status_code == 201, excluded.text
    assert excluded.json()["session"]["excluded_row_count"] == 1
    assert excluded.json()["session"]["difference_row_count"] == 0

    detail = client.get(
        f"/reconciliations/sessions/{session_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["rows"][0]["reconciliation_status"] == "excluded"
    exclusion_id = detail.json()["rows"][0]["exclusion"]["id"]

    completed = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "所有明細均已核對或有理由排除"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["session"]["status"] == "completed"
    assert completed.json()["session"]["completed_by"] == user_id

    blocked = client.post(
        f"/reconciliations/sessions/{session_id}/exclusions/{exclusion_id}/void?family_id={family_id}",
        headers=headers,
        json={"reason": "完成後不得直接修改"},
    )
    assert blocked.status_code == 409

    reopened = client.post(
        f"/reconciliations/sessions/{session_id}/reopen?family_id={family_id}",
        headers=headers,
        json={"reason": "收到補充憑證，需要重新核對"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["session"]["status"] == "in_progress"
    assert reopened.json()["session"]["completed_at"] is None

    unexcluded = client.post(
        f"/reconciliations/sessions/{session_id}/exclusions/{exclusion_id}/void?family_id={family_id}",
        headers=headers,
        json={"reason": "確認該筆應納入核對"},
    )
    assert unexcluded.status_code == 200, unexcluded.text
    assert unexcluded.json()["session"]["excluded_row_count"] == 0
    assert unexcluded.json()["session"]["difference_row_count"] == 1

    with Session(engine) as db:
        history = db.query(ReconciliationExclusion).filter(
            ReconciliationExclusion.id == exclusion_id
        ).one()
        audit_actions = {
            item.action for item in db.query(AuditLog).filter(
                AuditLog.family_id == family_id,
                AuditLog.entity_type.in_(["reconciliation_exclusion", "reconciliation_session"]),
            ).all()
        }
    assert history.status == "voided"
    assert history.void_reason == "確認該筆應納入核對"
    assert {"exclude", "complete", "reopen", "void"} <= audit_actions


def test_completion_rejects_unmatched_statement_rows(reconciliation_match_client):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, row_id, session_id = _create_confirmed_statement(
        client, headers, family_id, account_id, user_id
    )

    response = client.post(
        f"/reconciliations/sessions/{session_id}/complete?family_id={family_id}",
        headers=headers,
        json={"reason": "嘗試完成未核對資料"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["difference_row_count"] == 1

    with Session(engine) as db:
        session = db.query(ReconciliationSession).filter(
            ReconciliationSession.id == session_id
        ).one()
        assert session.status == "in_progress"


def test_reconciliation_lifecycle_routes_are_registered():
    from main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/exclude"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/complete"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/reopen"]
    assert "post" in paths["/reconciliations/sessions/{session_id}/exclusions/{exclusion_id}/void"]
