from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine
from app import models as all_models
from app.models.bank_import import BankImportBatch, BankImportRow
from app.models.einvoice import EInvoice, EInvoiceImportBatch
from app.models.einvoice_posting import EInvoicePayment, EInvoicePosting
from app.models.permission import Permission
from app.models.transaction import Transaction
from app.models.user import User
from app.permission_catalog import PERMISSION_CATALOG
from main import app


EINVOICE_RECONCILIATION_TEST_ROOTS = [
    "User", "Family", "FamilyMember", "Role", "Permission", "RolePermission",
    "MemberRole", "RoleDataScope", "RevokedToken", "AuditLog", "Account",
    "Transaction", "PurchaseLineItem", "BankImportBatch", "BankImportRow",
    "EInvoiceImportBatch", "EInvoice", "EInvoiceItem", "EInvoiceCategoryRule",
    "EInvoicePosting", "EInvoicePayment", "ReconciliationSession",
    "ReconciliationMatch", "ReconciliationExclusion",
]


def _einvoice_reconciliation_schema_tables():
    required = set()
    pending = [getattr(all_models, name).__table__ for name in EINVOICE_RECONCILIATION_TEST_ROOTS]
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


@pytest.fixture(scope="module", autouse=True)
def ensure_einvoice_reconciliation_schema():
    tables = _einvoice_reconciliation_schema_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    Base.metadata.drop_all(bind=engine, tables=tables)


@pytest.fixture
def einvoice_reconciliation_client(monkeypatch):
    from app.database import get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "einvoice-reconciliation-test-secret-key-at-least-32-bytes",
    )
    monkeypatch.setenv("EINVOICE_PERSISTENCE_ENABLED", "true")

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


def _create_family_and_account(client):
    suffix = uuid4().hex
    email = f"einvoice-reconciliation-{suffix}@example.com"
    password = "Einvoice-Reconciliation-Test-123!"
    _seed_permissions()

    registered = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "發票對帳測試"},
    )
    assert registered.status_code == 201, registered.text

    logged_in = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200, logged_in.text
    headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

    family = client.post(
        "/families",
        headers=headers,
        json={"name": f"發票對帳測試家庭 {suffix}", "currency": "TWD"},
    )
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    account = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={
            "name": "電子發票對帳銀行帳戶",
            "account_type": "bank",
            "currency_code": "TWD",
        },
    )
    assert account.status_code == 201, account.text

    with Session(engine) as db:
        user = db.query(User).filter(User.email == email).one()

    return headers, family_id, account.json()["id"], user.id


def _seed_invoice_payment_and_statement(family_id, account_id, user_id):
    """建立一張已付款發票、一筆正式支出，以及一列未產生帳務的銀行明細。"""
    with Session(engine) as db:
        statement = BankImportBatch(
            family_id=family_id,
            account_id=account_id,
            source_filename="invoice-payment-statement.csv",
            status="confirmed",
            column_mapping={"date": "日期", "amount": "金額", "description": "摘要"},
            total_rows=1,
            ready_rows=0,
            duplicate_rows=0,
            invalid_rows=0,
            imported_rows=1,
            created_by=user_id,
            confirmed_by=user_id,
            confirmed_at=datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc),
        )
        invoice_batch = EInvoiceImportBatch(
            family_id=family_id,
            source_filename="invoice-payment.csv",
            status="completed",
            total_invoices=1,
            saved_invoices=1,
            duplicate_invoices=0,
            issue_invoices=0,
            created_by=user_id,
        )
        db.add_all([statement, invoice_batch])
        db.flush()

        bank_row = BankImportRow(
            family_id=family_id,
            batch_id=statement.id,
            row_number=2,
            fingerprint="e" * 64,
            transaction_date=datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc),
            transaction_type="expense",
            amount=Decimal("3000.0000"),
            currency_code="TWD",
            description="測試超商刷卡消費",
            external_reference="BANK-INV-3000",
            raw_data={"日期": "2026-11-05", "金額": "-3000", "摘要": "測試超商刷卡消費"},
            status="imported",
        )
        invoice = EInvoice(
            family_id=family_id,
            import_batch_id=invoice_batch.id,
            invoice_number="AB12345678",
            invoice_date=date(2026, 11, 5),
            merchant_tax_id="12345678",
            merchant_name="測試超商",
            total_amount=Decimal("3000.00"),
            invoice_status="已開立",
            detail_total=Decimal("3000.00"),
            difference_amount=Decimal("0.00"),
            verification_status="matched",
            is_duplicate=False,
            created_by=user_id,
        )
        db.add_all([bank_row, invoice])
        db.flush()

        transaction = Transaction(
            family_id=family_id,
            account_id=account_id,
            transaction_type="expense",
            amount=Decimal("3000.0000"),
            currency_code="TWD",
            transaction_date=datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc),
            description="電子發票付款 測試超商 AB12345678",
            external_reference="AB12345678",
            created_by=user_id,
        )
        db.add(transaction)
        db.flush()

        posting = EInvoicePosting(
            family_id=family_id,
            invoice_id=invoice.id,
            invoice_amount=Decimal("3000.00"),
            invoice_currency_code="TWD",
            status="paid",
            created_by=user_id,
        )
        db.add(posting)
        db.flush()

        payment = EInvoicePayment(
            family_id=family_id,
            posting_id=posting.id,
            account_id=account_id,
            amount=Decimal("3000.00"),
            currency_code="TWD",
            account_amount=Decimal("3000.0000"),
            account_currency_code="TWD",
            exchange_rate=Decimal("1"),
            payment_date=datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc),
            transaction_id=transaction.id,
            description="電子發票付款",
            created_by=user_id,
        )
        db.add(payment)
        db.commit()

        return {
            "batch_id": statement.id,
            "bank_row_id": bank_row.id,
            "invoice_id": invoice.id,
            "posting_id": posting.id,
            "payment_id": payment.id,
            "transaction_id": transaction.id,
        }


def test_einvoice_payment_is_suggested_and_manually_reconciled_without_duplicate_transaction(
    einvoice_reconciliation_client,
):
    client = einvoice_reconciliation_client
    headers, family_id, account_id, user_id = _create_family_and_account(client)
    seeded = _seed_invoice_payment_and_statement(family_id, account_id, user_id)

    session_response = client.post(
        f"/reconciliations/sessions?family_id={family_id}",
        headers=headers,
        json={
            "account_id": account_id,
            "source_batch_id": seeded["batch_id"],
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
        },
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["session"]["id"]

    with Session(engine) as db:
        transaction_count_before = db.scalar(
            select(func.count(Transaction.id)).where(Transaction.family_id == family_id)
        )
        original_transaction = db.get(Transaction, seeded["transaction_id"])
        original_amount = original_transaction.amount

    suggestion_response = client.post(
        f"/reconciliations/sessions/{session_id}/suggestions?family_id={family_id}",
        headers=headers,
    )
    assert suggestion_response.status_code == 200, suggestion_response.text
    suggestions = suggestion_response.json()["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["bank_import_row"]["id"] == seeded["bank_row_id"]
    assert suggestions[0]["candidates"]
    candidate = next(
        item for item in suggestions[0]["candidates"]
        if item["transaction_id"] == seeded["transaction_id"]
    )
    assert candidate["source_type"] == "einvoice_payment"
    assert candidate["source_label"] == "電子發票付款"
    assert candidate["payment_id"] == seeded["payment_id"]
    assert candidate["posting_id"] == seeded["posting_id"]
    assert candidate["invoice_number"] == "AB12345678"
    assert candidate["merchant_name"] == "測試超商"
    assert candidate["invoice_payment_amount"] == "3000.00"
    assert candidate["invoice_total_amount"] == "3000.00"
    assert suggestion_response.json()["automatic_matches_created"] == 0

    match_response = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": seeded["bank_row_id"],
            "transaction_id": seeded["transaction_id"],
            "allocated_amount": "3000.0000",
        },
    )
    assert match_response.status_code == 201, match_response.text
    assert match_response.json()["match"]["transaction_id"] == seeded["transaction_id"]
    assert match_response.json()["bank_row"]["reconciliation_status"] == "matched"

    # A second active match for the same payment transaction is rejected.
    duplicate_match = client.post(
        f"/reconciliations/sessions/{session_id}/matches?family_id={family_id}",
        headers=headers,
        json={
            "bank_import_row_id": seeded["bank_row_id"],
            "transaction_id": seeded["transaction_id"],
            "allocated_amount": "3000.0000",
        },
    )
    assert duplicate_match.status_code == 409

    ledger_only = client.get(
        f"/reconciliations/sessions/{session_id}/ledger-only?family_id={family_id}",
        headers=headers,
    )
    assert ledger_only.status_code == 200, ledger_only.text
    assert ledger_only.json()["total"] == 0

    with Session(engine) as db:
        transaction_count_after = db.scalar(
            select(func.count(Transaction.id)).where(Transaction.family_id == family_id)
        )
        payment = db.get(EInvoicePayment, seeded["payment_id"])
        transaction = db.get(Transaction, seeded["transaction_id"])
        assert transaction_count_after == transaction_count_before
        assert transaction.amount == original_amount
        assert transaction.is_voided is False
        assert payment.is_voided is False
