"""Persistent family e-invoice API integration tests."""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models import (
    Account,
    AuditLog,
    Category,
    EInvoice,
    EInvoiceCategoryRule,
    EInvoiceImportBatch,
    EInvoiceItem,
    EInvoicePayment,
    EInvoicePosting,
    Transaction,
    Family,
    FamilyMember,
    MemberRole,
    Permission,
    RevokedToken,
    Role,
    RoleDataScope,
    RolePermission,
    User,
)
from app.permission_catalog import PERMISSION_CATALOG
from main import app


PERSISTENT_INVOICE_TEST_ROOTS = [
    User.__table__,
    Family.__table__,
    Category.__table__,
    Permission.__table__,
    FamilyMember.__table__,
    Role.__table__,
    RolePermission.__table__,
    RoleDataScope.__table__,
    MemberRole.__table__,
    RevokedToken.__table__,
    AuditLog.__table__,
    Account.__table__,
    Transaction.__table__,
    EInvoiceImportBatch.__table__,
    EInvoice.__table__,
    EInvoiceItem.__table__,
    EInvoiceCategoryRule.__table__,
    EInvoicePosting.__table__,
    EInvoicePayment.__table__,
]


def _invoice_test_schema_tables():
    # Include the transitive FK parents needed by account transactions without
    # creating unrelated application tables.
    required = set()
    pending = list(PERSISTENT_INVOICE_TEST_ROOTS)
    while pending:
        table = pending.pop()
        if table in required:
            continue
        required.add(table)
        for foreign_key in table.foreign_keys:
            parent_table = foreign_key.column.table
            if parent_table not in required:
                pending.append(parent_table)
    return [table for table in Base.metadata.sorted_tables if table in required]


PERSISTENT_INVOICE_TEST_TABLES = _invoice_test_schema_tables()


@pytest.fixture(autouse=True)
def ensure_persistent_einvoice_schema():
    if engine is None:
        pytest.skip("A disposable PostgreSQL DATABASE_URL is required for persistent invoice API tests")
    # Create only the tables this feature needs. Some existing integration
    # tests deliberately create/drop a smaller subset of the schema.
    Base.metadata.create_all(bind=engine, tables=PERSISTENT_INVOICE_TEST_TABLES)
    with Session(engine) as db:
        existing = {permission.code for permission in db.query(Permission).all()}
        for permission in PERMISSION_CATALOG:
            if permission["code"] not in existing:
                db.add(Permission(**permission))
        db.commit()
    yield
    Base.metadata.drop_all(bind=engine, tables=PERSISTENT_INVOICE_TEST_TABLES)


@pytest.fixture
def family_context(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "persistent-einvoice-api-test-secret-at-least-32-bytes")
    monkeypatch.setenv("EINVOICE_PERSISTENCE_ENABLED", "true")
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
    from sqlalchemy import text
    with Session(engine) as db:
        transaction_table_exists = db.execute(
            text("SELECT to_regclass('public.transactions') IS NOT NULL")
        ).scalar_one()
        if transaction_table_exists:
            transaction_count = db.execute(
                text("SELECT count(*) FROM transactions WHERE family_id = :family_id"),
                {"family_id": family_id},
            ).scalar_one()
            assert transaction_count == 0

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
        ("/einvoices/availability", "get"),
        ("/einvoices/imports", "post"),
        ("/einvoices", "get"),
        ("/einvoices/batches", "get"),
        ("/einvoices/categories", "get"),
        ("/einvoices/{invoice_id}", "get"),
        ("/einvoices/{invoice_id}/items/{item_id}/category", "put"),
        ("/einvoices/{invoice_id}/posting", "get"),
        ("/einvoices/{invoice_id}/posting", "post"),
        ("/einvoices/{invoice_id}/posting/payments", "post"),
        ("/einvoices/{invoice_id}/posting/void", "post"),
        ("/einvoices/{invoice_id}/void", "post"),
    ):
        operation = schema["paths"][path][method]
        assert "HTTPBearer" in str(operation.get("security", []))



def test_invoice_persistence_feature_flag_blocks_history_until_enabled(family_context, monkeypatch):
    client, headers, family_id = family_context
    monkeypatch.setenv("EINVOICE_PERSISTENCE_ENABLED", "false")

    availability = client.get("/einvoices/availability", headers=headers)
    assert availability.status_code == 200
    assert availability.json()["enabled"] is False

    response = client.get(f"/einvoices?family_id={family_id}", headers=headers)
    assert response.status_code == 503
    assert "資料庫尚未啟用" in response.json()["detail"]

    monkeypatch.setenv("EINVOICE_PERSISTENCE_ENABLED", "true")
    availability = client.get("/einvoices/availability", headers=headers)
    assert availability.json()["enabled"] is True


def test_invoice_item_category_rule_suggests_same_merchant_and_product(family_context):
    client, headers, family_id = family_context

    category_response = client.post(
        f"/categories?family_id={family_id}",
        headers=headers,
        json={"category_type": "expense", "name": "飲料"},
    )
    assert category_response.status_code == 201, category_response.text
    category_id = category_response.json()["id"]

    first_payload = invoice_payload("EF12345678")
    first_payload["items"] = [
        {"item_name": "珍珠奶茶", "amount": "120.50", "source_line": 2},
    ]
    first_saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [first_payload]},
    )
    assert first_saved.status_code == 201, first_saved.text

    first_list = client.get(f"/einvoices?family_id={family_id}", headers=headers)
    first_invoice = first_list.json()["invoices"][0]
    first_detail = client.get(
        f"/einvoices/{first_invoice['id']}?family_id={family_id}",
        headers=headers,
    )
    assert first_detail.status_code == 200, first_detail.text
    first_item = first_detail.json()["invoice"]["items"][0]

    saved_category = client.put(
        f"/einvoices/{first_invoice['id']}/items/{first_item['id']}/category?family_id={family_id}",
        headers=headers,
        json={"category_id": category_id, "remember_rule": True},
    )
    assert saved_category.status_code == 200, saved_category.text
    assert saved_category.json()["item"]["category_id"] == category_id
    assert saved_category.json()["item"]["category_source"] == "manual"

    second_payload = invoice_payload("GH12345678")
    second_payload["items"] = [
        {"item_name": "珍珠奶茶", "amount": "95.00", "source_line": 2},
        {"item_name": "折價優惠", "amount": "-10.00", "source_line": 3},
        {"item_name": "贈品", "amount": "0.00", "source_line": 4},
    ]
    second_payload["total_amount"] = "85.00"
    second_saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [second_payload]},
    )
    assert second_saved.status_code == 201, second_saved.text

    second_list = client.get(f"/einvoices?family_id={family_id}", headers=headers)
    second_invoice = next(
        invoice for invoice in second_list.json()["invoices"]
        if invoice["invoice_number"] == "GH12345678"
    )
    second_detail = client.get(
        f"/einvoices/{second_invoice['id']}?family_id={family_id}",
        headers=headers,
    )
    assert second_detail.status_code == 200, second_detail.text
    items = second_detail.json()["invoice"]["items"]
    assert items[0]["category_id"] is None
    assert items[0]["suggested_category_id"] == category_id
    assert items[0]["suggested_category_name"] == "飲料"
    assert items[0]["suggestion_reason"] == "同店家曾經確認過相同商品的分類"

    # Discounts and zero-value items do not inherit an expense category rule.
    assert items[1]["suggested_category_id"] is None
    assert items[2]["suggested_category_id"] is None

    rejected_discount = client.put(
        f"/einvoices/{second_invoice['id']}/items/{items[1]['id']}/category?family_id={family_id}",
        headers=headers,
        json={"category_id": category_id, "remember_rule": True},
    )
    assert rejected_discount.status_code == 422


def test_invoice_category_suggestions_are_isolated_by_family(family_context):
    client, headers, family_id = family_context

    category_response = client.post(
        f"/categories?family_id={family_id}",
        headers=headers,
        json={"category_type": "expense", "name": "交通"},
    )
    assert category_response.status_code == 201, category_response.text
    category_id = category_response.json()["id"]

    payload = invoice_payload("JK12345678")
    payload["items"] = [{"item_name": "捷運票", "amount": "50.00", "source_line": 2}]
    saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [payload]},
    )
    assert saved.status_code == 201, saved.text
    invoice = client.get(f"/einvoices?family_id={family_id}", headers=headers).json()["invoices"][0]
    item = client.get(
        f"/einvoices/{invoice['id']}?family_id={family_id}",
        headers=headers,
    ).json()["invoice"]["items"][0]

    other_family = client.post(
        "/families",
        headers=headers,
        json={"name": "分類隔離測試家庭", "currency": "TWD"},
    )
    assert other_family.status_code == 201, other_family.text
    other_family_id = other_family.json()["family_id"]
    foreign_category_response = client.post(
        f"/categories?family_id={other_family_id}",
        headers=headers,
        json={"category_type": "expense", "name": "另一家庭交通"},
    )
    assert foreign_category_response.status_code == 201, foreign_category_response.text
    foreign_category_id = foreign_category_response.json()["id"]

    other_payload = invoice_payload("LM12345678")
    other_payload["items"] = [{"item_name": "捷運票", "amount": "50.00", "source_line": 2}]
    other_saved = client.post(
        f"/einvoices/imports?family_id={other_family_id}",
        headers=headers,
        json={"invoices": [other_payload]},
    )
    assert other_saved.status_code == 201, other_saved.text
    other_invoice = client.get(
        f"/einvoices?family_id={other_family_id}", headers=headers
    ).json()["invoices"][0]
    other_detail = client.get(
        f"/einvoices/{other_invoice['id']}?family_id={other_family_id}",
        headers=headers,
    )
    assert other_detail.status_code == 200, other_detail.text
    other_item = other_detail.json()["invoice"]["items"][0]
    assert other_item["suggested_category_id"] is None

    rejected = client.put(
        f"/einvoices/{invoice['id']}/items/{item['id']}/category?family_id={family_id}",
        headers=headers,
        json={"category_id": foreign_category_id, "remember_rule": True},
    )
    assert rejected.status_code == 404




def test_invoice_posting_supports_deferred_split_payments_and_controlled_void(family_context):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models import Transaction as TransactionModel, EInvoicePayment as PaymentModel

    client, headers, family_id = family_context
    category = client.post(
        f"/categories?family_id={family_id}",
        headers=headers,
        json={"category_type": "expense", "name": "飲料"},
    )
    assert category.status_code == 201, category.text
    category_id = category.json()["id"]

    cash = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={"name": "發票測試現金", "account_type": "cash", "currency_code": "TWD"},
    )
    assert cash.status_code == 201, cash.text
    usd = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={"name": "發票測試美元帳戶", "account_type": "bank", "currency_code": "USD"},
    )
    assert usd.status_code == 201, usd.text
    cash_id = cash.json()["id"]
    usd_id = usd.json()["id"]

    payload = invoice_payload("NP12345678")
    saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [payload]},
    )
    assert saved.status_code == 201, saved.text
    invoice = client.get(f"/einvoices?family_id={family_id}&q=NP12345678", headers=headers)
    assert invoice.status_code == 200, invoice.text
    invoice_id = invoice.json()["invoices"][0]["id"]
    detail = client.get(f"/einvoices/{invoice_id}?family_id={family_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    item = next(row for row in detail.json()["invoice"]["items"] if row["amount"] == "150.00")
    classified = client.put(
        f"/einvoices/{invoice_id}/items/{item['id']}/category?family_id={family_id}",
        headers=headers,
        json={"category_id": category_id, "remember_rule": False},
    )
    assert classified.status_code == 200, classified.text

    # Confirm the invoice now, but do not create any payment or account transaction yet.
    opened = client.post(
        f"/einvoices/{invoice_id}/posting?family_id={family_id}",
        headers=headers,
        json={"payments": []},
    )
    assert opened.status_code == 201, opened.text
    posting = opened.json()["posting"]
    assert posting["status"] == "unpaid"
    assert posting["paid_amount"] == "0.00"
    assert posting["remaining_amount"] == "120.50"
    assert posting["payments"] == []

    with Session(engine) as db:
        assert db.scalar(
            select(func.count(TransactionModel.id)).where(
                TransactionModel.family_id == family_id,
                TransactionModel.transaction_type == "expense",
            )
        ) == 0

    # The first payment is partial and paid from a TWD cash account.
    first = client.post(
        f"/einvoices/{invoice_id}/posting/payments?family_id={family_id}",
        headers=headers,
        json={"payments": [{
            "account_id": cash_id,
            "amount": "50.00",
            "payment_date": "2026-11-27T12:00:00+08:00",
        }]},
    )
    assert first.status_code == 201, first.text
    posting = first.json()["posting"]
    assert posting["status"] == "partially_paid"
    assert posting["paid_amount"] == "50.00"
    assert posting["remaining_amount"] == "70.50"
    assert posting["payments"][0]["account_currency_code"] == "TWD"
    first_transaction_id = posting["payments"][0]["transaction_id"]

    # Complete the invoice from a USD account using account-currency units per TWD.
    second = client.post(
        f"/einvoices/{invoice_id}/posting/payments?family_id={family_id}",
        headers=headers,
        json={"payments": [{
            "account_id": usd_id,
            "amount": "70.50",
            "payment_date": "2026-11-27T13:00:00+08:00",
            "exchange_rate": "0.032",
        }]},
    )
    assert second.status_code == 201, second.text
    posting = second.json()["posting"]
    assert posting["status"] == "paid"
    assert posting["paid_amount"] == "120.50"
    assert posting["remaining_amount"] == "0.00"
    assert len(posting["payments"]) == 2

    with Session(engine) as db:
        payments = db.scalars(
            select(PaymentModel).where(
                PaymentModel.family_id == family_id,
                PaymentModel.posting_id == posting["id"],
            ).order_by(PaymentModel.id)
        ).all()
        transactions = db.scalars(
            select(TransactionModel).where(
                TransactionModel.family_id == family_id,
                TransactionModel.id.in_([payment.transaction_id for payment in payments]),
            ).order_by(TransactionModel.id)
        ).all()
        assert len(payments) == 2
        assert len(transactions) == 2
        assert all(row.transaction_type == "expense" for row in transactions)
        assert transactions[0].category_id == category_id
        usd_payment = next(payment for payment in payments if payment.account_id == usd_id)
        assert usd_payment.account_currency_code == "USD"
        assert usd_payment.exchange_rate == Decimal("0.032")
        assert usd_payment.account_amount == Decimal("2.2560")

    # Duplicate posting is blocked and a direct generic transaction edit/void is blocked.
    duplicate = client.post(
        f"/einvoices/{invoice_id}/posting?family_id={family_id}",
        headers=headers,
        json={"payments": []},
    )
    assert duplicate.status_code == 409

    direct_update = client.patch(
        f"/transactions/{first_transaction_id}?family_id={family_id}",
        headers=headers,
        json={"amount": "1.0000"},
    )
    assert direct_update.status_code == 400
    assert "電子發票付款" in direct_update.json()["detail"]
    direct_void = client.delete(
        f"/transactions/{first_transaction_id}?family_id={family_id}",
        headers=headers,
    )
    assert direct_void.status_code == 400
    assert "電子發票付款" in direct_void.json()["detail"]

    # The invoice cannot be voided while its posting is active.
    invoice_void_before_posting_void = client.post(
        f"/einvoices/{invoice_id}/void?family_id={family_id}&reason=測試作廢",
        headers=headers,
    )
    assert invoice_void_before_posting_void.status_code == 409

    posting_void = client.post(
        f"/einvoices/{invoice_id}/posting/void?family_id={family_id}&reason=付款資料測試沖銷",
        headers=headers,
    )
    assert posting_void.status_code == 200, posting_void.text
    assert posting_void.json()["posting"]["status"] == "voided"
    with Session(engine) as db:
        active_count = db.scalar(
            select(func.count(TransactionModel.id)).where(
                TransactionModel.family_id == family_id,
                TransactionModel.id.in_([first_transaction_id] + [
                    item["transaction_id"] for item in posting["payments"][1:]
                ]),
                TransactionModel.is_voided.is_(False),
            )
        )
        assert active_count == 0

    invoice_void_after_posting_void = client.post(
        f"/einvoices/{invoice_id}/void?family_id={family_id}&reason=入帳已先沖銷",
        headers=headers,
    )
    assert invoice_void_after_posting_void.status_code == 200, invoice_void_after_posting_void.text


def test_invoice_posting_rejects_overpayment_and_missing_foreign_exchange_rate(family_context):
    client, headers, family_id = family_context
    cash = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={"name": "付款測試現金", "account_type": "cash", "currency_code": "TWD"},
    )
    foreign = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={"name": "付款測試日圓", "account_type": "bank", "currency_code": "JPY"},
    )
    assert cash.status_code == 201, cash.text
    assert foreign.status_code == 201, foreign.text
    saved = client.post(
        f"/einvoices/imports?family_id={family_id}",
        headers=headers,
        json={"invoices": [invoice_payload("QR12345678")]},
    )
    assert saved.status_code == 201, saved.text
    invoice = client.get(
        f"/einvoices?family_id={family_id}&q=QR12345678",
        headers=headers,
    ).json()["invoices"][0]
    invoice_id = invoice["id"]

    opened = client.post(
        f"/einvoices/{invoice_id}/posting?family_id={family_id}",
        headers=headers,
        json={"payments": [{"account_id": cash.json()["id"], "amount": "100.00",
                            "payment_date": "2026-11-27T10:00:00+08:00"}]},
    )
    assert opened.status_code == 201, opened.text

    overpaid = client.post(
        f"/einvoices/{invoice_id}/posting/payments?family_id={family_id}",
        headers=headers,
        json={"payments": [{"account_id": cash.json()["id"], "amount": "21.00",
                            "payment_date": "2026-11-27T11:00:00+08:00"}]},
    )
    assert overpaid.status_code == 409

    missing_rate = client.post(
        f"/einvoices/{invoice_id}/posting/payments?family_id={family_id}",
        headers=headers,
        json={"payments": [{"account_id": foreign.json()["id"], "amount": "20.50",
                            "payment_date": "2026-11-27T11:00:00+08:00"}]},
    )
    assert missing_rate.status_code == 422


