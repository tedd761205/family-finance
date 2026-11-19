from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.permission import Permission
from app.models.reconciliation import ReconciliationMatch
from app.models.transaction import Transaction
from app.models.user import User
from app.permission_catalog import PERMISSION_CATALOG
from main import app


@pytest.fixture(scope="session", autouse=True)
def ensure_reconciliation_match_schema():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@pytest.fixture
def reconciliation_match_client(monkeypatch):
    from app.database import get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "g03-02-03-match-test-secret-key-at-least-32-bytes",
    )

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_permissions():
    with Session(engine) as db:
        existing = {item.code for item in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def _create_family_account(client):
    suffix = uuid4().hex
    email = f"g030203-match-{suffix}@example.com"
    password = "G03-02-03-match-test-password-123!"
    _seed_permissions()

    register = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Match Test"},
    )
    assert register.status_code == 201, register.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    family = client.post(
        "/families",
        headers=headers,
        json={"name": f"Match Test Family {suffix}", "currency": "TWD"},
    )
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    account = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={"name": "對帳測試帳戶", "account_type": "bank", "currency_code": "TWD"},
    )
    assert account.status_code == 201, account.text

    with Session(engine) as db:
        user = db.query(User).filter(User.email == email).one()
    return headers, family_id, account.json()["id"], user.id


def _create_confirmed_statement(client, headers, family_id, account_id, user_id):
    with Session(engine) as db:
        batch = BankImportBatch(
            family_id=family_id,
            account_id=account_id,
            source_filename="match-statement.csv",
            status="previewed",
            column_mapping={"date": "日期", "amount": "金額", "description": "摘要"},
            total_rows=1,
            ready_rows=1,
            duplicate_rows=0,
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
            fingerprint="d" * 64,
            transaction_date=datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc),
            transaction_type="expense",
            amount=Decimal("3000.0000"),
            currency_code="TWD",
            description="百貨公司消費",
            external_reference="BANK-MATCH-3000",
            raw_data={"日期": "2026-11-05", "金額": "-3000", "摘要": "百貨公司消費"},
            status="ready",
        )
        db.add(row)
        db.commit()
        batch_id, row_id = batch.id, row.id

    confirmed = client.post(
        f"/imports/batches/{batch_id}/confirm?family_id={family_id}",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["statement_only"] is True

    session = client.post(
        f"/reconciliations/sessions?family_id={family_id}",
        headers=headers,
        json={
            "account_id": account_id,
            "source_batch_id": batch_id,
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
        },
    )
    assert session.status_code == 201, session.text
    return batch_id, row_id, session.json()["session"]["id"]


def _create_transaction(db, family_id, account_id, user_id, amount, description, transaction_type="expense", external_reference=None):
    item = Transaction(
        family_id=family_id,
        account_id=account_id,
        transaction_type=transaction_type,
        amount=Decimal(amount),
        currency_code="TWD",
        transaction_date=datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc),
        description=description,
        external_reference=external_reference,
        created_by=user_id,
    )
    db.add(item)
    db.flush()
    return item.id


def test_one_statement_row_can_match_multiple_transactions_and_be_unmatched_with_audit(
    reconciliation_match_client,
):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, row_id, session_id = _create_confirmed_statement(
        client, headers, family_id, account_id, user_id
    )

    with Session(engine) as db:
        tx1 = _create_transaction(db, family_id, account_id, user_id, "1000.0000", "百貨商品 A")
        tx2 = _create_transaction(db, family_id, account_id, user_id, "2000.0000", "百貨商品 B", external_reference="BANK-MATCH-3000")
        wrong_direction_tx = _create_transaction(
            db, family_id, account_id, user_id, "500.0000", "退款", "income"
        )
        db.commit()

    suggestions = client.post(
        f"/reconciliations/sessions/{session_id}/suggestions?family_id={family_id}",
        headers=headers,
    )
    assert suggestions.status_code == 200, suggestions.text
    suggestion_payload = suggestions.json()
    assert suggestion_payload["automatic_matches_created"] == 0
    candidates = suggestion_payload["suggestions"][0]["candidates"]
    candidate_ids = {item["transaction_id"] for item in candidates}
    assert {tx1, tx2} <= candidate_ids
    assert wrong_direction_tx not in candidate_ids
    exact_reference_candidate = next(item for item in candidates if item["transaction_id"] == tx2)
    assert exact_reference_candidate["confidence"] == "high"
    with Session(engine) as db:
        assert db.query(ReconciliationMatch).filter(
            ReconciliationMatch.session_id == session_id
        ).count() == 0

    wrong_amount = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": row_id,
            "transaction_id": tx1,
            "allocated_amount": "500.0000",
        },
    )
    assert wrong_amount.status_code == 422

    wrong_direction = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": row_id,
            "transaction_id": wrong_direction_tx,
            "allocated_amount": "500.0000",
        },
    )
    assert wrong_direction.status_code == 422

    first = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": row_id,
            "transaction_id": tx1,
            "allocated_amount": "1000.0000",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["bank_row"]["reconciliation_status"] == "partially_matched"
    assert first.json()["bank_row"]["remaining_amount"] == "2000.0000"
    first_match_id = first.json()["match"]["id"]

    duplicate_match = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": row_id,
            "transaction_id": tx1,
            "allocated_amount": "1000.0000",
        },
    )
    assert duplicate_match.status_code == 409

    second = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": row_id,
            "transaction_id": tx2,
            "allocated_amount": "2000.0000",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["bank_row"]["reconciliation_status"] == "matched"
    assert second.json()["bank_row"]["remaining_amount"] == "0.0000"
    second_match_id = second.json()["match"]["id"]
    assert second.json()["session"]["matched_row_count"] == 1
    assert second.json()["session"]["difference_row_count"] == 0

    detail = client.get(
        f"/reconciliations/sessions/{session_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["rows"][0]["reconciliation_status"] == "matched"
    assert len(detail.json()["rows"][0]["matches"]) == 2

    void_first = client.post(
        f"/reconciliations/sessions/{session_id}/matches/{first_match_id}/void?family_id={family_id}",
        headers=headers,
        json={"reason": "第一次配對選錯交易"},
    )
    assert void_first.status_code == 200, void_first.text
    assert void_first.json()["bank_row"]["reconciliation_status"] == "partially_matched"
    assert void_first.json()["session"]["matched_row_count"] == 0
    assert void_first.json()["session"]["difference_row_count"] == 1

    void_second = client.post(
        f"/reconciliations/sessions/{session_id}/matches/{second_match_id}/void?family_id={family_id}",
        headers=headers,
        json={"reason": "取消剩餘配對以重新核對"},
    )
    assert void_second.status_code == 200, void_second.text
    assert void_second.json()["bank_row"]["reconciliation_status"] == "unmatched"
    assert void_second.json()["bank_row"]["remaining_amount"] == "3000.0000"

    with Session(engine) as db:
        matches = db.query(ReconciliationMatch).filter(
            ReconciliationMatch.session_id == session_id
        ).all()
    assert len(matches) == 2
    assert all(item.status == "voided" and item.void_reason for item in matches)
