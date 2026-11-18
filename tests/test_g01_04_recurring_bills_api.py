from uuid import uuid4

import pytest


@pytest.fixture
def recurring_bill_api_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from main import app
    from app.database import engine, get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "g01-04-recurring-api-test-secret-key-32-bytes",
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


@pytest.fixture(scope="session", autouse=True)
def ensure_recurring_bill_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def seed_recurring_permissions():
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.permission import Permission
    from app.permission_catalog import PERMISSION_CATALOG

    with Session(engine) as db:
        existing = {row.code for row in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def register_recurring_user(client, suffix):
    email = f"g0104-recurring-{suffix}@example.com"
    password = "G01-04-recurring-test-password-123!"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": "G-01-04 定期帳單測試",
        },
    )
    assert registered.status_code == 201, registered.text
    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }


def test_recurring_bill_api_create_generate_idempotently_and_deactivate(
    recurring_bill_api_client,
):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.audit_log import AuditLog
    from app.models.bill import Bill

    seed_recurring_permissions()
    suffix = uuid4().hex
    headers = register_recurring_user(recurring_bill_api_client, suffix)

    family = recurring_bill_api_client.post(
        "/families",
        headers=headers,
        json={"name": f"G-01-04 定期帳單家庭 {suffix}", "currency": "TWD"},
    )
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    created = recurring_bill_api_client.post(
        f"/recurring-bills?family_id={family_id}",
        headers=headers,
        json={
            "title": "每月電費",
            "frequency": "monthly",
            "interval_count": 1,
            "start_date": "2026-11-01",
            "end_date": "2027-01-01",
            "original_amount": "1200.0000",
            "tax_amount": "0",
            "discount_amount": "0",
            "currency_code": "TWD",
            "due_days_after": 10,
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    rule_id = rule["id"]
    assert rule["next_run_date"] == "2026-11-01"

    generated = recurring_bill_api_client.post(
        f"/recurring-bills/{rule_id}/generate?family_id={family_id}&through_date=2026-12-01",
        headers=headers,
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["generated_count"] == 2
    assert generated.json()["next_run_date"] == "2027-01-01"

    repeated = recurring_bill_api_client.post(
        f"/recurring-bills/{rule_id}/generate?family_id={family_id}&through_date=2026-12-01",
        headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["generated_count"] == 0

    with Session(engine) as db:
        bills = db.scalars(
            select(Bill).where(
                Bill.family_id == family_id,
                Bill.recurring_bill_id == rule_id,
            )
        ).all()
        assert len(bills) == 2
        assert {bill.recurring_occurrence_date.isoformat() for bill in bills} == {
            "2026-11-01",
            "2026-12-01",
        }
        assert all(bill.due_date.isoformat().endswith("-11") for bill in bills)
        audit_count = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.family_id == family_id,
                AuditLog.entity_type == "recurring_bill",
                AuditLog.entity_id == rule_id,
            )
        )
        assert audit_count >= 2

    deactivated = recurring_bill_api_client.delete(
        f"/recurring-bills/{rule_id}?family_id={family_id}",
        headers=headers,
    )
    assert deactivated.status_code == 200, deactivated.text

    after_deactivation = recurring_bill_api_client.post(
        f"/recurring-bills/{rule_id}/generate?family_id={family_id}&through_date=2027-02-01",
        headers=headers,
    )
    assert after_deactivation.status_code == 200, after_deactivation.text
    assert after_deactivation.json()["generated_count"] == 0
