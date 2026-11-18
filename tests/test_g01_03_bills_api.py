from uuid import uuid4

import pytest


@pytest.fixture
def bill_api_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from main import app
    from app.database import engine, get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "g01-03-bills-api-integration-test-secret-key-32-bytes",
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
def ensure_bill_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def seed_bill_permissions():
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


def register_user(client, suffix, label):
    email = f"g0103-{label}-{suffix}@example.com"
    password = "G01-03-bill-test-password-123!"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": f"G-01-03 {label}",
        },
    )
    assert registered.status_code == 201, registered.text
    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return registered.json(), {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }


def create_family(client, headers, suffix):
    response = client.post(
        "/families",
        headers=headers,
        json={"name": f"G-01-03 帳單測試家庭 {suffix}", "currency": "TWD"},
    )
    assert response.status_code == 201, response.text
    return response.json()["family_id"]


def bill_payload(number, title):
    return {
        "bill_number": number,
        "title": title,
        "bill_date": "2026-11-01",
        "billing_period_start": "2026-10-01",
        "billing_period_end": "2026-10-31",
        "due_date": "2026-11-30",
        "original_amount": "1000.0000",
        "tax_amount": "50.0000",
        "discount_amount": "20.0000",
        "currency_code": "TWD",
        "note": "G-01-03 integration test",
    }


def test_bill_api_create_update_void_and_audit(bill_api_client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.audit_log import AuditLog

    seed_bill_permissions()
    suffix = uuid4().hex
    _, headers = register_user(bill_api_client, suffix, "owner")
    family_id = create_family(bill_api_client, headers, suffix)

    created = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=headers,
        json=bill_payload("000123", "測試電費"),
    )
    assert created.status_code == 201, created.text
    bill = created.json()
    bill_id = bill["id"]
    assert bill["bill_number"] == "000123"
    assert bill["total_amount"] == "1030.0000"
    assert bill["status"] == "unpaid"

    updated = bill_api_client.patch(
        f"/bills/{bill_id}?family_id={family_id}",
        headers=headers,
        json={"title": "修改後電費", "discount_amount": "30.0000"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "修改後電費"
    assert updated.json()["total_amount"] == "1020.0000"

    with Session(engine) as db:
        audit = db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity_type == "bill",
                AuditLog.entity_id == bill_id,
                AuditLog.action.in_(["create", "update"]),
            )
        )
        assert audit is not None

    voided = bill_api_client.delete(
        f"/bills/{bill_id}?family_id={family_id}&reason=duplicate",
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["bill"]["status"] == "voided"
    assert voided.json()["bill"]["void_reason"] == "duplicate"

    active = bill_api_client.get(
        f"/bills?family_id={family_id}", headers=headers,
    )
    assert active.status_code == 200
    assert active.json()["total"] == 0

    history = bill_api_client.get(
        f"/bills?family_id={family_id}&include_voided=true", headers=headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["bills"][0]["status"] == "voided"


def test_bill_api_own_scope_isolates_member_records(bill_api_client):
    suffix = uuid4().hex
    _, owner_headers = register_user(bill_api_client, suffix, "scope-owner")
    invitee, invitee_headers = register_user(
        bill_api_client, suffix, "scope-member",
    )
    family_id = create_family(bill_api_client, owner_headers, suffix)

    invited = bill_api_client.post(
        f"/families/{family_id}/members",
        headers=owner_headers,
        json={"email": invitee["email"]},
    )
    assert invited.status_code == 201, invited.text

    owner_bill = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=owner_headers,
        json=bill_payload("OWNER-001", "管理員帳單"),
    )
    assert owner_bill.status_code == 201, owner_bill.text

    member_list = bill_api_client.get(
        f"/bills?family_id={family_id}", headers=invitee_headers,
    )
    assert member_list.status_code == 200
    assert member_list.json()["total"] == 0

    hidden = bill_api_client.get(
        f"/bills/{owner_bill.json()['id']}?family_id={family_id}",
        headers=invitee_headers,
    )
    assert hidden.status_code == 404

    member_bill = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=invitee_headers,
        json=bill_payload("MEMBER-001", "成員自己的帳單"),
    )
    assert member_bill.status_code == 201, member_bill.text

    own_list = bill_api_client.get(
        f"/bills?family_id={family_id}", headers=invitee_headers,
    )
    assert own_list.status_code == 200
    assert own_list.json()["total"] == 1
    assert own_list.json()["bills"][0]["id"] == member_bill.json()["id"]


def test_bill_api_rejects_category_from_another_family(bill_api_client):
    seed_bill_permissions()
    suffix = uuid4().hex
    _, first_headers = register_user(bill_api_client, suffix, "first-family")
    _, second_headers = register_user(bill_api_client, suffix, "second-family")
    first_family_id = create_family(bill_api_client, first_headers, f"{suffix}-one")
    second_family_id = create_family(bill_api_client, second_headers, f"{suffix}-two")

    foreign_category = bill_api_client.post(
        f"/categories?family_id={second_family_id}",
        headers=second_headers,
        json={"category_type": "expense", "name": f"外家庭分類-{suffix}"},
    )
    assert foreign_category.status_code == 201, foreign_category.text

    rejected = bill_api_client.post(
        f"/bills?family_id={first_family_id}",
        headers=first_headers,
        json={
            **bill_payload("FOREIGN-CATEGORY-001", "跨家庭分類測試"),
            "category_id": foreign_category.json()["id"],
        },
    )
    assert rejected.status_code == 404


def test_bill_number_can_be_reused_only_after_previous_bill_is_voided(bill_api_client):
    seed_bill_permissions()
    suffix = uuid4().hex
    _, headers = register_user(bill_api_client, suffix, "number-owner")
    family_id = create_family(bill_api_client, headers, suffix)

    first = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=headers,
        json=bill_payload("SAME-NUMBER", "第一張帳單"),
    )
    assert first.status_code == 201, first.text

    duplicate = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=headers,
        json=bill_payload("SAME-NUMBER", "重複帳單"),
    )
    assert duplicate.status_code == 409

    voided = bill_api_client.delete(
        f"/bills/{first.json()['id']}?family_id={family_id}",
        headers=headers,
    )
    assert voided.status_code == 200

    reused = bill_api_client.post(
        f"/bills?family_id={family_id}",
        headers=headers,
        json=bill_payload("SAME-NUMBER", "作廢後重用編號"),
    )
    assert reused.status_code == 201, reused.text
