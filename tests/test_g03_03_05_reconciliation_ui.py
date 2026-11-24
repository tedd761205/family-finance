from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import pytest

from app.database import Base, engine


@pytest.fixture(scope="session", autouse=True)
def ensure_g03_03_05_schema():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

from test_g03_02_03_reconciliation_matches import (
    _create_confirmed_statement,
    _create_family_account,
    _create_transaction,
    reconciliation_match_client,
)


def test_ledger_only_endpoint_excludes_opening_balance_transactions(reconciliation_match_client):
    client = reconciliation_match_client
    headers, family_id, account_id, user_id = _create_family_account(client)
    _, _, session_id = _create_confirmed_statement(
        client, headers, family_id, account_id, user_id
    )

    with Session(engine) as db:
        expense_id = _create_transaction(
            db, family_id, account_id, user_id, "1200.0000", "超市消費",
            transaction_type="expense",
        )
        income_id = _create_transaction(
            db, family_id, account_id, user_id, "5000.0000", "薪資入帳",
            transaction_type="income",
        )
        opening_id = _create_transaction(
            db, family_id, account_id, user_id, "30000.0000", "帳戶期初餘額",
            transaction_type="opening_balance",
        )
        db.commit()

    response = client.get(
        f"/reconciliations/sessions/{session_id}/ledger-only?family_id={family_id}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    transaction_ids = {item["id"] for item in response.json()["transactions"]}
    assert transaction_ids == {expense_id, income_id}
    assert opening_id not in transaction_ids


def test_two_way_reconciliation_ui_exposes_all_g03_03_panels():
    with TestClient(__import__("main").app) as client:
        home = client.get("/")
        javascript = client.get("/static/reconciliation.js")
        css = client.get("/static/styles.css")

    assert home.status_code == 200
    assert 'id="reconciliation-opening-balance"' in home.text
    assert 'id="reconciliation-closing-balance"' in home.text
    assert 'id="reconciliation-ledger-only-list"' in home.text
    assert 'id="reconciliation-balance-check"' in home.text
    assert 'id="reconciliation-issues-list"' in home.text
    assert 'id="reconciliation-final-report"' in home.text
    assert javascript.status_code == 200
    assert 'base+"/ledger-only?limit=500"' in javascript.text
    assert 'base+"/balance-check"' in javascript.text
    assert 'base+"/issues?limit=200"' in javascript.text
    assert 'base+"/final-report"' in javascript.text
    assert '"/resolve?family_id="+selectedFamilyId' in javascript.text
    assert css.status_code == 200
    assert ".reconciliation-advanced-grid" in css.text
    assert "@media(max-width:760px)" in css.text


def test_completion_button_requires_successful_final_report():
    with TestClient(__import__("main").app) as client:
        javascript = client.get("/static/reconciliation.js").text

    assert 'const ready=report?.ready_to_complete===true' in javascript
    assert 'button.disabled=!ready' in javascript
    assert "無法載入時不會允許完成對帳" in javascript
