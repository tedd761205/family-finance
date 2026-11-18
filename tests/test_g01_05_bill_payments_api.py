from uuid import uuid4

import pytest


@pytest.fixture
def bill_payment_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from main import app
    from app.database import engine, get_db

    monkeypatch.setenv("JWT_SECRET_KEY", "g01-05-payment-test-secret-key-32-bytes")

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
def ensure_bill_payment_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def seed_permissions():
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.permission import Permission
    from app.permission_catalog import PERMISSION_CATALOG

    with Session(engine) as db:
        existing = {item.code for item in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def setup_family_and_account(client, suffix):
    seed_permissions()
    email = f"g0105-{suffix}@example.com"
    password = "G01-05-payment-test-password-123!"
    registered = client.post("/auth/register", json={
        "email": email, "password": password, "display_name": "G-01-05 付款測試",
    })
    assert registered.status_code == 201, registered.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    family = client.post("/families", headers=headers, json={
        "name": f"G-01-05 付款測試家庭 {suffix}", "currency": "TWD",
    })
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    account = client.post(f"/accounts?family_id={family_id}", headers=headers, json={
        "name": "測試銀行帳戶", "account_type": "bank", "currency_code": "TWD",
    })
    assert account.status_code == 201, account.text
    return headers, family_id, account.json()["id"]


def create_test_bill(client, headers, family_id, number="BILL-001", amount="1000.0000"):
    response = client.post(f"/bills?family_id={family_id}", headers=headers, json={
        "bill_number": number, "title": "測試水電費", "bill_date": "2026-11-01",
        "due_date": "2026-11-30", "original_amount": amount,
        "tax_amount": "0", "discount_amount": "0", "currency_code": "TWD",
    })
    assert response.status_code == 201, response.text
    return response.json()


def payment_payload(bill_id, account_id, amount):
    return {
        "bill_id": bill_id, "account_id": account_id, "amount": amount,
        "currency_code": "TWD", "payment_date": "2026-11-18T10:00:00+08:00",
        "description": "測試帳單付款",
    }


def refund_payload(account_id, amount):
    return {
        "account_id": account_id, "amount": amount, "currency_code": "TWD",
        "payment_date": "2026-11-19T10:00:00+08:00", "description": "測試退款",
    }


def test_partial_payments_refunds_and_bill_balance_are_atomic(bill_payment_client):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.audit_log import AuditLog
    from app.models.bill_payment import BillPayment
    from app.models.transaction import Transaction
    from app.models.account import Account
    from app.services.account_balance import calculate_account_balance
    from decimal import Decimal

    suffix = uuid4().hex
    headers, family_id, account_id = setup_family_and_account(bill_payment_client, suffix)
    bill = create_test_bill(bill_payment_client, headers, family_id)
    bill_id = bill["id"]

    first = bill_payment_client.post(
        f"/bill-payments?family_id={family_id}", headers=headers,
        json=payment_payload(bill_id, account_id, "400.0000"),
    )
    assert first.status_code == 201, first.text
    assert first.json()["payment_type"] == "payment"

    partial = bill_payment_client.get(
        f"/bills/{bill_id}?family_id={family_id}", headers=headers,
    )
    assert partial.status_code == 200
    assert partial.json()["paid_amount"] == "400.0000"
    assert partial.json()["remaining_amount"] == "600.0000"
    assert partial.json()["status"] == "partially_paid"

    second = bill_payment_client.post(
        f"/bill-payments?family_id={family_id}", headers=headers,
        json=payment_payload(bill_id, account_id, "600.0000"),
    )
    assert second.status_code == 201, second.text
    paid = bill_payment_client.get(
        f"/bills/{bill_id}?family_id={family_id}", headers=headers,
    )
    assert paid.json()["paid_amount"] == "1000.0000"
    assert paid.json()["remaining_amount"] == "0.0000"
    assert paid.json()["status"] == "paid"

    overpayment = bill_payment_client.post(
        f"/bill-payments?family_id={family_id}", headers=headers,
        json=payment_payload(bill_id, account_id, "0.0001"),
    )
    assert overpayment.status_code == 409

    refund = bill_payment_client.post(
        f"/bill-payments/{first.json()['id']}/refund?family_id={family_id}",
        headers=headers, json=refund_payload(account_id, "150.0000"),
    )
    assert refund.status_code == 201, refund.text
    assert refund.json()["payment_type"] == "refund"
    assert refund.json()["original_payment_id"] == first.json()["id"]

    after_refund = bill_payment_client.get(
        f"/bills/{bill_id}?family_id={family_id}", headers=headers,
    )
    assert after_refund.json()["paid_amount"] == "850.0000"
    assert after_refund.json()["remaining_amount"] == "150.0000"
    assert after_refund.json()["status"] == "partially_paid"

    excess_refund = bill_payment_client.post(
        f"/bill-payments/{first.json()['id']}/refund?family_id={family_id}",
        headers=headers, json=refund_payload(account_id, "300.0000"),
    )
    assert excess_refund.status_code == 409

    payment_txn = bill_payment_client.get(
        f"/bill-payments/{first.json()['id']}?family_id={family_id}",
        headers=headers,
    )
    assert payment_txn.status_code == 200
    txn_id = payment_txn.json()["transactions"][0]["id"]
    forbidden_edit = bill_payment_client.patch(
        f"/transactions/{txn_id}?family_id={family_id}", headers=headers,
        json={"description": "不允許直接修改"},
    )
    assert forbidden_edit.status_code == 400

    with Session(engine) as db:
        records = db.scalars(select(BillPayment).where(BillPayment.bill_id == bill_id)).all()
        assert len(records) == 3
        transactions = db.scalars(select(Transaction).where(
            Transaction.family_id == family_id,
            Transaction.bill_payment_id.is_not(None),
        )).all()
        assert len(transactions) == 3
        assert sorted(item.transaction_type for item in transactions) == ["expense", "expense", "income"]
        assert all(not item.is_voided for item in transactions)
        account = db.get(Account, account_id)
        balance = calculate_account_balance(db, account)
        assert balance["total_expense"] == Decimal("1000.0000")
        assert balance["total_income"] == Decimal("150.0000")
        assert balance["balance"] == Decimal("-850.0000")
        audit_count = db.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.family_id == family_id,
            AuditLog.entity_type == "bill_payment",
        ))
        assert audit_count == 3

    cannot_void_original = bill_payment_client.delete(
        f"/bill-payments/{first.json()['id']}?family_id={family_id}",
        headers=headers,
    )
    assert cannot_void_original.status_code == 409

    void_refund = bill_payment_client.delete(
        f"/bill-payments/{refund.json()['id']}?family_id={family_id}&reason=refund-correction",
        headers=headers,
    )
    assert void_refund.status_code == 200, void_refund.text

    void_first_payment = bill_payment_client.delete(
        f"/bill-payments/{first.json()['id']}?family_id={family_id}&reason=payment-correction",
        headers=headers,
    )
    assert void_first_payment.status_code == 200, void_first_payment.text

    final_bill = bill_payment_client.get(
        f"/bills/{bill_id}?family_id={family_id}", headers=headers,
    )
    assert final_bill.json()["paid_amount"] == "600.0000"
    assert final_bill.json()["remaining_amount"] == "400.0000"
    with Session(engine) as db:
        account = db.get(Account, account_id)
        balance = calculate_account_balance(db, account)
        assert balance["balance"] == Decimal("-600.0000")


def test_bill_cannot_be_reduced_below_net_paid_or_voided_with_balance(bill_payment_client):
    suffix = uuid4().hex
    headers, family_id, account_id = setup_family_and_account(bill_payment_client, suffix)
    bill = create_test_bill(bill_payment_client, headers, family_id, "BILL-002", "500.0000")
    payment = bill_payment_client.post(
        f"/bill-payments?family_id={family_id}", headers=headers,
        json=payment_payload(bill["id"], account_id, "300.0000"),
    )
    assert payment.status_code == 201, payment.text

    reduce_total = bill_payment_client.patch(
        f"/bills/{bill['id']}?family_id={family_id}", headers=headers,
        json={"original_amount": "200.0000"},
    )
    assert reduce_total.status_code == 409

    void_bill = bill_payment_client.delete(
        f"/bills/{bill['id']}?family_id={family_id}", headers=headers,
    )
    assert void_bill.status_code == 409


def test_payment_rejects_foreign_family_account(bill_payment_client):
    suffix = uuid4().hex
    headers_a, family_a, _ = setup_family_and_account(bill_payment_client, f"{suffix}-a")
    headers_b, family_b, account_b = setup_family_and_account(bill_payment_client, f"{suffix}-b")
    bill = create_test_bill(bill_payment_client, headers_a, family_a, "BILL-FOREIGN")
    response = bill_payment_client.post(
        f"/bill-payments?family_id={family_a}", headers=headers_a,
        json=payment_payload(bill["id"], account_b, "100.0000"),
    )
    assert response.status_code == 404
