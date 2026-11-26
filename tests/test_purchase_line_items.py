from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.fixture
def purchase_api_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from main import app
    from app.database import engine, get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "purchase-line-item-test-secret-key-at-least-32-bytes",
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
def ensure_purchase_line_item_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def seed_purchase_permissions():
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


def setup_purchase_family(client, suffix, label="owner"):
    seed_purchase_permissions()
    email = f"purchase-{label}-{suffix}@example.com"
    password = "Purchase-line-item-test-password-123!"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": f"採買明細測試 {label}",
        },
    )
    assert registered.status_code == 201, registered.text
    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    family = client.post(
        "/families",
        headers=headers,
        json={"name": f"採買明細測試家庭 {suffix}", "currency": "TWD"},
    )
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    account = client.post(
        f"/accounts?family_id={family_id}",
        headers=headers,
        json={
            "name": "測試現金",
            "account_type": "cash",
            "currency_code": "TWD",
        },
    )
    assert account.status_code == 201, account.text
    return registered.json(), headers, family_id, account.json()["id"]


def purchase_payload(account_id, *, transaction_type="expense", items=None):
    return {
        "account_id": account_id,
        "transaction_type": transaction_type,
        "amount": "150.0000",
        "currency_code": "TWD",
        "transaction_date": "2026-11-26T12:00:00+08:00",
        "description": "市場採買",
        "purchase_items": items or [],
    }


def test_purchase_items_are_saved_under_one_transaction_and_audited(purchase_api_client):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.audit_log import AuditLog
    from app.models.purchase_line_item import PurchaseLineItem
    from app.models.transaction import Transaction

    suffix = uuid4().hex
    _, headers, family_id, account_id = setup_purchase_family(
        purchase_api_client, suffix,
    )

    created = purchase_api_client.post(
        f"/transactions?family_id={family_id}",
        headers=headers,
        json=purchase_payload(
            account_id,
            items=[
                {
                    "item_name": "高麗菜",
                    "quantity": "1",
                    "unit": "顆",
                    "unit_price": "45",
                },
                {
                    "item_name": "雞蛋",
                    "quantity": "2",
                    "unit": "盒",
                    "unit_price": "52.5",
                },
            ],
        ),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    transaction_id = body["id"]

    assert body["transaction_type"] == "expense"
    assert len(body["purchase_items"]) == 2
    assert body["purchase_items"][0]["item_name"] == "高麗菜"
    assert body["purchase_items"][0]["line_total"] == "45.0000"
    assert body["purchase_items"][1]["line_total"] == "105.0000"

    with Session(engine) as db:
        transaction_count = db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.family_id == family_id,
                Transaction.id == transaction_id,
            )
        )
        lines = db.scalars(
            select(PurchaseLineItem)
            .where(
                PurchaseLineItem.family_id == family_id,
                PurchaseLineItem.transaction_id == transaction_id,
            )
            .order_by(PurchaseLineItem.sort_order)
        ).all()
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.family_id == family_id,
                AuditLog.entity_type == "transaction",
                AuditLog.entity_id == transaction_id,
                AuditLog.action == "create",
            )
        )

        assert transaction_count == 1
        assert len(lines) == 2
        assert lines[0].created_by is not None
        assert audit is not None
        assert len(audit.new_values["purchase_items"]) == 2

    listed = purchase_api_client.get(
        f"/transactions?family_id={family_id}",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    matching = next(
        row for row in listed.json()["transactions"]
        if row["id"] == transaction_id
    )
    assert len(matching["purchase_items"]) == 2

    detail = purchase_api_client.get(
        f"/transactions/{transaction_id}?family_id={family_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert [row["item_name"] for row in detail.json()["purchase_items"]] == [
        "高麗菜",
        "雞蛋",
    ]


def test_purchase_items_can_be_replaced_atomically_on_transaction_update(purchase_api_client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.audit_log import AuditLog
    from app.models.purchase_line_item import PurchaseLineItem

    suffix = uuid4().hex
    _, headers, family_id, account_id = setup_purchase_family(
        purchase_api_client, suffix,
    )
    created = purchase_api_client.post(
        f"/transactions?family_id={family_id}",
        headers=headers,
        json=purchase_payload(
            account_id,
            items=[
                {"item_name": "牛奶", "quantity": "1", "unit": "瓶", "unit_price": "90"},
                {"item_name": "吐司", "quantity": "1", "unit": "條", "unit_price": "60"},
            ],
        ),
    )
    assert created.status_code == 201, created.text
    transaction_id = created.json()["id"]

    updated = purchase_api_client.patch(
        f"/transactions/{transaction_id}?family_id={family_id}",
        headers=headers,
        json={
            "amount": "120.0000",
            "purchase_items": [
                {
                    "item_name": "無糖豆漿",
                    "quantity": "2",
                    "unit": "瓶",
                    "unit_price": "60",
                },
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["amount"] == "120.0000"
    assert len(updated.json()["purchase_items"]) == 1
    assert updated.json()["purchase_items"][0]["item_name"] == "無糖豆漿"
    assert updated.json()["purchase_items"][0]["line_total"] == "120.0000"

    with Session(engine) as db:
        lines = db.scalars(
            select(PurchaseLineItem).where(
                PurchaseLineItem.family_id == family_id,
                PurchaseLineItem.transaction_id == transaction_id,
            )
        ).all()
        audits = db.scalars(
            select(AuditLog).where(
                AuditLog.family_id == family_id,
                AuditLog.entity_type == "transaction",
                AuditLog.entity_id == transaction_id,
                AuditLog.action == "update",
            )
        ).all()
        assert len(lines) == 1
        assert lines[0].item_name == "無糖豆漿"
        assert len(audits) == 1
        assert len(audits[0].old_values["purchase_items"]) == 2
        assert len(audits[0].new_values["purchase_items"]) == 1


def test_purchase_items_are_expense_only_and_cannot_inject_foreign_family_id(purchase_api_client):
    suffix = uuid4().hex
    _, headers, family_id, account_id = setup_purchase_family(
        purchase_api_client, suffix,
    )

    non_expense = purchase_api_client.post(
        f"/transactions?family_id={family_id}",
        headers=headers,
        json=purchase_payload(
            account_id,
            transaction_type="income",
            items=[
                {
                    "item_name": "不可附加",
                    "quantity": "1",
                    "unit_price": "1",
                },
            ],
        ),
    )
    assert non_expense.status_code == 400
    assert "只能附加在支出" in non_expense.json()["detail"]

    injected_scope = purchase_api_client.post(
        f"/transactions?family_id={family_id}",
        headers=headers,
        json=purchase_payload(
            account_id,
            items=[
                {
                    "family_id": family_id + 1,
                    "item_name": "跨家庭注入",
                    "quantity": "1",
                    "unit_price": "10",
                },
            ],
        ),
    )
    assert injected_scope.status_code == 422


def test_purchase_item_visibility_follows_parent_transaction_own_scope(purchase_api_client):
    suffix = uuid4().hex
    _, owner_headers, family_id, account_id = setup_purchase_family(
        purchase_api_client, suffix, "owner",
    )
    # Register a second user, then join the owner's family.
    email = f"purchase-member-{suffix}@example.com"
    password = "Purchase-line-item-test-password-123!"
    member = purchase_api_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": "採買明細家庭成員",
        },
    )
    assert member.status_code == 201, member.text
    login = purchase_api_client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    joined = purchase_api_client.post(
        f"/families/{family_id}/members",
        headers=owner_headers,
        json={"email": email},
    )
    assert joined.status_code == 201, joined.text

    created = purchase_api_client.post(
        f"/transactions?family_id={family_id}",
        headers=owner_headers,
        json=purchase_payload(
            account_id,
            items=[
                {"item_name": "蘋果", "quantity": "3", "unit": "顆", "unit_price": "20"},
            ],
        ),
    )
    assert created.status_code == 201, created.text
    transaction_id = created.json()["id"]

    hidden_detail = purchase_api_client.get(
        f"/transactions/{transaction_id}?family_id={family_id}",
        headers=member_headers,
    )
    assert hidden_detail.status_code == 403

    hidden_list = purchase_api_client.get(
        f"/transactions?family_id={family_id}",
        headers=member_headers,
    )
    assert hidden_list.status_code == 200
    assert all(
        row["id"] != transaction_id
        for row in hidden_list.json()["transactions"]
    )


def test_purchase_item_editor_and_invoice_bridge_are_wired_for_mobile_transactions(purchase_api_client):
    with purchase_api_client as client:
        page = client.get("/")
        javascript = client.get("/static/app.js").text
        receipt_script = client.get("/static/local-receipt-ocr.js").text
        css = client.get("/static/styles.css").text

    assert page.status_code == 200
    assert 'id="purchase-items-panel"' in page.text
    assert 'id="purchase-item-add"' in page.text
    assert 'id="purchase-items-total"' in page.text
    assert 'id="purchase-items-apply-total"' in page.text
    assert "purchase_items:type===\"expense\"?readPurchaseItems():[]" in javascript
    assert "window.setTransactionPurchaseItems" in receipt_script
    assert "structuredItems.map((item)" in receipt_script
    assert ".purchase-item-row" in css
    assert "@media(max-width:760px)" in css
