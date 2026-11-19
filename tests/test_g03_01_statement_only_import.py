from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.transaction import Transaction
from app.models.user import User
from app.models.permission import Permission
from app.permission_catalog import PERMISSION_CATALOG
from main import app


@pytest.fixture(scope="session", autouse=True)
def ensure_statement_import_schema():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@pytest.fixture
def statement_import_client(monkeypatch):
    from app.database import get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "g03-01-statement-only-test-secret-key-32-bytes",
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


def seed_permissions():
    with Session(engine) as db:
        existing = {row.code for row in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def create_user_family_account(client):
    suffix = uuid4().hex
    email = f"g0301-statement-{suffix}@example.com"
    password = "G03-01-statement-test-password-123!"
    seed_permissions()

    registered = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "G-03-01 Statement Test"},
    )
    assert registered.status_code == 201, registered.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    family = client.post(
        "/families",
        headers=headers,
        json={"name": f"G-03-01 Statement Family {suffix}", "currency": "TWD"},
    )
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    account = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={
            "name": "測試銀行帳戶",
            "account_type": "bank",
            "currency_code": "TWD",
            "institution_name": "測試銀行",
        },
    )
    assert account.status_code == 201, account.text

    with Session(engine) as db:
        user = db.query(User).filter(User.email == email).one()

    return headers, family_id, account.json()["id"], user.id


def create_preview_batch(family_id, account_id, user_id):
    with Session(engine) as db:
        batch = BankImportBatch(
            family_id=family_id,
            account_id=account_id,
            source_filename="statement.csv",
            status="previewed",
            column_mapping={"date": "日期", "amount": "金額", "description": "摘要"},
            total_rows=3,
            ready_rows=1,
            duplicate_rows=1,
            invalid_rows=1,
            imported_rows=0,
            created_by=user_id,
        )
        db.add(batch)
        db.flush()

        ready = BankImportRow(
            family_id=family_id,
            batch_id=batch.id,
            row_number=2,
            fingerprint="a" * 64,
            transaction_date=datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc),
            transaction_type="expense",
            amount=Decimal("100.0000"),
            currency_code="TWD",
            description="超商消費",
            external_reference="REF-READY",
            raw_data={"日期": "2026-11-05", "金額": "-100", "摘要": "超商消費"},
            status="ready",
        )
        db.add(ready)
        db.flush()

        duplicate = BankImportRow(
            family_id=family_id,
            batch_id=batch.id,
            row_number=3,
            fingerprint="b" * 64,
            transaction_date=datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc),
            transaction_type="expense",
            amount=Decimal("200.0000"),
            currency_code="TWD",
            description="疑似重複扣款",
            external_reference="REF-DUP",
            raw_data={"日期": "2026-11-06", "金額": "-200", "摘要": "疑似重複扣款"},
            status="duplicate",
            duplicate_of_row_id=ready.id,
            error_message="與既有匯入資料重複",
        )
        invalid = BankImportRow(
            family_id=family_id,
            batch_id=batch.id,
            row_number=4,
            fingerprint="c" * 64,
            transaction_date=None,
            transaction_type=None,
            amount=None,
            currency_code=None,
            description=None,
            external_reference=None,
            raw_data={"日期": "bad", "金額": "bad"},
            status="invalid",
            error_message="日期格式無法辨識",
        )
        db.add_all([duplicate, invalid])
        db.commit()
        return batch.id, ready.id, duplicate.id, invalid.id


def test_confirm_defaults_to_statement_only_and_reconciliation_includes_duplicates(
    statement_import_client,
):
    client = statement_import_client
    headers, family_id, account_id, user_id = create_user_family_account(client)
    batch_id, ready_id, duplicate_id, invalid_id = create_preview_batch(
        family_id, account_id, user_id
    )

    confirmed = client.post(
        f"/imports/batches/{batch_id}/confirm?family_id={family_id}",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["statement_only"] is True
    assert payload["created_transaction_count"] == 0
    assert payload["batch"]["status"] == "confirmed"
    assert payload["batch"]["ready_rows"] == 0
    assert payload["batch"]["duplicate_rows"] == 1
    assert payload["batch"]["imported_rows"] == 2

    with Session(engine) as db:
        rows = {
            row.id: row.status
            for row in db.query(BankImportRow).filter(
                BankImportRow.id.in_([ready_id, duplicate_id, invalid_id])
            ).all()
        }
        created_transactions = db.query(Transaction.id).filter(
            Transaction.family_id == family_id,
            Transaction.import_row_id.in_([ready_id, duplicate_id]),
        ).count()
    assert rows == {
        ready_id: "imported",
        duplicate_id: "duplicate",
        invalid_id: "invalid",
    }
    assert created_transactions == 0

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
    session_id = session.json()["session"]["id"]
    assert session.json()["session"]["statement_row_count"] == 2

    detail = client.get(
        f"/reconciliations/sessions/{session_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["total_rows"] == 2
    assert {row["id"] for row in detail.json()["rows"]} == {ready_id, duplicate_id}
    assert all(row["reconciliation_status"] == "unmatched" for row in detail.json()["rows"])


def test_confirm_can_explicitly_create_transactions_when_requested(statement_import_client):
    client = statement_import_client
    headers, family_id, account_id, user_id = create_user_family_account(client)
    batch_id, ready_id, duplicate_id, _ = create_preview_batch(
        family_id, account_id, user_id
    )

    confirmed = client.post(
        f"/imports/batches/{batch_id}/confirm?family_id={family_id}&create_transactions=true",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["statement_only"] is False
    assert payload["created_transaction_count"] == 1
    assert len(payload["transaction_ids"]) == 1

    with Session(engine) as db:
        rows = {
            row.id: row.status
            for row in db.query(BankImportRow).filter(
                BankImportRow.id.in_([ready_id, duplicate_id])
            ).all()
        }
        transactions = db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.import_row_id.in_([ready_id, duplicate_id]),
        ).all()
    assert rows == {ready_id: "imported", duplicate_id: "duplicate"}
    assert len(transactions) == 1
    assert transactions[0].import_row_id == ready_id
