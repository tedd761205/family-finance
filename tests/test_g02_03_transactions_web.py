from fastapi.testclient import TestClient

from main import app


def test_transaction_management_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-transactions"' in response.text
    assert 'id="transactions-view"' in response.text
    assert 'id="transactions-list"' in response.text
    assert 'id="transaction-form"' in response.text


def test_transaction_workspace_uses_existing_transaction_and_category_apis():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/transactions?"+transactionQuery())' in javascript
    assert 'api("/categories?family_id="+selectedFamilyId)' in javascript
    assert 'method:"POST"' in javascript
    assert 'method:"PATCH"' in javascript
    assert 'method:"DELETE"' in javascript
    assert 'transaction_type:type' in javascript
    assert 'category_id:categoryId?Number(categoryId):null' in javascript


def test_transaction_workspace_protects_managed_transfer_and_payment_rows():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'item.transfer_id!==null||item.credit_card_payment_id!==null||item.bill_payment_id!==null' in javascript
    assert "請至對應功能修改或作廢" in javascript
    assert "include_voided" in javascript


def test_transaction_update_does_not_send_create_only_currency_field():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'if(wasEditing) {' in javascript
    assert 'delete payload.currency_code;' in javascript
    assert 'method:"PATCH",body:JSON.stringify(payload)' in javascript


def test_transaction_workspace_includes_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".transactions-list" in css
    assert ".transaction-filters" in css
    assert "@media(max-width:420px)" in css
