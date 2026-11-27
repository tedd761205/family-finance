"""Persistent family e-invoice API integration tests."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine
from app import models  # noqa: F401
from main import app


@pytest.fixture(scope="session", autouse=True)
def ensure_persistent_einvoice_schema():
    if engine is None:
        pytest.skip("A disposable PostgreSQL DATABASE_URL is required for persistent invoice API tests")
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def family_context(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "persistent-einvoice-api-test-secret-at-least-32-bytes")
    suffix = uuid4().hex
    email = f"einvoice-{suffix}@example.com"
    password = "EInvoice-test-password-2026!"
    with TestClient(app) as client:
        registered = client.post("/auth/register", json={
            "email": email,
            "password": password,
            "display_name": "發票 API 測試",
        })
        assert registered.status_code == 201, registered.text
        login = client.post("/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = client.post("/families", headers=headers, json={
            "name": f"發票測試家庭 {suffix[:8]}",
            "currency": "TWD",
        })
        assert created.status_code == 201, created.text
        yield client, headers, created.json()["family_id"]


def invoice_payload(invoice_number="AB12345678"):
    return {
        "invoice_number": invoice_number,
        "date": "2026-11-25",
        "merchant_tax_id": "12345678",
        "merchant_name": "測試茶飲店",
        "total_amount": "120.50",
        "invoice_status": "已開立",
        "carrier_type": "手機條碼",
        # The server must ignore this secret field and never persist it.
        "carrier_number": "/SECRET-CARRIER-NUMBER",
        "items": [
            {"item_name": "珍珠奶茶", "amount": "150.00", "source_line": 2},
            {"item_name": "優惠折扣", "amount": "-29.50", "source_line": 3},
            {"item_name": "環保杯折抵", "amount": "0.00", "source_line": 4},
        ],
    }


def test_persist_einvoice_detail_search_deduplication_and_void(family_context):
    client, headers, family_id = family_context

    saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={
            "source_filename": "2026-11-invoices.csv",
            "source_sha256": "a" * 64,
            "invoices": [invoice_payload()],
        },
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["batch"]["saved_invoices"] == 1
    assert saved.json()["batch"]["duplicate_invoices"] == 0

    searched = client.get(
        f"/einvoices?family_id={family_id}&q=珍珠奶茶&month=2026-11&verification_status=matched",
        headers=headers,
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["total"] == 1
    invoice = searched.json()["invoices"][0]
    assert invoice["invoice_number"] == "AB12345678"
    assert invoice["total_amount"] == "120.50"
    assert invoice["detail_total"] == "120.50"
    assert invoice["difference_amount"] == "0.00"
    assert "carrier_number" not in invoice
    assert "SECRET-CARRIER" not in str(invoice)

    detail = client.get(f"/einvoices/{invoice['id']}?family_id={family_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert [row["item_name"] for row in detail.json()["invoice"]["items"]] == [
        "珍珠奶茶", "優惠折扣", "環保杯折抵"
    ]
    assert [row["amount"] for row in detail.json()["invoice"]["items"]] == [
        "150.00", "-29.50", "0.00"
    ]
    assert "carrier_number" not in detail.json()["invoice"]

    duplicate = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"source_filename": "repeat.csv", "invoices": [invoice_payload()]},
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["batch"]["saved_invoices"] == 0
    assert duplicate.json()["batch"]["duplicate_invoices"] == 1

    batches = client.get(f"/einvoices/batches?family_id={family_id}", headers=headers)
    assert batches.status_code == 200, batches.text
    assert batches.json()["total"] == 2

    # Electronic invoices are evidence records, not posted income/expense transactions.
    from app.models.transaction import Transaction
    with Session(engine) as db:
        assert db.query(Transaction).filter(Transaction.family_id == family_id).count() == 0

    voided = client.post(
        f"/einvoices/{invoice['id']}/void?family_id={family_id}&reason=測試作廢",
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["invoice"]["is_voided"] is True

    hidden = client.get(f"/einvoices?family_id={family_id}", headers=headers)
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    included = client.get(f"/einvoices?family_id={family_id}&include_voided=true", headers=headers)
    assert included.status_code == 200
    assert included.json()["total"] == 1


def test_invoice_numbers_are_unique_within_family_but_isolated_between_families(family_context):
    client, headers, family_id = family_context
    other_family = client.post("/families", headers=headers, json={
        "name": "另一個發票測試家庭",
        "currency": "TWD",
    })
    assert other_family.status_code == 201, other_family.text
    other_family_id = other_family.json()["family_id"]

    first = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [invoice_payload()]},
    )
    second = client.post(
        f"/einvoices/imports?family_id={other_family_id}",
        headers=headers,
        json={"invoices": [invoice_payload()]},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    first_list = client.get(f"/einvoices?family_id={family_id}", headers=headers)
    second_list = client.get(f"/einvoices?family_id={other_family_id}", headers=headers)
    assert first_list.json()["total"] == 1
    assert second_list.json()["total"] == 1


def test_invoice_import_rejects_invalid_header_total_and_malformed_tax_id(family_context):
    client, headers, family_id = family_context
    bad_total = invoice_payload()
    bad_total["total_amount"] = "-1.00"
    response = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [bad_total]},
    )
    assert response.status_code == 422

    bad_tax = invoice_payload("CD87654321")
    bad_tax["merchant_tax_id"] = "123"
    response = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [bad_tax]},
    )
    assert response.status_code == 422


def test_persistent_invoice_routes_require_authentication():
    schema = app.openapi()
    for path, method in (
        ("/einvoices/imports", "post"),
        ("/einvoices", "get"),
        ("/einvoices/batches", "get"),
        ("/einvoices/{invoice_id}", "get"),
        ("/einvoices/{invoice_id}/void", "post"),
    ):
        operation = schema["paths"][path][method]
        assert "HTTPBearer" in str(operation.get("security", []))
