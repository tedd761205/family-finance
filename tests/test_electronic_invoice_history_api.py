from uuid import uuid4

import pytest


@pytest.fixture
def invoice_api_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from main import app
    from app.database import engine, get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "electronic-invoice-api-test-secret-key-32-bytes-minimum",
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


@pytest.fixture(scope="module", autouse=True)
def ensure_electronic_invoice_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def seed_invoice_permissions():
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


def register_user(client, label):
    suffix = uuid4().hex
    email = f"einvoice-{label}-{suffix}@example.com"
    password = "EInvoice-test-password-123!"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": f"電子發票測試 {label}",
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


def create_family(client, headers):
    suffix = uuid4().hex
    response = client.post(
        "/families",
        headers=headers,
        json={"name": f"電子發票測試家庭 {suffix}", "currency": "TWD"},
    )
    assert response.status_code == 201, response.text
    return response.json()["family_id"]


def sample_invoice(number="AB12345678", date="2026-11-27", **overrides):
    invoice = {
        "invoice_date": date,
        "invoice_number": number,
        "merchant_tax_id": "12345678",
        "merchant_name": "全聯福利中心",
        "total_amount": "100.00",
        "invoice_status": "已開立",
        "carrier_type": "手機條碼",
        "duplicate_in_source": False,
        "items": [
            {"item_name": "鮮乳", "amount": "120.00"},
            {"item_name": "折扣", "amount": "-20.00"},
        ],
    }
    invoice.update(overrides)
    return invoice


def test_invoice_import_is_persistent_idempotent_searchable_and_audited(invoice_api_client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.audit_log import AuditLog
    from app.models.electronic_invoice import (
        ElectronicInvoice,
        ElectronicInvoiceImportBatch,
        ElectronicInvoiceItem,
    )
    from app.models.transaction import Transaction

    seed_invoice_permissions()
    _, headers = register_user(invoice_api_client, "owner")
    family_id = create_family(invoice_api_client, headers)

    payload = {
        "source_filename": "2026-11 電子發票.csv",
        "invoices": [
            sample_invoice(),
            sample_invoice(
                number="CD12345678",
                merchant_name="家樂福",
                total_amount="50.00",
                items=[{"item_name": "白米", "amount": "45.00"}],
            ),
        ],
    }
    saved = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=headers,
        json=payload,
    )
    assert saved.status_code == 201, saved.text
    result = saved.json()
    assert result["received_count"] == 2
    assert result["saved_count"] == 2
    assert result["duplicate_count"] == 0
    assert result["detail_count"] == 3

    by_item = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&q=鮮乳",
        headers=headers,
    )
    assert by_item.status_code == 200, by_item.text
    assert by_item.json()["total"] == 1
    invoice_id = by_item.json()["invoices"][0]["id"]
    assert by_item.json()["invoices"][0]["validation_status"] == "matched"

    by_tax_id = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&q=12345678",
        headers=headers,
    )
    assert by_tax_id.status_code == 200
    assert by_tax_id.json()["total"] == 2

    by_amount = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&q=100.00",
        headers=headers,
    )
    assert by_amount.status_code == 200
    assert by_amount.json()["total"] == 1

    detail = invoice_api_client.get(
        f"/electronic-invoices/{invoice_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["items"]) == 2
    assert detail.json()["items"][1]["amount"] == "-20.00"
    assert detail.json()["difference_amount"] == "0.00"

    second_batch = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=headers,
        json={
            "source_filename": "2026-11 再次匯入.csv",
            "invoices": [
                sample_invoice(date="2026-11-28"),
                sample_invoice(
                    number="EF12345678",
                    merchant_name="便利商店",
                    total_amount="30.00",
                    items=[{"item_name": "礦泉水", "amount": "30.00"}],
                ),
            ],
        },
    )
    assert second_batch.status_code == 201, second_batch.text
    assert second_batch.json()["saved_count"] == 1
    assert second_batch.json()["duplicate_count"] == 1

    all_rows = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&limit=100",
        headers=headers,
    )
    assert all_rows.status_code == 200
    assert all_rows.json()["total"] == 3
    assert len({row["invoice_number"] for row in all_rows.json()["invoices"]}) == 3

    with Session(engine) as db:
        assert db.scalar(
            select(ElectronicInvoiceImportBatch.id).where(
                ElectronicInvoiceImportBatch.id == result["batch_id"],
                ElectronicInvoiceImportBatch.family_id == family_id,
            )
        ) is not None
        assert db.scalar(
            select(ElectronicInvoiceItem.id).where(
                ElectronicInvoiceItem.family_id == family_id,
                ElectronicInvoiceItem.invoice_id == invoice_id,
            )
        ) is not None
        assert db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity_type == "electronic_invoice_import_batch",
                AuditLog.entity_id == result["batch_id"],
                AuditLog.action == "import",
            )
        ) is not None
        assert db.scalar(
            select(Transaction.id).where(Transaction.family_id == family_id)
        ) is None


def test_invoice_own_scope_and_soft_void_are_enforced(invoice_api_client):
    seed_invoice_permissions()
    _, owner_headers = register_user(invoice_api_client, "scope-owner")
    member, member_headers = register_user(invoice_api_client, "scope-member")
    family_id = create_family(invoice_api_client, owner_headers)

    invited = invoice_api_client.post(
        f"/families/{family_id}/members",
        headers=owner_headers,
        json={"email": member["email"]},
    )
    assert invited.status_code == 201, invited.text

    owner_import = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=owner_headers,
        json={
            "source_filename": "owner.csv",
            "invoices": [sample_invoice()],
        },
    )
    assert owner_import.status_code == 201, owner_import.text

    member_before = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}",
        headers=member_headers,
    )
    assert member_before.status_code == 200
    assert member_before.json()["total"] == 0

    member_import = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=member_headers,
        json={
            "source_filename": "member.csv",
            "invoices": [
                sample_invoice(
                    number="GH12345678",
                    merchant_name="市場",
                    total_amount="25.00",
                    items=[{"item_name": "青菜", "amount": "25.00"}],
                )
            ],
        },
    )
    assert member_import.status_code == 201, member_import.text

    member_rows = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}",
        headers=member_headers,
    )
    assert member_rows.status_code == 200
    assert member_rows.json()["total"] == 1
    member_invoice_id = member_rows.json()["invoices"][0]["id"]

    owner_rows = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}",
        headers=owner_headers,
    )
    assert owner_rows.status_code == 200
    assert owner_rows.json()["total"] == 2

    voided = invoice_api_client.request(
        "DELETE",
        f"/electronic-invoices/{member_invoice_id}?family_id={family_id}",
        headers=member_headers,
        json={"reason": "測試作廢"},
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["is_voided"] is True

    active = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}",
        headers=member_headers,
    )
    assert active.status_code == 200
    assert active.json()["total"] == 0

    history = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&include_voided=true",
        headers=member_headers,
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["invoices"][0]["is_voided"] is True

    reimported = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=member_headers,
        json={
            "source_filename": "member-corrected.csv",
            "invoices": [
                sample_invoice(
                    number="GH12345678",
                    date="2026-11-28",
                    merchant_name="市場修正版",
                    total_amount="25.00",
                    items=[{"item_name": "青菜", "amount": "25.00"}],
                )
            ],
        },
    )
    assert reimported.status_code == 201, reimported.text
    assert reimported.json()["saved_count"] == 1
    assert reimported.json()["duplicate_count"] == 0

    active_after_reimport = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}",
        headers=member_headers,
    )
    assert active_after_reimport.status_code == 200
    assert active_after_reimport.json()["total"] == 1
    assert active_after_reimport.json()["invoices"][0]["merchant_name"] == "市場修正版"

    full_history = invoice_api_client.get(
        f"/electronic-invoices?family_id={family_id}&include_voided=true",
        headers=member_headers,
    )
    assert full_history.status_code == 200
    assert full_history.json()["total"] == 2
    assert sum(row["is_voided"] for row in full_history.json()["invoices"]) == 1


def test_invoice_family_isolation_and_invalid_payload_rejection(invoice_api_client):
    seed_invoice_permissions()
    _, headers = register_user(invoice_api_client, "isolated")
    family_id = create_family(invoice_api_client, headers)
    other_family_id = family_id + 999999

    outsider = invoice_api_client.get(
        f"/electronic-invoices?family_id={other_family_id}",
        headers=headers,
    )
    assert outsider.status_code == 403

    invalid = invoice_api_client.post(
        f"/electronic-invoices/imports?family_id={family_id}",
        headers=headers,
        json={
            "source_filename": "bad.csv",
            "invoices": [
                sample_invoice(number="BAD-INVOICE", merchant_tax_id="not-a-tax-id")
            ],
        },
    )
    assert invalid.status_code == 422
